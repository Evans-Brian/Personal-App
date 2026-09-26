"""Local-only audio transcription. Audio stays in memory, not on disk."""
import io
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_lock = threading.Lock()
_model = None
MAX_BYTES = 12 * 1024 * 1024


def transcribe(audio):
    global _model
    if not audio or len(audio) > MAX_BYTES:
        raise ValueError('Record between a moment and two minutes of audio.')
    if not _lock.acquire(blocking=False):
        raise ValueError('Another recording is being transcribed. Try again in a moment.')
    try:
        runtime = str(ROOT / 'data' / 'voice-runtime')
        if runtime not in sys.path:
            sys.path.insert(0, runtime)
        from faster_whisper import WhisperModel
        from faster_whisper.audio import decode_audio
        if _model is None:
            _model = WhisperModel(str(ROOT / 'data' / 'voice-model'), device='cpu', compute_type='int8', cpu_threads=4, local_files_only=True)
        waveform = decode_audio(io.BytesIO(audio), sampling_rate=16000)
        if len(waveform) > 125 * 16000:
            raise ValueError('Please keep recordings under two minutes.')
        segments, _ = _model.transcribe(waveform, language='en', beam_size=3, vad_filter=True, condition_on_previous_text=False)
        return ' '.join(segment.text.strip() for segment in segments).strip()
    finally:
        _lock.release()
