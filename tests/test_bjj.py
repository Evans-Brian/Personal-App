import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from app import make_server
from bjj import BJJLibrary
from official_chapters import chapters
from transcribe_bjj import chapter_at, normalize_segments


class BJJTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.root, self.vault = base / "library", base / "vault"
        media = self.root / "media" / "octopus-guard-2"
        transcript = self.root / "transcripts" / "octopus-guard-2"
        media.mkdir(parents=True); transcript.mkdir(parents=True); self.vault.mkdir()
        (media / "octopus-guard-2-v01.mp4").write_bytes(b"0123456789")
        self.entry = {"id": "octopus-guard-2-v01", "course_id": "octopus-guard-2", "volume": 1,
                      "path": "media/octopus-guard-2/octopus-guard-2-v01.mp4", "duration_seconds": 10,
                      "sha256": "abc", "transcript": "transcripts/octopus-guard-2/v01.segments.json",
                      "chapters": [{"id": "intro", "title": "Introduction", "start_seconds": 0}]}
        (self.root / "manifest.json").write_text(json.dumps({"version": 1, "media": [self.entry]}), encoding="utf-8")
        segments = {"segments": [{"segment_id": 0, "start_seconds": 0, "end_seconds": 3,
                                   "raw_text": "Use the under hook from octopus guard.",
                                   "corrected_text": "Use the underhook from octopus guard.", "chapter_id": "intro"}]}
        (transcript / "v01.segments.json").write_text(json.dumps(segments), encoding="utf-8")
        self.library = BJJLibrary(self.root, self.vault)

    def tearDown(self):
        self.temporary.cleanup()

    def test_library_index_search_and_idempotency(self):
        self.assertEqual(self.library.library()["courses"][1]["volumes"][0]["id"], "octopus-guard-2-v01")
        self.assertEqual(self.library.rebuild_index()["chunks"], 1)
        self.assertEqual(self.library.rebuild_index()["chunks"], 1)
        exact = self.library.search("underhook")
        self.assertEqual(exact[0]["media_id"], "octopus-guard-2-v01")
        self.assertEqual(self.library.search("octopus position", semantic=True)[0]["start_seconds"], 0)

    def test_manifest_cannot_escape_media_root(self):
        self.entry["path"] = "../secret.mp4"
        (self.root / "manifest.json").write_text(json.dumps({"media": [self.entry]}), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.library.entry("octopus-guard-2-v01")

    def test_notes_and_training_are_markdown_in_vault(self):
        note = self.library.save_note({"media_id": "octopus-guard-2-v01", "timestamp": 2.5, "excerpt": "underhook",
                                       "text": "Keep my elbow close.", "tags": ["guard"]})
        self.assertIn("bjj://octopus-guard-2-v01?t=2.500", (self.vault / note["path"]).read_text(encoding="utf-8"))
        self.assertEqual(self.library.notes()[0]["timestamp"], 2.5)
        journal = self.library.save_training({"date": "2026-09-28", "techniques": "Octopus entry", "next_focus": "Hip position"})
        self.assertIn("Octopus entry", (self.vault / journal["path"]).read_text(encoding="utf-8"))
        loaded = self.library.training("2026-09-28")
        self.assertEqual((loaded["techniques"], loaded["next_focus"]), ("Octopus entry", "Hip position"))

    def test_http_range_and_security(self):
        database = Path(self.temporary.name) / "oura.sqlite3"
        server = make_server(self.vault, database, 0, bjj_root=self.root)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            def get(path, headers=None):
                connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
                connection.request("GET", path, headers={"Host": f"127.0.0.1:{server.server_port}", **(headers or {})})
                response = connection.getresponse(); body = response.read(); values = dict(response.getheaders()); connection.close()
                return response.status, body, values
            status, body, headers = get("/api/bjj/media/octopus-guard-2-v01", {"Range": "bytes=2-5"})
            self.assertEqual((status, body, headers["Content-Range"]), (206, b"2345", "bytes 2-5/10"))
            self.assertEqual(get("/api/bjj/media/octopus-guard-2-v01", {"Range": "bytes=50-60"})[0], 416)
            self.assertEqual(get("/api/bjj/media/../../config.local.json")[0], 404)
            self.assertEqual(get("/api/bjj/library", {"Host": "evil.example"})[0], 403)
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_official_chapter_mapping(self):
        mapped = {**self.entry, "chapters": chapters("octopus-guard-2", 1)}
        self.assertEqual(chapter_at(mapped, 0), "v1-1")
        self.assertEqual(chapter_at(mapped, 700), "v1-3")

    def test_transcript_normalization_clamps_and_coalesces(self):
        segments = [
            {"segment_id": 0, "start_seconds": 8, "end_seconds": 9, "raw_text": "Keep", "corrected_text": "Keep", "chapter_id": "one"},
            {"segment_id": 1, "start_seconds": 9, "end_seconds": 12, "raw_text": "moving", "corrected_text": "moving", "chapter_id": "one"},
        ]
        result = normalize_segments(segments, 10)
        self.assertEqual((len(result), result[0]["corrected_text"], result[0]["end_seconds"]), (1, "Keep moving", 10))


if __name__ == "__main__":
    unittest.main()
