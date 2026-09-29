"""Local text embeddings with an explicit, testable model boundary."""
from __future__ import annotations

import hashlib
import math
import sys
import threading
from array import array
from pathlib import Path


MODEL_NAME = "BAAI/bge-small-en-v1.5"
MODEL_VERSION = "bge-small-en-v1.5-fastembed-v2"
MODEL_DIMENSIONS = 384
APP_ROOT = Path(__file__).resolve().parent
RUNTIME_ROOT = APP_ROOT / "data" / "embedding-runtime"
MODEL_ROOT = APP_ROOT / "data" / "embedding-models"


class EmbeddingUnavailable(RuntimeError):
    pass


def vector_to_blob(values):
    vector = array("f", (float(value) for value in values))
    if sys.byteorder != "little":
        vector.byteswap()
    return vector.tobytes()


def blob_to_vector(value):
    if not isinstance(value, (bytes, bytearray, memoryview)):
        return []
    vector = array("f")
    vector.frombytes(bytes(value))
    if sys.byteorder != "little":
        vector.byteswap()
    return list(vector)


class LocalBGEEmbedder:
    """Lazy, offline-only BGE inference through FastEmbed/ONNX."""

    model_name = MODEL_NAME
    version = MODEL_VERSION
    dimensions = MODEL_DIMENSIONS

    def __init__(self, runtime_root=RUNTIME_ROOT, model_root=MODEL_ROOT):
        self.runtime_root = Path(runtime_root)
        self.model_root = Path(model_root)
        self._model = None
        self._lock = threading.RLock()

    @property
    def installed(self):
        return self.runtime_root.is_dir() and self.model_root.is_dir()

    def _load(self):
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is not None:
                return self._model
            if not self.installed:
                raise EmbeddingUnavailable(
                    "Related-ideas search needs the local embedding model. Run `python setup_embeddings.py`, then rebuild the index."
                )
            runtime = str(self.runtime_root)
            if runtime not in sys.path:
                sys.path.insert(0, runtime)
            try:
                from fastembed import TextEmbedding
                self._model = TextEmbedding(
                    model_name=self.model_name,
                    cache_dir=str(self.model_root),
                    local_files_only=True,
                    lazy_load=False,
                )
            except Exception as exc:
                raise EmbeddingUnavailable(
                    "The local embedding model could not be loaded. Run `python setup_embeddings.py` again."
                ) from exc
        return self._model

    def embed_documents(self, texts):
        texts = [str(text) for text in texts]
        if not texts:
            return []
        with self._lock:
            return [list(vector) for vector in self._load().embed(texts, batch_size=32)]

    def embed_query(self, text):
        with self._lock:
            model = self._load()
            instruction = "Represent this sentence for searching relevant passages: "
            return list(next(iter(model.embed([instruction + str(text)]))))


class HashEmbedder:
    """Legacy baseline retained only for tests and retrieval evaluations."""

    model_name = "signed-feature-hash"
    version = "hash-v1"
    dimensions = 192
    installed = True

    @staticmethod
    def _words(text):
        import re
        return re.findall(r"[a-z0-9][a-z0-9'_-]*", (text or "").lower(), re.I)

    def _embed(self, text):
        vector = [0.0] * self.dimensions
        words = self._words(text)
        features = words + [" ".join(words[index:index + 2]) for index in range(max(0, len(words) - 1))]
        for token in features:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            number = int.from_bytes(digest, "little")
            vector[number % self.dimensions] += -1.0 if number & 1 else 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    def embed_documents(self, texts):
        return [self._embed(text) for text in texts]

    def embed_query(self, text):
        return self._embed(text)
