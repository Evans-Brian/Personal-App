"""Private, restart-safe chapter summary cache helpers."""
from __future__ import annotations

import json
import os
import tempfile


def load(path):
    if not path.is_file():
        return {"version": 1, "summaries": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("summaries"), dict):
        raise ValueError("The chapter summary cache is invalid.")
    return data


def atomic_write(path, data):
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
