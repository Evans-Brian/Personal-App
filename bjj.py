"""Private BJJ media library, transcript index, and portable notes."""
from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import tempfile
import threading
from contextlib import closing
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path

from embeddings import EmbeddingUnavailable, LocalBGEEmbedder, blob_to_vector, vector_to_blob
from chapter_ai import (
    AIServiceUnavailable,
    JEV_SHORTLIST,
    OPENAI_SUMMARY_MODEL,
    SUMMARY_PROMPT_VERSION,
    JevReranker,
)
from journal import Conflict

COURSES = (
    {"id": "down-right-sloppy-half-butterfly", "title": "Down Right Sloppy Half Butterfly", "instructor": "Eoghan O'Flanagan"},
    {"id": "octopus-guard-2", "title": "Octopus Guard 2.0", "instructor": "Craig Jones"},
    {"id": "shotgun-k-guard", "title": "Shotgun K Guard", "instructor": "Mateusz Szczecinski"},
)
TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9'_-]*", re.I)
SEARCH_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "because", "but", "by", "can", "do", "for", "from",
    "get", "how", "i", "in", "into", "is", "it", "me", "my", "of", "on", "or", "should", "that",
    "the", "their", "this", "to", "was", "what", "when", "while", "why", "with",
}
INDEX_SOURCE_TYPES = ("bjj_transcript", "bjj_training", "bjj_note")


def _utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_day(value):
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError):
        raise ValueError("Expected a date in YYYY-MM-DD format.")


def _number(value, name, minimum=0):
    if isinstance(value, bool):
        raise ValueError(f"Invalid {name}.")
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid {name}.")
    if not math.isfinite(result) or result < minimum:
        raise ValueError(f"Invalid {name}.")
    return result


def _words(text):
    return TOKEN_RE.findall((text or "").lower())


def _plain_markdown(text):
    text = re.sub(r"\A---\s*\n.*?\n---\s*\n", "", text, flags=re.S)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"!\[([^]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^\s*(?:[-*+]\s+)?\[[ xX]\]\s*", "", text, flags=re.M)
    text = re.sub(r"^[#>*_`~-]+\s*", "", text, flags=re.M)
    return re.sub(r"\s+", " ", text).strip()


def _text_windows(text, target_words=160, overlap_words=30):
    words = text.split()
    if not words:
        return []
    windows = []
    start = 0
    while start < len(words):
        end = min(start + target_words, len(words))
        windows.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start = max(start + 1, end - overlap_words)
    return windows


