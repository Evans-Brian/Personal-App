"""Run once to install free, local English dictation (no API key)."""
from pathlib import Path
import subprocess
import sys
root = Path(__file__).resolve().parent
runtime = root / 'data' / 'voice-runtime'
subprocess.run([sys.executable, '-m', 'pip', 'install', '--target', str(runtime), 'faster-whisper==1.2.1'], check=True)
sys.path.insert(0, str(runtime))
from huggingface_hub import snapshot_download
snapshot_download('Systran/faster-whisper-base.en', local_dir=root / 'data' / 'voice-model', allow_patterns=['model.bin', 'config.json', 'tokenizer.json', 'vocabulary.txt'])
print('Local dictation is ready. Restart the journal app.')
