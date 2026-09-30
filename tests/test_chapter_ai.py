import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from chapter_ai import (AIServiceUnavailable, CODEX_PROMPT_VERSION, CODEX_SUMMARY_MODEL,
                        JevReranker)
from chapter_cache import atomic_write, load
from embeddings import LocalBGEEmbedder
from summarize_with_codex import pending_chapters


class FakeLibrary:
    def __init__(self, root):
        self.summary_path = Path(root) / "chapter-summaries.json"
        self.content = "Control the knee line before exposing the heel."

    def chapter_sources(self):
        return [{"id": "course-v01:v1-1", "title": "Heel exposure",
                 "instructor": "Test instructor", "content": self.content}]


class ChapterAITests(unittest.TestCase):
    def test_chapter_embedding_mean_pools_and_normalizes_all_parts(self):
        class FakeModel:
            def embed(self, texts, batch_size=32):
                vectors = {"first": [1.0, 0.0], "second": [0.0, 1.0], "only": [0.0, 2.0]}
                return [vectors[text] for text in texts]

        class TwoDimensionalEmbedder(LocalBGEEmbedder):
            dimensions = 2

        embedder = TwoDimensionalEmbedder()
        embedder._model = FakeModel()
        vectors = embedder.embed_document_parts([["first", "second"], ["only"]])
        self.assertAlmostEqual(vectors[0][0], 2 ** -0.5)
        self.assertAlmostEqual(vectors[0][1], 2 ** -0.5)
        self.assertEqual(vectors[1], [0.0, 1.0])

    def test_bge_query_uses_query_embedding_path(self):
        class FakeModel:
            def query_embed(self, text):
                self.text = text
                return [[0.25, 0.75]]

        class TwoDimensionalEmbedder(LocalBGEEmbedder):
            dimensions = 2

        embedder = TwoDimensionalEmbedder()
        embedder._model = FakeModel()
        self.assertEqual(embedder.embed_query("half guard"), [0.25, 0.75])
        self.assertEqual(embedder._model.text, "half guard")

    def test_summary_cache_is_restart_safe_and_invalidates_changed_transcript(self):
        with tempfile.TemporaryDirectory() as root:
            library = FakeLibrary(root)
            cache = load(library.summary_path)
            self.assertEqual(len(pending_chapters(library, cache)), 1)
            cache["summaries"]["course-v01:v1-1"] = {
                "source_sha256": sha256(library.content.encode()).hexdigest(),
                "model": CODEX_SUMMARY_MODEL,
                "prompt_version": CODEX_PROMPT_VERSION,
                "summary": "Control the knee line, then expose the heel.",
            }
            atomic_write(library.summary_path, cache)
            restored = load(library.summary_path)
            self.assertEqual(len(pending_chapters(library, restored)), 0)
            library.content += " Finish with controlled rotation."
            self.assertEqual(len(pending_chapters(library, restored)), 1)

    @patch("chapter_ai._post_json")
    def test_jev_ranks_only_fifteen_candidates(self, post):
        post.side_effect = lambda _url, payload, _key, **_kwargs: {
            "answers": {"relevant": {"noul": float(payload["state"]["candidate"]["title"].split()[-1])}}
        }
        reranker = JevReranker(api_key="test", workers=1)
        candidates = [{"title": f"Chapter {index}", "_content": "guard details"} for index in range(20)]
        ranked = reranker.rank("guard", candidates)
        self.assertEqual(len(post.call_args_list), 15)
        self.assertEqual(len(ranked), 15)
        self.assertEqual(ranked[0]["title"], "Chapter 14")

    def test_jev_rejects_oversized_state_before_network(self):
        reranker = JevReranker(api_key="test", workers=1)
        with self.assertRaisesRegex(AIServiceUnavailable, "context budget"):
            reranker.rank("guard", [{"title": "Long", "_content": "x" * 31_000}])

if __name__ == "__main__":
    unittest.main()
