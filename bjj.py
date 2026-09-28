"""Private BJJ media library, transcript index, and portable notes."""
from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path

COURSES = (
    {"id": "down-right-sloppy-half-butterfly", "title": "Down Right Sloppy Half Butterfly", "instructor": "Eoghan O'Flanagan"},
    {"id": "octopus-guard-2", "title": "Octopus Guard 2.0", "instructor": "Craig Jones"},
    {"id": "shotgun-k-guard", "title": "Shotgun K Guard", "instructor": "Mateusz Szczecinski"},
)
TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9'_-]*", re.I)


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


def _embedding(text, dimensions=192):
    """Small deterministic local embedding suitable for this 12-video collection."""
    vector = [0.0] * dimensions
    words = _words(text)
    for token in words + [" ".join(words[i:i + 2]) for i in range(max(0, len(words) - 1))]:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        number = int.from_bytes(digest, "little")
        vector[number % dimensions] += -1.0 if number & 1 else 1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


class BJJLibrary:
    def __init__(self, root, vault):
        self.root = Path(root).resolve()
        self.vault = Path(vault).resolve()
        self.media_root = self.root / "media"
        self.transcript_root = self.root / "transcripts"
        self.index_path = self.root / "index" / "bjj.sqlite3"
        self.manifest_path = self.root / "manifest.json"

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
        return {"courses": result, "index_ready": self.index_path.is_file()}

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
              media_sha256 TEXT NOT NULL, embedding TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(id UNINDEXED, excerpt, chapter, instructor, course_id);
        """)
        return connection

    def rebuild_index(self):
        manifest = self.manifest()
        with closing(self.connect()) as connection:
            connection.execute("DELETE FROM chunks")
            connection.execute("DELETE FROM chunks_fts")
            count = 0
            for item in manifest["media"]:
                payload = self.transcript(item["id"])
                segments = payload["segments"]
                course = next((course for course in COURSES if course["id"] == item["course_id"]), None)
                if not course:
                    continue
                index = 0
                while index < len(segments):
                    chapter_id = segments[index].get("chapter_id") or "Unchaptered"
                    group, words = [], 0
                    while index < len(segments):
                        segment = segments[index]
                        if (segment.get("chapter_id") or "Unchaptered") != chapter_id and group:
                            break
                        text = (segment.get("corrected_text") or segment.get("raw_text") or segment.get("text") or "").strip()
                        group.append(segment)
                        words += len(_words(text))
                        index += 1
                        if words >= 350:
                            break
                    text = " ".join((segment.get("corrected_text") or segment.get("raw_text") or segment.get("text") or "").strip() for segment in group).strip()
                    if not text:
                        continue
                    chunk_id = f"{item['id']}:{int(group[0].get('segment_id', index)):06d}"
                    values = (chunk_id, item["id"], item["course_id"], course["instructor"], int(item["volume"]), str(chapter_id),
                              float(group[0]["start_seconds"]), float(group[-1]["end_seconds"]), text,
                              item.get("sha256", ""), json.dumps(_embedding(text), separators=(",", ":")))
                    connection.execute("INSERT OR REPLACE INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?,?)", values)
                    connection.execute("INSERT INTO chunks_fts(id,excerpt,chapter,instructor,course_id) VALUES (?,?,?,?,?)", (chunk_id, text, chapter_id, course["instructor"], item["course_id"]))
                    count += 1
            connection.commit()
        return {"chunks": count}

    def search(self, query, course_id="", volume="", chapter="", semantic=False, limit=30):
        query = (query or "").strip()
        if not query or len(query) > 300:
            raise ValueError("Enter a search query up to 300 characters.")
        limit = min(max(int(limit), 1), 100)
        if not self.index_path.exists():
            return []
        clauses, values = [], []
        if course_id:
            clauses.append("c.course_id = ?"); values.append(course_id)
        if volume:
            clauses.append("c.volume = ?"); values.append(int(volume))
        if chapter:
            clauses.append("c.chapter = ?"); values.append(chapter)
        where = (" AND " + " AND ".join(clauses)) if clauses else ""
        with closing(self.connect()) as connection:
            if semantic:
                rows = connection.execute("SELECT c.* FROM chunks c WHERE 1=1" + where, values).fetchall()
                needle = _embedding(query)
                ranked = sorted(((sum(a * b for a, b in zip(needle, json.loads(row["embedding"]))), row) for row in rows), reverse=True, key=lambda x: x[0])[:limit]
                return [self._result(row, score) for score, row in ranked if score > 0]
            terms = " ".join(f'"{word}"' for word in _words(query))
            if not terms:
                return []
            rows = connection.execute("SELECT c.*, bm25(chunks_fts) score FROM chunks_fts JOIN chunks c ON c.id=chunks_fts.id WHERE chunks_fts MATCH ?" + where + " ORDER BY score LIMIT ?", [terms, *values, limit]).fetchall()
            return [self._result(row, -float(row["score"])) for row in rows]

    @staticmethod
    def _result(row, score):
        return {key: row[key] for key in ("media_id", "course_id", "instructor", "volume", "chapter", "start_seconds", "end_seconds", "excerpt")} | {"score": score}

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
        return {"path": str(path.relative_to(self.vault)), "media_id": media_id, "timestamp": timestamp}

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
        folder = self.vault / "BJJ" / "Journal"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{day}.md"
        fields = (("techniques", "Techniques studied"), ("drills", "Drills"), ("sparring", "Sparring observations"),
                  ("worked", "What worked"), ("problems", "Problems encountered"), ("next_focus", "Next practice focus"))
        lines = ["---", f"date: {day}", "type: bjj-training-journal", "tags: [bjj, training]", "---", "", f"# BJJ training — {day}", ""]
        for key, title in fields:
            value = str(data.get(key) or "").strip()
            if len(value) > 20_000:
                raise ValueError("Training journal field is too long.")
            lines.extend([f"## {title}", "", value, ""])
        temporary = path.with_suffix(".tmp")
        temporary.write_text("\n".join(lines), encoding="utf-8")
        temporary.replace(path)
        return {"path": str(path.relative_to(self.vault)), "date": day, "saved_at": _utc_now()}

    def training(self, day):
        day = _safe_day(day)
        path = self.vault / "BJJ" / "Journal" / f"{day}.md"
        values = {key: "" for key in ("techniques", "drills", "sparring", "worked", "problems", "next_focus")}
        if not path.is_file():
            return {"date": day, **values}
        text = path.read_text(encoding="utf-8")
        fields = (("techniques", "Techniques studied"), ("drills", "Drills"), ("sparring", "Sparring observations"),
                  ("worked", "What worked"), ("problems", "Problems encountered"), ("next_focus", "Next practice focus"))
        for key, title in fields:
            match = re.search(rf"^## {re.escape(title)}\s*\n\s*(.*?)(?=^## |\Z)", text, re.M | re.S)
            if match:
                values[key] = match.group(1).strip()
        return {"date": day, "path": str(path.relative_to(self.vault)), **values}
