"""Generate cached chapter summaries, then rebuild the chapter-level search index."""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from bjj import BJJLibrary
from chapter_ai import OPENAI_SUMMARY_MODEL, SUMMARY_PROMPT_VERSION, OpenAIChapterSummarizer
from setup_embeddings import configured_paths, install_embeddings


def _load(path):
    if not path.is_file():
        return {"version": 1, "summaries": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("summaries"), dict):
        raise ValueError("The chapter summary cache is invalid.")
    return data


def _atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".chapter-summaries-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as output:
            json.dump(data, output, ensure_ascii=False, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def generate_summaries(library, summarizer, cache_path=None, progress=print):
    cache_path = Path(cache_path or library.summary_path)
    cache = _load(cache_path)
    sources = library.chapter_sources()
    changed = 0
    for position, source in enumerate(sources, 1):
        digest = sha256(source["content"].encode("utf-8")).hexdigest()
        cached = cache["summaries"].get(source["id"], {})
        if (cached.get("source_sha256") == digest and cached.get("model") == summarizer.model
                and cached.get("prompt_version") == SUMMARY_PROMPT_VERSION and cached.get("summary")):
            continue
        summary = summarizer.summarize(source["title"], source["content"])
        cache["summaries"][source["id"]] = {
            "source_sha256": digest,
            "model": summarizer.model,
            "prompt_version": SUMMARY_PROMPT_VERSION,
            "summary": summary,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        _atomic_write(cache_path, cache)
        changed += 1
        progress(f"Summarized chapter {position}/{len(sources)}: {source['id']}")
    return {"chapters": len(sources), "generated": changed, "cache": str(cache_path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bjj-library", type=Path)
    parser.add_argument("--vault", type=Path)
    parser.add_argument("--skip-embedding-install", action="store_true")
    args = parser.parse_args()
    configured_bjj, configured_vault = configured_paths()
    bjj_root, vault = args.bjj_library or configured_bjj, args.vault or configured_vault
    if not bjj_root.is_dir() or not vault.is_dir():
        raise SystemExit("The BJJ library and vault folders must exist. Pass both paths explicitly.")
    library = BJJLibrary(bjj_root, vault)
    summarizer = OpenAIChapterSummarizer(api_key=library.openai_api_key())
    if not summarizer.available:
        raise SystemExit("Set OPENAI_API_KEY before generating chapter summaries.")
    if not args.skip_embedding_install:
        install_embeddings()
    result = generate_summaries(library, summarizer)
    rebuilt = library.rebuild_index(require_summaries=True)
    print(json.dumps({"summary_model": OPENAI_SUMMARY_MODEL, **result, "index": rebuilt}, indent=2))


if __name__ == "__main__":
    main()
