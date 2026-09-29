import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from chapter_ai import AIServiceUnavailable, JevReranker, OpenAIChapterSummarizer
from embeddings import LocalBGEEmbedder
from setup_chapter_search import generate_summaries


class FakeLibrary:
    def __init__(self, root):
        self.summary_path = Path(root) / "chapter-summaries.json"
        self.content = "Control the knee line before exposing the heel."

    def chapter_sources(self):
        return [{"id": "course-v01:v1-1", "title": "Heel exposure", "content": self.content}]


class FakeSummarizer:
    model = "gpt-6-luna"

    def __init__(self):
        self.calls = []

    def summarize(self, title, transcript):
        self.calls.append((title, transcript))
        return "Control the knee line, then expose the heel."


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

    def test_summary_cache_is_restart_safe_and_invalidates_changed_transcript(self):
        with tempfile.TemporaryDirectory() as root:
            library = FakeLibrary(root)
            summarizer = FakeSummarizer()
            first = generate_summaries(library, summarizer, progress=lambda _: None)
            second = generate_summaries(library, summarizer, progress=lambda _: None)
            library.content += " Finish with controlled rotation."
            third = generate_summaries(library, summarizer, progress=lambda _: None)
            self.assertEqual((first["generated"], second["generated"], third["generated"]), (1, 0, 1))
            self.assertEqual(len(summarizer.calls), 2)

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

    @patch("chapter_ai._post_json")
    def test_openai_summary_uses_response_text(self, post):
        post.return_value = {"output": [{"type": "message", "content": [
            {"type": "output_text", "text": "A concise chapter summary."}
        ]}]}
        summarizer = OpenAIChapterSummarizer(api_key="test")
        self.assertEqual(summarizer.summarize("Title", "Transcript"), "A concise chapter summary.")
        payload = post.call_args.args[1]
        self.assertEqual(payload["model"], "gpt-6-luna")
        self.assertFalse(payload["store"])


if __name__ == "__main__":
    unittest.main()
