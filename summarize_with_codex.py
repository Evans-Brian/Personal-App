"""One-time chapter summaries using the signed-in Codex CLI, not OpenAI API billing.

The transcript and summary cache stay in the private BJJ library. Each completed
batch is saved immediately, so an interrupted run resumes without repeating it.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from bjj import BJJLibrary
from chapter_ai import CODEX_PROMPT_VERSION, CODEX_SUMMARY_MODEL
from setup_chapter_search import _atomic_write, _load


SCHEMA = {
    "type": "object",
    "properties": {
        "summaries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "summary": {"type": "string"}},
                "required": ["id", "summary"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summaries"],
    "additionalProperties": False,
}


def pending_chapters(library, cache, model_tag=CODEX_SUMMARY_MODEL):
    pending = []
    for source in library.chapter_sources():
        digest = sha256(source["content"].encode("utf-8")).hexdigest()
        cached = cache["summaries"].get(source["id"], {})
        if (cached.get("source_sha256") == digest
                and cached.get("model") == model_tag
                and cached.get("prompt_version") == CODEX_PROMPT_VERSION
                and cached.get("summary")):
            continue
        pending.append({"id": source["id"], "title": source["title"],
                        "instructor": source["instructor"],
                        "transcript": source["content"], "source_sha256": digest})
    return pending


def summarize_batch(chapters, model, work_dir, timeout=600):
    work_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="codex-chapters-", dir=work_dir) as scratch:
        scratch = Path(scratch)
        schema_path = scratch / "schema.json"
        output_path = scratch / "summaries.json"
        schema_path.write_text(json.dumps(SCHEMA), encoding="utf-8")
        prompt = (
            "Summarize each BJJ instructional chapter below for semantic search. "
            "Use only the supplied transcripts. Cut filler, repetition, and verbal tics. "
            "Preserve actual positions, grips, actions, reactions, troubleshooting, submissions, "
            "and decision points. Treat the title and instructor fields as authoritative for names; "
            "do not infer other names from noisy speech recognition. Correct obvious transcription "
            "spacing only. Do not invent "
            "techniques, outcomes, or people. Write one dense paragraph of roughly 100–180 "
            "words per chapter, or shorter when the source is too thin. Return exactly one "
            "summary per supplied ID. Do not call tools or access other files.\n\n"
            + json.dumps([{"id": item["id"], "title": item["title"],
                           "instructor": item["instructor"],
                           "transcript": item["transcript"]} for item in chapters], ensure_ascii=False)
        )
        environment = os.environ.copy()
        environment.pop("OPENAI_API_KEY", None)
        environment.pop("TYPESAFE_API_KEY", None)
        executable = shutil.which("codex.exe") or shutil.which("codex.cmd") or shutil.which("codex")
        if not executable:
            raise RuntimeError("Codex CLI was not found on PATH.")
        command = [executable, "exec", "-m", model, "--sandbox", "read-only",
                   "--skip-git-repo-check", "--ephemeral", "--ignore-user-config",
                   "--output-schema", str(schema_path), "--output-last-message", str(output_path),
                   "-C", str(work_dir), "-"]
        result = subprocess.run(command, input=prompt.encode("utf-8"), capture_output=True,
                                env=environment, timeout=timeout, check=False)
        if result.returncode != 0 or not output_path.is_file():
            (work_dir / "codex-summary-last-error.log").write_bytes(result.stderr)
            raise RuntimeError(f"Codex batch failed (exit {result.returncode}); no cache entries were changed.")
        response = json.loads(output_path.read_text(encoding="utf-8"))
    values = response.get("summaries", [])
    expected = {item["id"] for item in chapters}
    if len(values) != len(chapters) or {item.get("id") for item in values} != expected:
        raise ValueError("Codex returned missing, duplicate, or unexpected chapter IDs.")
    summaries = {}
    for item in values:
        summary = " ".join(str(item.get("summary", "")).split())
        if not 15 <= len(summary.split()) <= 230:
            raise ValueError(f"Codex returned an implausible summary length for {item['id']}.")
        summaries[item["id"]] = summary
    return summaries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bjj-library", type=Path, required=True)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=6)
    parser.add_argument("--limit", type=int, help="Summarize at most this many pending chapters")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rebuild", action="store_true", help="Rebuild the local search index after summarizing")
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 10:
        parser.error("--batch-size must be between 1 and 10")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    library = BJJLibrary(args.bjj_library, args.vault)
    cache = _load(library.summary_path)
    pending = pending_chapters(library, cache)
    total = len(library.chapter_sources())
    print(f"{total} chapters; {len(pending)} need Codex summaries.", flush=True)
    if args.dry_run:
        return
    selected = pending[:args.limit] if args.limit else pending
    for start in range(0, len(selected), args.batch_size):
        batch = selected[start:start + args.batch_size]
        summaries = summarize_batch(batch, "gpt-6-luna", library.root / "work")
        for source in batch:
            cache["summaries"][source["id"]] = {
                "source_sha256": source["source_sha256"],
                "model": CODEX_SUMMARY_MODEL,
                "prompt_version": CODEX_PROMPT_VERSION,
                "summary": summaries[source["id"]],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        _atomic_write(library.summary_path, cache)
        print(f"Saved {start + len(batch)}/{len(selected)} selected chapters.", flush=True)
    if args.rebuild and not args.limit:
        result = library.rebuild_index(require_summaries=True)
        print(f"Rebuilt local search index: {result['sources']}", flush=True)


if __name__ == "__main__":
    main()
