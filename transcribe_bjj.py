"""Resumable local BJJ transcription and indexing pipeline."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import wave
from datetime import datetime, timezone
from pathlib import Path

from bjj import BJJLibrary

PIPELINE_VERSION = 1
APP_ROOT = Path(__file__).resolve().parent
VOCABULARY = {
    "key guard": "K guard", "butter fly": "butterfly", "octopus card": "octopus guard",
    "kimora": "kimura", "under hook": "underhook", "over hook": "overhook",
}
DLL_HANDLES = []


def configure_gpu_runtime(root):
    if os.name != "nt":
        return
    base = Path(root) / "gpu-runtime" / "nvidia"
    directories = [base / "cublas" / "bin", base / "cudnn" / "bin", base / "cuda_nvrtc" / "bin"]
    existing = [str(path) for path in directories if path.is_dir()]
    if existing:
        os.environ["PATH"] = os.pathsep.join(existing + [os.environ.get("PATH", "")])
        DLL_HANDLES.extend(os.add_dll_directory(path) for path in existing)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def probe(path):
    command = ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,codec_name", "-of", "json", str(path)]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        data = json.loads(result.stdout)
    except FileNotFoundError:
        runtime = APP_ROOT / "data" / "voice-runtime"
        if runtime.is_dir() and str(runtime) not in sys.path:
            sys.path.insert(0, str(runtime))
        import av
        with av.open(str(path)) as container:
            streams = [{"codec_type": stream.type, "codec_name": stream.codec_context.name} for stream in container.streams]
            if container.duration is not None:
                duration = float(container.duration / av.time_base)
            else:
                durations = [float(stream.duration * stream.time_base) for stream in container.streams if stream.duration is not None and stream.time_base is not None]
                duration = max(durations, default=0.0)
        data = {"format": {"duration": duration}, "streams": streams}
    if not any(stream.get("codec_type") == "audio" for stream in data.get("streams", [])):
        raise ValueError(f"No audio stream: {path}")
    duration = float(data["format"]["duration"])
    if duration <= 0:
        raise ValueError(f"Invalid duration: {path}")
    return duration, data.get("streams", [])


def corrected(text):
    result = text.strip()
    for wrong, right in VOCABULARY.items():
        result = result.replace(wrong, right).replace(wrong.title(), right)
    return result


def timestamp(seconds):
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def write_text_atomic(path, text):
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def outputs(root, entry, segments):
    folder = root / "transcripts" / entry["course_id"]
    folder.mkdir(parents=True, exist_ok=True)
    stem = f"v{int(entry['volume']):02d}"
    payload = {"media_id": entry["id"], "pipeline_version": PIPELINE_VERSION,
               "transcription_complete": True, "segments": segments}
    write_text_atomic(folder / f"{stem}.segments.json", json.dumps(payload, indent=2, ensure_ascii=False))
    vtt = ["WEBVTT", ""]
    markdown = [f"# {entry.get('title', entry['course_id'])} — Volume {entry['volume']}", ""]
    for segment in segments:
        text = segment["corrected_text"]
        vtt.extend([str(segment["segment_id"] + 1), f"{timestamp(segment['start_seconds'])} --> {timestamp(segment['end_seconds'])}", text, ""])
        markdown.append(f"[{timestamp(segment['start_seconds'])}](bjj://{entry['id']}?t={segment['start_seconds']:.3f}) {text}")
    write_text_atomic(folder / f"{stem}.vtt", "\n".join(vtt))
    write_text_atomic(folder / f"{stem}.md", "\n\n".join(markdown) + "\n")


def transcript_output_complete(root, entry):
    relative = Path(entry.get("transcript", ""))
    if not relative or relative.is_absolute() or ".." in relative.parts:
        return False
    path = root / relative
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict) or data.get("media_id") != entry.get("id") or data.get("pipeline_version") != PIPELINE_VERSION:
        return False
    segments = data.get("segments")
    if not isinstance(segments, list) or not segments:
        return False
    previous_end = 0.0
    for segment in segments:
        try:
            start = float(segment["start_seconds"])
            end = float(segment["end_seconds"])
        except (KeyError, TypeError, ValueError):
            return False
        if start < previous_end - 0.01 or end <= start or "corrected_text" not in segment or "raw_text" not in segment:
            return False
        previous_end = end
    return data.get("transcription_complete") is True or previous_end >= float(entry.get("duration_seconds") or 0) - 1


def chapter_at(entry, seconds):
    current = None
    for chapter in entry.get("chapters", []):
        if float(chapter.get("start_seconds", 0)) > seconds:
            break
        current = chapter.get("id")
    return current


def normalize_segments(segments, duration):
    """Clamp unplayable audio tails and coalesce overly granular decoder output."""
    normalized = []
    for source in segments:
        if float(source["start_seconds"]) >= duration:
            break
        clean = dict(source)
        clean["end_seconds"] = min(float(clean["end_seconds"]), duration)
        if clean["end_seconds"] <= float(clean["start_seconds"]):
            continue
        previous = normalized[-1] if normalized else None
        previous_text = (previous or {}).get("corrected_text") or (previous or {}).get("raw_text") or ""
        can_merge = (previous and previous.get("chapter_id") == clean.get("chapter_id") and
                     float(clean["start_seconds"]) - float(previous["end_seconds"]) <= 0.05 and
                     float(previous["end_seconds"]) - float(previous["start_seconds"]) < 6 and
                     len(previous_text.split()) < 25 and
                     float(clean["end_seconds"]) - float(previous["start_seconds"]) <= 15)
        if can_merge:
            previous["end_seconds"] = clean["end_seconds"]
            for key in ("raw_text", "corrected_text"):
                previous[key] = " ".join(filter(None, (previous.get(key, "").strip(), clean.get(key, "").strip())))
        else:
            clean["segment_id"] = len(normalized)
            normalized.append(clean)
    return normalized


def extract_audio(media, audio):
    """Create the stable 16 kHz mono WAV used for restartable transcription."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        subprocess.run([ffmpeg, "-v", "error", "-i", str(media), "-vn", "-ac", "1", "-ar", "16000",
                        "-c:a", "pcm_s16le", str(audio)], check=True)
        return
    from faster_whisper.audio import decode_audio
    import numpy as np
    samples = np.clip(decode_audio(str(media), sampling_rate=16000), -1, 1)
    with wave.open(str(audio), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(16000)
        target.writeframes((samples * 32767).astype("<i2").tobytes())


def transcribe(root, media_id, model_name="large-v3-turbo", device="cuda", compute_type="float16"):
    configure_gpu_runtime(root)
    library = BJJLibrary(root, root / "unused-vault")
    entry, media = library.entry(media_id)
    media_hash = sha256(media)
    duration, _ = probe(media)
    work = root / "work" / media_id
    work.mkdir(parents=True, exist_ok=True)
    audio = work / "audio.wav"
    runtime = APP_ROOT / "data" / "voice-runtime"
    if runtime.is_dir() and str(runtime) not in sys.path:
        sys.path.insert(0, str(runtime))
    if not audio.exists():
        extract_audio(media, audio)
    progress = work / "segments.jsonl"
    completed = []
    if progress.exists():
        completed = [json.loads(line) for line in progress.read_text(encoding="utf-8").splitlines() if line.strip()]
    def validate():
        normalized = normalize_segments(completed, duration)
        changed = normalized != completed
        completed[:] = normalized
        if completed and any(a["end_seconds"] - b["start_seconds"] > 0.01 for a, b in zip(completed, completed[1:])):
            raise ValueError("Transcript timestamps are not monotonic or exceed media duration.")
        if changed:
            temporary = progress.with_suffix(".tmp")
            temporary.write_text("".join(json.dumps(segment, ensure_ascii=False) + "\n" for segment in completed), encoding="utf-8")
            temporary.replace(progress)
    if completed and completed[-1]["end_seconds"] >= duration - 1:
        validate()
        outputs(root, entry, completed)
        return len(completed)
    def run(active_device, active_compute):
        from faster_whisper import WhisperModel
        model = WhisperModel(model_name, device=active_device, compute_type=active_compute,
                             download_root=str(root / "models"))
        resume_at = completed[-1]["end_seconds"] if completed else 0.0
        stream, _ = model.transcribe(str(audio), language="en", vad_filter=True, word_timestamps=False,
                                     clip_timestamps=f"{resume_at}")
        with progress.open("a", encoding="utf-8") as target:
            for source in stream:
                raw = source.text.strip()
                segment = {"course_id": entry["course_id"], "volume": int(entry["volume"]), "segment_id": len(completed),
                           "start_seconds": float(source.start), "end_seconds": float(source.end), "raw_text": raw,
                           "corrected_text": corrected(raw), "chapter_id": chapter_at(entry, float(source.start)), "model": model_name,
                           "pipeline_version": PIPELINE_VERSION, "media_sha256": media_hash,
                           "transcript_created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat()}
                target.write(json.dumps(segment, ensure_ascii=False) + "\n")
                target.flush()
                completed.append(segment)
    try:
        run(device, compute_type)
    except RuntimeError as error:
        if device == "cpu" or not any(term in str(error).lower() for term in ("cuda", "cublas", "cudnn")):
            raise
        print(f"GPU runtime unavailable ({error}); resuming on CPU/int8.", file=sys.stderr)
        run("cpu", "int8")
    validate()
    outputs(root, entry, completed)
    return len(completed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--media-id")
    parser.add_argument("--all", action="store_true", help="Transcribe every manifest item sequentially, skipping completed JSON outputs.")
    parser.add_argument("--model", default="large-v3-turbo")
    parser.add_argument("--cpu", action="store_true")
    parser.add_argument("--index", action="store_true")
    args = parser.parse_args()
    if args.index:
        print(BJJLibrary(args.root, args.root / "unused-vault").rebuild_index())
    elif args.all:
        library = BJJLibrary(args.root, args.root / "unused-vault")
        for entry in library.manifest()["media"]:
            if transcript_output_complete(args.root, entry):
                print({"media_id": entry["id"], "status": "skipped", "reason": "complete"}, flush=True)
                continue
            count = transcribe(args.root, entry["id"], args.model, "cpu" if args.cpu else "cuda", "int8" if args.cpu else "float16")
            print({"media_id": entry["id"], "status": "complete", "segments": count}, flush=True)
    elif args.media_id:
        print({"segments": transcribe(args.root, args.media_id, args.model, "cpu" if args.cpu else "cuda", "int8" if args.cpu else "float16")})
    else:
        parser.error("Choose --media-id, --all, or --index")


if __name__ == "__main__":
    main()
