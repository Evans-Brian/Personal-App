import importlib.util
import unittest
from pathlib import Path


spec = importlib.util.spec_from_file_location(
    "check_repo_secrets", Path(__file__).parents[1] / "scripts" / "check_repo_secrets.py"
)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class SecretGateTests(unittest.TestCase):
    def test_private_paths_are_blocked(self):
        for path in ("config.local.json", ".env", "data/bjj.sqlite3",
                     "BJJ-Library/work/chapter-summaries.json", "vault/Journal/entry.md",
                     "media/video.mp4", "ai-secrets.bin"):
            with self.subTest(path=path):
                self.assertTrue(gate.private_path(path))
        self.assertFalse(gate.private_path("static/bjj.js"))

    def test_recognizable_tokens_are_blocked(self):
        self.assertIsNotNone(gate.SECRET_PATTERNS["API token"].search(b"sk-" + b"x" * 40))
        self.assertIsNotNone(gate.SECRET_PATTERNS["API token"].search(b"typesafe_" + b"x" * 40))
        self.assertIsNotNone(gate.SECRET_PATTERNS["credential assignment"].search(
            b"service_api_key = '" + b"x" * 40 + b"'"
        ))


if __name__ == "__main__":
    unittest.main()