class BJJLibrary:
    def __init__(self, root, vault, embedder=None, reranker=None):
        self.root = Path(root).resolve()
        self.vault = Path(vault).resolve()
        self.media_root = self.root / "media"
        self.transcript_root = self.root / "transcripts"
        self.index_path = self.root / "index" / "bjj.sqlite3"
        self.summary_path = self.root / "work" / "chapter-summaries.json"
        self.manifest_path = self.root / "manifest.json"
        self.embedder = embedder or LocalBGEEmbedder()
        self.reranker = reranker or JevReranker()
        self.training_lock = threading.Lock()

    def manifest(self):
        if not self.manifest_path.exists():
            return {"version": 1, "updated_at": None, "media": []}
        data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("media"), list):
            raise ValueError("BJJ manifest is invalid.")
        return data

    def _entry_path(self, entry):
        relative = Path(entry.get("path", ""))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("BJJ manifest contains an unsafe media path.")
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.media_root) or not path.is_file():
            raise ValueError("BJJ media file is missing or outside the media folder.")
        return path

    def entry(self, media_id):
        if not isinstance(media_id, str) or not re.fullmatch(r"[a-z0-9-]+-v0[1-4]", media_id):
            raise ValueError("Unknown media ID.")
        for item in self.manifest()["media"]:
            if item.get("id") == media_id:
                return item, self._entry_path(item)
        raise ValueError("Unknown media ID.")

    def transcript(self, media_id):
        item, _ = self.entry(media_id)
        relative = Path(item.get("transcript", f"transcripts/{item['course_id']}/v{int(item['volume']):02d}.segments.json"))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Unsafe transcript path.")
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.transcript_root) or not path.is_file():
            return {"media_id": media_id, "segments": [], "chapters": item.get("chapters", [])}
        data = json.loads(path.read_text(encoding="utf-8"))
        segments = data.get("segments", data) if isinstance(data, dict) else data
        if not isinstance(segments, list):
            raise ValueError("Transcript is invalid.")
        return {"media_id": media_id, "segments": segments, "chapters": item.get("chapters", [])}

    def library(self):
        entries = self.manifest()["media"]
        result = []
        for course in COURSES:
            volumes = []
            for item in sorted((x for x in entries if x.get("course_id") == course["id"]), key=lambda x: x.get("volume", 0)):
                try:
                    present = self._entry_path(item).is_file()
                except ValueError:
                    present = False
                transcript_path = self.root / item.get("transcript", f"transcripts/{course['id']}/v{int(item.get('volume', 0)):02d}.segments.json")
                volumes.append({
                    "id": item.get("id"), "volume": item.get("volume"), "duration": item.get("duration_seconds"),
                    "present": present, "transcribed": transcript_path.is_file(), "chapters": item.get("chapters", []),
                })
            result.append({**course, "volumes": volumes, "complete": len(volumes) == 4 and all(x["present"] for x in volumes),
                           "duration": sum((x.get("duration") or 0) for x in volumes)})
        index = {"ready": False, "embedding_model": None, "chunks": 0}
        if self.index_path.is_file():
            try:
                with closing(self.connect()) as connection:
                    metadata = dict(connection.execute("SELECT key, value FROM index_meta").fetchall())
                index = {"ready": metadata.get("embedding_model") == self.embedder.version,
                         "embedding_model": metadata.get("embedding_model"),
                         "chunks": int(metadata.get("chunks", 0))}
            except (sqlite3.Error, ValueError):
                pass
        return {"courses": result, "index_ready": index["ready"], "search_index": index}

    def connect(self):
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.index_path)
        connection.row_factory = sqlite3.Row
        connection.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS chunks (
              id TEXT PRIMARY KEY, media_id TEXT NOT NULL, course_id TEXT NOT NULL,
              instructor TEXT NOT NULL, volume INTEGER NOT NULL, chapter TEXT NOT NULL,
              start_seconds REAL NOT NULL, end_seconds REAL NOT NULL, excerpt TEXT NOT NULL,
              media_sha256 TEXT NOT NULL, embedding BLOB NOT NULL,
              source_type TEXT NOT NULL DEFAULT 'bjj_transcript', source_path TEXT NOT NULL DEFAULT '',
              journal_date TEXT NOT NULL DEFAULT '', section TEXT NOT NULL DEFAULT '',
              title TEXT NOT NULL DEFAULT '', embedding_model TEXT NOT NULL DEFAULT 'hash-v1',
              content TEXT NOT NULL DEFAULT '', summary TEXT NOT NULL DEFAULT ''
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(id UNINDEXED, excerpt, chapter, instructor, course_id);
            CREATE TABLE IF NOT EXISTS index_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(chunks)")}
        migrations = {
            "source_type": "TEXT NOT NULL DEFAULT 'bjj_transcript'", "source_path": "TEXT NOT NULL DEFAULT ''",
            "journal_date": "TEXT NOT NULL DEFAULT ''", "section": "TEXT NOT NULL DEFAULT ''",
            "title": "TEXT NOT NULL DEFAULT ''", "embedding_model": "TEXT NOT NULL DEFAULT 'hash-v1'",
            "content": "TEXT NOT NULL DEFAULT ''", "summary": "TEXT NOT NULL DEFAULT ''",
        }
        for name, definition in migrations.items():
            if name not in columns:
                connection.execute(f"ALTER TABLE chunks ADD COLUMN {name} {definition}")
        deprecated = [row[0] for row in connection.execute(
            "SELECT id FROM chunks WHERE source_type = ?", ("general_journal",)
        )]
        if deprecated:
            connection.executemany("DELETE FROM chunks_fts WHERE id = ?", ((identifier,) for identifier in deprecated))
            connection.execute("DELETE FROM chunks WHERE source_type = ?", ("general_journal",))
            count = connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            connection.execute("INSERT OR REPLACE INTO index_meta(key,value) VALUES ('chunks',?)", (str(count),))
            connection.execute("INSERT OR REPLACE INTO index_meta(key,value) VALUES ('updated_at',?)", (_utc_now(),))
        connection.commit()
        return connection

    def rebuild_index(self, require_summaries=False):
        documents = [*self._transcript_documents(), *self._vault_documents()]
        transcript_documents = [document for document in documents if document["source_type"] == "bjj_transcript"]
        missing_summaries = [document["id"] for document in transcript_documents if not document.get("summary")]
        if require_summaries and missing_summaries:
            raise RuntimeError(
                f"{len(missing_summaries)} chapters are missing AI summaries. Run setup_chapter_search.py with OPENAI_API_KEY set."
            )
        vectors, embedding_model = self._embed_documents(documents)
        with closing(self.connect()) as connection:
            with connection:
                connection.execute("DELETE FROM chunks")
                connection.execute("DELETE FROM chunks_fts")
                connection.execute("DELETE FROM index_meta")
                for document, vector in zip(documents, vectors):
                    self._insert_document(connection, document, vector, embedding_model)
                metadata = {"schema_version": "4", "embedding_model": self.embedder.version,
                            "embedding_dimensions": str(self.embedder.dimensions), "chunks": str(len(documents)),
                            "built_at": _utc_now(), "chapter_summaries": str(len(transcript_documents) - len(missing_summaries)),
                            "summary_model": OPENAI_SUMMARY_MODEL if transcript_documents and not missing_summaries else ""}
                if not embedding_model:
                    metadata["embedding_model"] = ""
                    metadata["embedding_dimensions"] = "0"
                connection.executemany("INSERT INTO index_meta(key,value) VALUES (?,?)", metadata.items())
        counts = {}
        for document in documents:
            counts[document["source_type"]] = counts.get(document["source_type"], 0) + 1
        return {"chunks": len(documents), "sources": counts, "embedding_model": embedding_model,
                "dimensions": self.embedder.dimensions}

    def _embed_documents(self, documents, semantic=True):
        if not semantic:
            return [self._empty_vector() for _ in documents], ""
        try:
            if hasattr(self.embedder, "embed_document_parts"):
                vectors = self.embedder.embed_document_parts([
                    document.get("embedding_parts", [document["embedding_text"]]) for document in documents
                ])
            else:
                vectors = self.embedder.embed_documents([document["embedding_text"] for document in documents])
        except EmbeddingUnavailable:
            return [self._empty_vector() for _ in documents], ""
        if len(vectors) != len(documents) or any(len(vector) != self.embedder.dimensions for vector in vectors):
            raise RuntimeError("The embedding model returned an unexpected number or size of vectors.")
        return vectors, self.embedder.version

    def _empty_vector(self):
        return [0.0] * self.embedder.dimensions

    def _summary_cache(self):
        if not self.summary_path.is_file():
            return {}
        data = json.loads(self.summary_path.read_text(encoding="utf-8"))
        summaries = data.get("summaries", {}) if isinstance(data, dict) else {}
        return summaries if isinstance(summaries, dict) else {}

    def chapter_sources(self):
        documents = []
        summaries = self._summary_cache()
        for item in self.manifest()["media"]:
            course = next((value for value in COURSES if value["id"] == item.get("course_id")), None)
            if not course:
                continue
            segments = self.transcript(item["id"])["segments"]
            chapters = {chapter.get("id"): chapter.get("title", chapter.get("id")) for chapter in item.get("chapters", [])}
            groups = []
            for segment in segments:
                chapter_id = segment.get("chapter_id") or "Unchaptered"
                if not groups or groups[-1][0] != chapter_id:
                    groups.append((chapter_id, []))
                groups[-1][1].append(segment)
            for chapter_id, group in groups:
                content = " ".join(
                    (segment.get("corrected_text") or segment.get("raw_text") or segment.get("text") or "").strip()
                    for segment in group
                ).strip()
                if not content:
                    continue
                title = chapters.get(chapter_id, str(chapter_id))
                identifier = f"{item['id']}:{chapter_id}"
                summary_entry = summaries.get(identifier, {})
                digest = sha256(content.encode("utf-8")).hexdigest()
                summary = ""
                if (summary_entry.get("source_sha256") == digest
                        and summary_entry.get("model") == OPENAI_SUMMARY_MODEL
                        and summary_entry.get("prompt_version") == SUMMARY_PROMPT_VERSION):
                    summary = str(summary_entry.get("summary", "")).strip()
                display = summary or content
                documents.append({
                    "id": identifier, "media_id": item["id"], "course_id": item["course_id"],
                    "instructor": course["instructor"], "volume": int(item["volume"]), "chapter": str(chapter_id),
                    "start_seconds": float(group[0]["start_seconds"]), "end_seconds": float(group[-1]["end_seconds"]),
                    "excerpt": display, "content": content, "summary": summary, "search_text": content,
                    "media_sha256": item.get("sha256", ""), "source_type": "bjj_transcript",
                    "source_path": item.get("transcript", ""), "journal_date": "", "section": title,
                    "title": f"{course['title']} · Volume {item['volume']} · {title}",
                    "embedding_text": f"BJJ instructional chapter. {course['title']}. {title}. {display}",
                    "embedding_parts": [
                        f"BJJ instructional chapter. {course['title']}. {title}. {part}"
                        for part in ([summary] if summary else []) + _text_windows(content, target_words=160, overlap_words=30)
                    ],
                })
        return documents

    def _transcript_documents(self):
        return self.chapter_sources()

    def _vault_documents(self):
        documents = []
        folders = ((self.vault / "BJJ" / "Journal", "bjj_training"),
                   (self.vault / "BJJ" / "Study Notes", "bjj_note"))
        for folder, source_type in folders:
            if not folder.is_dir():
                continue
            for path in sorted(folder.glob("*.md")):
                documents.extend(self._markdown_documents(path, source_type))
        return documents

    def _markdown_documents(self, path, source_type):
        raw = path.read_text(encoding="utf-8")
        body = re.sub(r"\A---\s*\n.*?\n---\s*\n", "", raw, flags=re.S)
        headings = list(re.finditer(r"^(#{1,3})\s+(.+?)\s*$", body, re.M))
        relative = str(path.relative_to(self.vault)).replace("\\", "/")
        journal_date = path.stem[:10] if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", path.stem) else ""
        note_metadata = {"media_id": "", "course_id": "", "instructor": "", "volume": 0, "start_seconds": 0.0}
        if source_type == "bjj_note":
            media_match = re.search(r"^media_id:\s*(\S+)\s*$", raw, re.M)
            time_match = re.search(r"^timestamp_seconds:\s*([0-9.]+)\s*$", raw, re.M)
            if media_match:
                item = next((value for value in self.manifest()["media"] if value.get("id") == media_match.group(1)), None)
                course = next((value for value in COURSES if item and value["id"] == item.get("course_id")), None)
                if item and course:
                    note_metadata = {"media_id": item["id"], "course_id": item["course_id"],
                                     "instructor": course["instructor"], "volume": int(item["volume"]),
                                     "start_seconds": float(time_match.group(1)) if time_match else 0.0}
        documents = []
        if not headings:
            headings = [re.match(r"", body)]
        for position, heading in enumerate(headings):
            title = heading.group(2).strip() if heading and heading.lastindex else path.stem
            start = heading.end() if heading else 0
            end = headings[position + 1].start() if position + 1 < len(headings) else len(body)
            excerpt = _plain_markdown(body[start:end])
            if len(_words(excerpt)) < 3:
                continue
            for part, window in enumerate(_text_windows(excerpt)):
                context = {"bjj_training": "BJJ training journal", "bjj_note": "BJJ study note"}[source_type]
                documents.append({
                    "id": f"{source_type}:{relative}:{position:03d}:{part:03d}", **note_metadata,
                    "chapter": title, "end_seconds": note_metadata["start_seconds"],
                    "excerpt": window, "media_sha256": "", "source_type": source_type, "source_path": relative,
                    "journal_date": journal_date, "section": title, "title": f"{journal_date} · {title}" if journal_date else title,
                    "embedding_text": f"{context}. Date {journal_date}. Section {title}. {window}",
                })
        return documents

    def _insert_document(self, connection, document, vector, embedding_model=None):
        if document.get("source_type") not in INDEX_SOURCE_TYPES:
            raise ValueError("Only BJJ material can be added to the BJJ search index.")
        columns = ("id", "media_id", "course_id", "instructor", "volume", "chapter", "start_seconds", "end_seconds",
                   "excerpt", "media_sha256", "embedding", "source_type", "source_path", "journal_date", "section", "title",
                   "embedding_model", "content", "summary")
        values = [document.get(column, "") for column in columns]
        values[10] = vector_to_blob(vector)
        values[16] = self.embedder.version if embedding_model is None else embedding_model
        connection.execute(f"INSERT OR REPLACE INTO chunks({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", values)
        connection.execute("INSERT INTO chunks_fts(id,excerpt,chapter,instructor,course_id) VALUES (?,?,?,?,?)",
                           (document["id"], document.get("search_text", document["excerpt"]), document["section"],
                            document["instructor"], document["course_id"]))

    def refresh_journal(self, path, source_type="bjj_training"):
        """Refresh one saved Markdown file without rebuilding every transcript."""
        path = Path(path).resolve()
        allowed_roots = {
            "bjj_training": self.vault / "BJJ" / "Journal",
            "bjj_note": self.vault / "BJJ" / "Study Notes",
        }
        root = allowed_roots.get(source_type)
        if root is None or not path.is_relative_to(root.resolve()):
            raise ValueError("Cannot index that journal path.")
        if not self.index_path.is_file():
            return {"indexed": 0, "skipped": True}
        documents = self._markdown_documents(path, source_type) if path.is_file() else []
        relative = str(path.relative_to(self.vault)).replace("\\", "/")
        with closing(self.connect()) as connection:
            metadata = dict(connection.execute("SELECT key, value FROM index_meta").fetchall())
            semantic = metadata.get("embedding_model") == self.embedder.version
            vectors, embedding_model = self._embed_documents(documents, semantic=semantic)
            with connection:
                identifiers = [row[0] for row in connection.execute("SELECT id FROM chunks WHERE source_path = ?", (relative,))]
                connection.executemany("DELETE FROM chunks_fts WHERE id = ?", ((identifier,) for identifier in identifiers))
                connection.execute("DELETE FROM chunks WHERE source_path = ?", (relative,))
                for document, vector in zip(documents, vectors):
                    self._insert_document(connection, document, vector, embedding_model)
                count = connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
                connection.execute("INSERT OR REPLACE INTO index_meta(key,value) VALUES ('chunks',?)", (str(count),))
                connection.execute("INSERT OR REPLACE INTO index_meta(key,value) VALUES ('updated_at',?)", (_utc_now(),))
        return {"indexed": len(documents), "skipped": False}

    def search(self, query, course_id="", volume="", chapter="", semantic=False, limit=30, source="bjj"):
        query = (query or "").strip()
        if not query or len(query) > 300:
            raise ValueError("Enter a search query up to 300 characters.")
        limit = min(max(int(limit), 1), 100)
        if not self.index_path.exists():
            return []
        if source not in {"bjj", "training", "all"}:
            raise ValueError("Unknown search source.")
        clauses, values = [], []
        source_types = {"bjj": ("bjj_transcript",), "training": ("bjj_training",), "all": INDEX_SOURCE_TYPES}[source]
        clauses.append("c.source_type IN (" + ",".join("?" for _ in source_types) + ")"); values.extend(source_types)
        if course_id:
            clauses.append("c.course_id = ?"); values.append(course_id)
        if volume:
            clauses.append("c.volume = ?"); values.append(int(volume))
        if chapter:
            clauses.append("c.chapter = ?"); values.append(chapter)
        where = (" AND " + " AND ".join(clauses)) if clauses else ""
        with closing(self.connect()) as connection:
            if semantic:
                semantic_rows = connection.execute("SELECT c.* FROM chunks c WHERE c.embedding_model = ?" + where,
                                                   [self.embedder.version, *values]).fetchall()
                if not semantic_rows:
                    raise ValueError("The related-ideas index is missing or outdated. Run `python setup_embeddings.py` to rebuild it.")
                needle = self.embedder.embed_query(query)
                semantic_ranked = sorted(((sum(a * b for a, b in zip(needle, blob_to_vector(row["embedding"]))), row)
                                          for row in semantic_rows), reverse=True, key=lambda item: item[0])[:max(limit * 4, 60)]
                lexical = self._fts_rows(connection, query, where, values, max(limit * 4, 60), any_term=True)
                combined = {}
                rows_by_id = {}
                for rank, (_, row) in enumerate(semantic_ranked, 1):
                    combined[row["id"]] = combined.get(row["id"], 0) + 0.85 / (60 + rank)
                    rows_by_id[row["id"]] = row
                for rank, row in enumerate(lexical, 1):
                    combined[row["id"]] = combined.get(row["id"], 0) + 0.15 / (60 + rank)
                    rows_by_id[row["id"]] = row
                ranked_ids = sorted(combined, key=combined.get, reverse=True)[:JEV_SHORTLIST]
                candidates = [self._result(rows_by_id[row_id], combined[row_id], internal=True) for row_id in ranked_ids]
                if self.reranker.available:
                    try:
                        candidates = self.reranker.rank(query, candidates)
                    except AIServiceUnavailable:
                        pass
                return [self._public_result(candidate) for candidate in candidates[:limit]]
            rows = self._fts_rows(connection, query, where, values, limit)
            return [self._result(row, -float(row["score"])) for row in rows]

    @staticmethod
    def _fts_rows(connection, query, where, values, limit, any_term=False):
        words = [word for word in _words(query) if word not in SEARCH_STOP_WORDS]
        if not words:
            return []
        separator = " OR " if any_term else " "
        terms = separator.join(f'"{word}"' for word in words)
        return connection.execute(
            "SELECT c.*, bm25(chunks_fts) score FROM chunks_fts JOIN chunks c ON c.id=chunks_fts.id "
            "WHERE chunks_fts MATCH ?" + where + " ORDER BY score LIMIT ?", [terms, *values, limit]
        ).fetchall()

    @staticmethod
    def _result(row, score, internal=False):
        keys = ("media_id", "course_id", "instructor", "volume", "chapter", "start_seconds", "end_seconds",
                "excerpt", "source_type", "source_path", "journal_date", "section", "title", "summary")
        result = {key: row[key] for key in keys} | {"score": score}
        if internal:
            result["_content"] = row["content"] or row["excerpt"]
        return result

    @staticmethod
    def _public_result(result):
        return {key: value for key, value in result.items() if not key.startswith("_")}

    def save_note(self, data):
        media_id = data.get("media_id")
        item, _ = self.entry(media_id)
        timestamp = _number(data.get("timestamp"), "timestamp")
        if timestamp > float(item.get("duration_seconds") or timestamp + 1):
            raise ValueError("Timestamp is outside the video.")
        text = str(data.get("text") or "").strip()
        excerpt = str(data.get("excerpt") or "").strip()
        if not text or len(text) > 20_000 or len(excerpt) > 2_000:
            raise ValueError("Enter a note up to 20,000 characters.")
        folder = self.vault / "BJJ" / "Study Notes"
        folder.mkdir(parents=True, exist_ok=True)
        created = datetime.now().astimezone()
        stem = f"{created:%Y-%m-%d} {media_id} {created:%H%M%S%f}"
        path = folder / f"{stem}.md"
        suffix = 2
        while path.exists():
            path = folder / f"{stem}-{suffix}.md"
            suffix += 1
        course = next(course for course in COURSES if course["id"] == item["course_id"])
        tags = [tag for tag in data.get("tags", []) if isinstance(tag, str) and re.fullmatch(r"[a-z0-9-]{1,40}", tag)]
        body = ["---", "type: bjj-study-note", f"created: {created.isoformat()}", f"course: {json.dumps(course['title'])}",
                f"instructor: {json.dumps(course['instructor'])}", f"volume: {int(item['volume'])}", f"media_id: {media_id}",
                f"timestamp_seconds: {timestamp:.3f}", f"tags: {json.dumps(['bjj', *tags])}", "---", "", f"# {course['title']} — Volume {item['volume']}", "",
                f"[Open at {int(timestamp)//60}:{int(timestamp)%60:02d}](bjj://{media_id}?t={timestamp:.3f})", ""]
        if excerpt:
            body.extend(["> " + excerpt.replace("\n", "\n> "), ""])
        body.extend([text, ""])
        path.write_text("\n".join(body), encoding="utf-8")
        result = {"path": str(path.relative_to(self.vault)), "media_id": media_id, "timestamp": timestamp}
        try:
            self.refresh_journal(path, "bjj_note")
        except (OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
            result["index_warning"] = str(exc)
        return result

    def notes(self, limit=100):
        folder = self.vault / "BJJ" / "Study Notes"
        if not folder.is_dir():
            return []
        notes = []
        pattern = re.compile(r"^(media_id|timestamp_seconds):\s*(.+)$", re.M)
        for path in sorted(folder.glob("*.md"), reverse=True)[:min(max(int(limit), 1), 500)]:
            text = path.read_text(encoding="utf-8")
            fields = dict(pattern.findall(text))
            media_id = fields.get("media_id", "").strip()
            try:
                timestamp = float(fields.get("timestamp_seconds", ""))
                self.entry(media_id)
            except (ValueError, TypeError):
                continue
            title = next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")), path.stem)
            notes.append({"path": str(path.relative_to(self.vault)), "title": title,
                          "media_id": media_id, "timestamp": timestamp})
        return notes

    def save_training(self, data):
        day = _safe_day(data.get("date"))
        revision = data.get("revision")
        folder = self.vault / "BJJ" / "Journal"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{day}.md"
        fields = (("general_notes", "General Notes"), ("session_goals", "Session Goals"),
                  ("problems", "Problems encountered"), ("worked", "What worked"))
        values = {}
        for key, title in fields:
            value = str(data.get(key) or "").strip()
            if len(value) > 20_000:
                raise ValueError("Training journal field is too long.")
            values[title] = value
        rating = str(data.get("rating") or "").strip()
        if rating and rating not in {"1", "2", "3", "4", "5"}:
            raise ValueError("Session rating must be from 1 to 5.")
        values["Session rating"] = rating
        with self.training_lock:
            raw = path.read_bytes() if path.exists() else b""
            current_revision = sha256(raw).hexdigest()
            if revision != current_revision:
                raise Conflict("This training note changed since you opened it. Copy your draft, then reload to review the latest note.")
            if path.is_file():
                text = raw.decode("utf-8")
                for title, value in values.items():
                    section = f"## {title}\n\n{value}\n\n"
                    pattern = rf"^## {re.escape(title)}\s*\n.*?(?=^## |\Z)"
                    if re.search(pattern, text, re.M | re.S):
                        text = re.sub(pattern, section, text, count=1, flags=re.M | re.S)
                    else:
                        text = text.rstrip() + "\n\n" + section
                output = text.rstrip() + "\n"
            else:
                lines = ["---", f"date: {day}", "type: bjj-training-journal", "tags: [bjj, training]", "---", "", f"# BJJ training — {day}", ""]
                for title, value in values.items():
                    lines.extend([f"## {title}", "", value, ""])
                output = "\n".join(lines)
            fd, temporary = tempfile.mkstemp(prefix=".bjj-training-", suffix=".tmp", dir=folder)
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                    handle.write(output)
                    handle.flush()
                    os.fsync(handle.fileno())
                latest_raw = path.read_bytes() if path.exists() else b""
                if sha256(latest_raw).hexdigest() != revision:
                    raise Conflict("The training note changed during saving. Your draft has not overwritten it.")
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            saved_revision = sha256(path.read_bytes()).hexdigest()
        result = {"path": str(path.relative_to(self.vault)), "date": day, "saved_at": _utc_now(), "revision": saved_revision}
        try:
            self.refresh_journal(path, "bjj_training")
        except (OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
            result["index_warning"] = str(exc)
        return result

    def training(self, day):
        day = _safe_day(day)
        path = self.vault / "BJJ" / "Journal" / f"{day}.md"
        values = {key: "" for key in ("rating", "general_notes", "session_goals", "problems", "worked")}
        if not path.is_file():
            return {"date": day, "revision": sha256(b"").hexdigest(), **values}
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        fields = (("general_notes", "General Notes"), ("session_goals", "Session Goals"),
                  ("problems", "Problems encountered"), ("worked", "What worked"), ("rating", "Session rating"))
        for key, title in fields:
            match = re.search(rf"^## {re.escape(title)}\s*\n\s*(.*?)(?=^## |\Z)", text, re.M | re.S)
            if match:
                values[key] = match.group(1).strip()
        if not values["general_notes"]:
            legacy_notes = []
            for title in ("Techniques studied", "Drills", "Sparring observations"):
                match = re.search(rf"^## {re.escape(title)}\s*\n\s*(.*?)(?=^## |\Z)", text, re.M | re.S)
                if match and match.group(1).strip():
                    legacy_notes.append(f"{title}:\n{match.group(1).strip()}")
            values["general_notes"] = "\n\n".join(legacy_notes)
        if not values["session_goals"]:
            match = re.search(r"^## Next practice focus\s*\n\s*(.*?)(?=^## |\Z)", text, re.M | re.S)
            if match:
                values["session_goals"] = match.group(1).strip()
        return {"date": day, "path": str(path.relative_to(self.vault)), "revision": sha256(raw).hexdigest(), **values}
