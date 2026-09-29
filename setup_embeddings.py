"""Install and cache the private, local BGE embedding runtime."""
from pathlib import Path
import argparse
import json
import subprocess
import sys

from embeddings import MODEL_NAME, MODEL_ROOT, RUNTIME_ROOT


ROOT = Path(__file__).resolve().parent


def configured_paths():
    config_path = ROOT / "config.local.json"
    config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.is_file() else {}
    return Path(config.get("bjj_library", ROOT / "data" / "bjj-library")), Path(config.get("vault", ROOT / "demo-vault"))


def install_embeddings():
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    MODEL_ROOT.mkdir(parents=True, exist_ok=True)
    if not (RUNTIME_ROOT / "fastembed").is_dir():
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--target", str(RUNTIME_ROOT), "fastembed>=0.7,<1"],
            check=True,
        )
    sys.path.insert(0, str(RUNTIME_ROOT))
    from fastembed import TextEmbedding

    model = TextEmbedding(model_name=MODEL_NAME, cache_dir=str(MODEL_ROOT))
    vector = list(next(iter(model.query_embed("half guard underhook"))))
    if len(vector) != 384:
        raise RuntimeError(f"Expected a 384-dimensional embedding, received {len(vector)}.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bjj-library", type=Path)
    parser.add_argument("--vault", type=Path)
    args = parser.parse_args()
    install_embeddings()

    from bjj import BJJLibrary
    configured_bjj, configured_vault = configured_paths()
    bjj_root, vault = args.bjj_library or configured_bjj, args.vault or configured_vault
    if not bjj_root.is_dir() or not vault.is_dir():
        raise SystemExit("The BJJ library and vault folders must exist. Pass --bjj-library and --vault explicitly.")
    result = BJJLibrary(bjj_root, vault).rebuild_index()
    print(f"Local embeddings are ready: {MODEL_NAME}")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
