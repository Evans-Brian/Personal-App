"""Block private BJJ data and recognizable credentials from Git commits.

Run with --index before committing or --commit SHA from the pre-push hook.
Only filenames and finding categories are printed, never matching content.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from pathlib import PurePosixPath


PRIVATE_NAMES = {"config.local.json", "private_context.md"}
PRIVATE_DIRECTORIES = {
    "bjj-library", "media", "transcripts", "index", "work", "models",
    "journal", "people", "restaurants", "tasks", "backups", "demo-vault", "data",
}
PRIVATE_SUFFIXES = (
    ".bin", ".db", ".db-wal", ".db-shm", ".sqlite", ".sqlite3",
    ".jsonl", ".vtt", ".segments.json", ".onnx", ".safetensors",
    ".mp4", ".mkv", ".mov", ".webm", ".wav", ".mp3",
)
SECRET_PATTERNS = {
    "API token": re.compile(
        rb"\bsk-[A-Za-z0-9_-]{20,}\b|\b(?:typesafe|jev|ts)[_-][A-Za-z0-9_-]{24,}\b|"
        rb"\bgithub_pat_[A-Za-z0-9_]{20,}\b|\bgh[pousr]_[A-Za-z0-9]{30,}\b"
    ),
    "private key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "credential assignment": re.compile(
        rb"(?i)\b[a-z][a-z0-9_]*_api_key\b\s*[=:]\s*['\"]?[A-Za-z0-9_./+-]{20,}"
    ),
}


def git(*args):
    return subprocess.run(["git", *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def private_path(name):
    path = PurePosixPath(name)
    lowered = [part.lower() for part in path.parts]
    base = lowered[-1]
    return (
        base in PRIVATE_NAMES
        or base == ".env" or base.startswith(".env.")
        or any(part in PRIVATE_DIRECTORIES for part in lowered[:-1])
        or base.endswith(PRIVATE_SUFFIXES)
    )


def scan(revision):
    if revision == "working-tree":
        paths = git("ls-files", "-z", "--cached", "--others", "--exclude-standard").split(b"\0")
    elif revision is None:
        paths = git("ls-files", "-z", "--cached").split(b"\0")
    else:
        paths = git("ls-tree", "-r", "-z", "--name-only", revision).split(b"\0")
    findings = []
    for raw_path in paths:
        if not raw_path:
            continue
        path = raw_path.decode("utf-8", errors="replace")
        if private_path(path):
            findings.append((path, "private-data path"))
            continue
        if revision == "working-tree":
            if not Path(path).is_file():
                continue
            blob = Path(path).read_bytes()
        else:
            blob = git("show", f":{path}" if revision is None else f"{revision}:{path}")
        for category, pattern in SECRET_PATTERNS.items():
            if pattern.search(blob):
                findings.append((path, category))
    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--index", action="store_true")
    group.add_argument("--working-tree", action="store_true")
    group.add_argument("--commit")
    args = parser.parse_args()
    try:
        findings = scan("working-tree" if args.working_tree else None if args.index else args.commit)
    except subprocess.CalledProcessError as error:
        print(f"Secret gate could not inspect Git objects (exit {error.returncode}).", file=sys.stderr)
        return 2
    for path, category in findings:
        print(f"Blocked {path}: {category}.", file=sys.stderr)
    if findings:
        return 1
    print("Secret gate passed: no private paths or recognizable credentials in checked files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
