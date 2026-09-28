"""Validate normalized BJJ media and create/update its private manifest."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from bjj import COURSES
from transcribe_bjj import probe, sha256
from official_chapters import chapters

EXPECTED = {
    "down-right-sloppy-half-butterfly": {"date": "2024-12-25", "messages": [313, 314, 315, 316], "references": [1880, 2094, 1525, 1723]},
    "octopus-guard-2": {"date": "2026-01-04", "messages": [395, 396, 397, 398], "references": [2351, 2652, 2337, 2502]},
    "shotgun-k-guard": {"date": "2026-08-11", "messages": [430, 431, 432, 433], "references": [4056, 3498, 3423, 2002]},
}


def build(root):
    root = Path(root).resolve()
    manifest_path = root / "manifest.json"
    previous = {}
    if manifest_path.exists():
        previous = {item["id"]: item for item in json.loads(manifest_path.read_text(encoding="utf-8")).get("media", [])}
    items, missing = [], []
    for course in COURSES:
        source = EXPECTED[course["id"]]
        for volume in range(1, 5):
            media_id = f"{course['id']}-v{volume:02d}"
            path = root / "media" / course["id"] / f"{media_id}.mp4"
            if not path.is_file():
                missing.append(media_id); continue
            duration, streams = probe(path)
            old = previous.get(media_id, {})
            item = {
                "id": media_id, "course_id": course["id"], "title": course["title"], "instructor": course["instructor"],
                "volume": volume, "source": "Telegram / Blind Viewer", "source_date": source["date"],
                "source_message": source["messages"][volume - 1], "path": str(path.relative_to(root)).replace("\\", "/"),
                "byte_size": path.stat().st_size, "duration_seconds": duration,
                "duration_reference_seconds": source["references"][volume - 1], "streams": streams, "sha256": sha256(path),
                "transcript": f"transcripts/{course['id']}/v{volume:02d}.segments.json", "chapters": chapters(course["id"], volume),
            }
            items.append(item)
    hashes = {}
    for item in items:
        hashes.setdefault(item["sha256"], []).append(item["id"])
    duplicates = [ids for ids in hashes.values() if len(ids) > 1]
    if duplicates:
        raise ValueError(f"Duplicate media hashes: {duplicates}")
    result = {"version": 1, "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), "media": items}
    manifest_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"valid": len(items), "missing": missing, "duplicates": duplicates, "manifest": str(manifest_path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.root), indent=2))


if __name__ == "__main__":
    main()
