# BJJ implementation and operations

The application keeps source code in Git and all private/generated BJJ data under the ignored, absolute `bjj_library` directory configured in `config.local.json`. The Obsidian vault remains the canonical store for human-written notes.

## Data contract

`manifest.json` contains a `media` array. Each item has a stable ID (`<course-id>-v01` through `v04`), `course_id`, `volume`, root-relative `path`, `duration_seconds`, `sha256`, source message/date metadata, codec information, a transcript path, and official chapters with start seconds. Media routes accept only the stable ID and resolve it through this manifest.

Canonical transcript JSON contains `segments`. Every segment records `course_id`, `volume`, `segment_id`, absolute start/end seconds, raw and corrected text, chapter ID, model, pipeline version, media SHA-256, and creation time. Raw recognition is retained when vocabulary corrections are applied.

## Operations

1. Download one Telegram file at a time into the matching `<BJJLibrary>\media\<course-id>` folder and normalize its filename without transcoding.
2. Use `ffprobe` and SHA-256 to populate and validate the manifest. Keep the corrected January 4 Octopus Guard files.
3. Pilot transcription:

   `python transcribe_bjj.py --root "C:\path\to\your\BJJLibrary" --media-id octopus-guard-2-v01`

4. Review the pilot at its beginning, middle, and end; finalize vocabulary and official chapter starts in the manifest.
5. Run the remaining media IDs sequentially with `python transcribe_bjj.py --root "C:\path\to\your\BJJLibrary" --all`. The JSONL work file is appended segment by segment and a retry resumes after the last completed timestamp. Add `--cpu` for the clean int8 fallback.
6. Install the local BGE runtime/model and rebuild the idempotent transcript-and-journal index:

   `python setup_embeddings.py --bjj-library "C:\path\to\your\BJJLibrary" --vault "C:\path\to\your\ObsidianVault"`

   Later transcript-only pipeline runs may still invoke `python transcribe_bjj.py --root "C:\path\to\your\BJJLibrary" --index`; the local embedding setup must already be present and the configured vault should be used when journals also need rebuilding.

7. Start the journal normally. `/api/bjj/media/<media-id>` supports private same-origin byte ranges; BJJ notes are Markdown under `BJJ/Study Notes` and daily training entries under `BJJ/Journal` in the configured vault.

On Windows, optional private wheels `nvidia-cublas-cu12` and `nvidia-cudnn-cu12` may be installed under the library's `gpu-runtime` folder. The pipeline discovers their DLL folders automatically; no model or runtime files belong in Git. Set the absolute `bjj_library` path in the ignored `config.local.json`.

## Private-data gate

Before every commit, inspect `git diff --cached --name-only` and reject media, transcripts, subtitle files, model weights, SQLite/index files, work state, logs, vault notes, credentials, or `config.local.json`. Only source, tests, and documentation belong in Git.
