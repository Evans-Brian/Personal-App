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
EXPECTED_MEDIA_COUNT = 12
DURATION_TOLERANCE_SECONDS = 2.0


def stream_codecs(streams, codec_type):
    return sorted(stream.get("codec_name", "") for stream in streams if stream.get("codec_type") == codec_type)


def build(root):
    root = Path(root).resolve()
    manifest_path = root / "manifest.json"
    items, missing, duration_mismatches, codec_mismatches = [], [], [], []
    for course in COURSES:
        source = EXPECTED[course["id"]]
        for volume in range(1, 5):
            media_id = f"{course['id']}-v{volume:02d}"
            path = root / "media" / course["id"] / f"{media_id}.mp4"
            if not path.is_file():
                missing.append(media_id); continue
            duration, streams = probe(path)
            reference = source["references"][volume - 1]
            if abs(duration - reference) > DURATION_TOLERANCE_SECONDS:
                duration_mismatches.append({"id": media_id, "duration": duration, "reference": reference})
            video_codecs = stream_codecs(streams, "video")
            audio_codecs = stream_codecs(streams, "audio")
            if not video_codecs or not audio_codecs:
                codec_mismatches.append({"id": media_id, "video": video_codecs, "audio": audio_codecs})
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
    errors = {}
    if missing:
        errors["missing"] = missing
    if len(items) != EXPECTED_MEDIA_COUNT:
        errors["count"] = {"expected": EXPECTED_MEDIA_COUNT, "actual": len(items)}
    if duration_mismatches:
        errors["duration_mismatches"] = duration_mismatches
    if codec_mismatches:
        errors["codec_mismatches"] = codec_mismatches
    if duplicates:
        errors["duplicate_hashes"] = duplicates
    if errors:
        raise ValueError(json.dumps(errors, indent=2, ensure_ascii=False))
    result = {"version": 1, "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), "media": items}
    temporary = manifest_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(manifest_path)
    return {"valid": len(items), "missing": missing, "duplicates": duplicates, "manifest": str(manifest_path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.root), indent=2))


if __name__ == "__main__":
    main()
