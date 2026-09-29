import http.client
import json
import tempfile
import threading
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import prepare_bjj
from app import make_server
from bjj import BJJLibrary
from official_chapters import chapters
from transcribe_bjj import chapter_at, normalize_segments, outputs, transcript_output_complete


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
        journal = self.library.save_training({"date": "2026-09-28", "general_notes": "Octopus entry", "session_goals": "Hip position", "rating": "4"})
        self.assertIn("Octopus entry", (self.vault / journal["path"]).read_text(encoding="utf-8"))
        loaded = self.library.training("2026-09-28")
        self.assertEqual((loaded["general_notes"], loaded["session_goals"], loaded["rating"]), ("Octopus entry", "Hip position", "4"))

    def test_training_rating_validation(self):
        with self.assertRaisesRegex(ValueError, "from 1 to 5"):
            self.library.save_training({"date": "2026-09-28", "rating": "6"})

    def test_legacy_training_fields_are_preserved_when_loaded(self):
        folder = self.vault / "BJJ" / "Journal"
        folder.mkdir(parents=True)
        (folder / "2026-09-27.md").write_text(
            "# BJJ training\n\n## Techniques studied\n\nK guard\n\n## Drills\n\nEntries\n\n"
            "## What worked\n\nTiming\n\n## Problems encountered\n\nPosture\n\n## Next practice focus\n\nFrames\n",
            encoding="utf-8",
        )
        loaded = self.library.training("2026-09-27")
        self.assertIn("K guard", loaded["general_notes"])
        self.assertIn("Entries", loaded["general_notes"])
        self.assertEqual(loaded["session_goals"], "Frames")
        self.assertEqual((loaded["problems"], loaded["worked"]), ("Posture", "Timing"))

    def test_training_save_preserves_unmanaged_markdown(self):
        folder = self.vault / "BJJ" / "Journal"
        folder.mkdir(parents=True)
        path = folder / "2026-09-28.md"
        path.write_text(
            "---\ncustom: keep\n---\n\n# Existing title\n\nIntro stays.\n\n"
            "## General Notes\n\nOld notes\n\n## Private review\n\nDo not overwrite\n",
            encoding="utf-8",
        )
        self.library.save_training({"date": "2026-09-28", "general_notes": "New notes", "session_goals": "Frames"})
        text = path.read_text(encoding="utf-8")
        self.assertIn("custom: keep", text)
        self.assertIn("Intro stays.", text)
        self.assertIn("## Private review\n\nDo not overwrite", text)
        self.assertIn("## General Notes\n\nNew notes", text)
        self.assertIn("## Session Goals\n\nFrames", text)
        self.assertNotIn("Old notes", text)

    def test_study_notes_do_not_collide_with_same_clock_tick(self):
        class FixedDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 9, 28, 12, 0, 0, 123456, tzinfo=tz)

        with patch("bjj.datetime", FixedDatetime):
            first = self.library.save_note({"media_id": "octopus-guard-2-v01", "timestamp": 2.5, "text": "First"})
            second = self.library.save_note({"media_id": "octopus-guard-2-v01", "timestamp": 2.5, "text": "Second"})
        self.assertNotEqual(first["path"], second["path"])
        self.assertTrue((self.vault / first["path"]).is_file())
        self.assertTrue((self.vault / second["path"]).is_file())

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

    def test_prepare_manifest_rejects_failed_media_verification(self):
        root = Path(self.temporary.name) / "prepare"
        for course in prepare_bjj.COURSES:
            folder = root / "media" / course["id"]
            folder.mkdir(parents=True)
            for volume in range(1, 5):
                media_id = f"{course['id']}-v{volume:02d}"
                (folder / f"{media_id}.mp4").write_bytes(media_id.encode("utf-8"))

        def fake_probe(path):
            course_id = path.parent.name
            volume = int(path.stem.rsplit("-v", 1)[1])
            return prepare_bjj.EXPECTED[course_id]["references"][volume - 1] + 10, [{"codec_type": "audio", "codec_name": "aac"}]

        with patch("prepare_bjj.probe", side_effect=fake_probe), patch("prepare_bjj.sha256", side_effect=lambda path: path.stem):
            with self.assertRaisesRegex(ValueError, "duration_mismatches"):
                prepare_bjj.build(root)
        self.assertFalse((root / "manifest.json").exists())

    def test_transcript_completion_rejects_partial_or_corrupt_output(self):
        output = self.root / self.entry["transcript"]
        output.write_text("{", encoding="utf-8")
        self.assertFalse(transcript_output_complete(self.root, self.entry))
        output.write_text(json.dumps({"media_id": self.entry["id"], "pipeline_version": 1,
                                      "segments": [{"segment_id": 0, "start_seconds": 0, "end_seconds": 5,
                                                    "raw_text": "half", "corrected_text": "half"}]}), encoding="utf-8")
        self.assertFalse(transcript_output_complete(self.root, self.entry))
        outputs(self.root, self.entry, [{"segment_id": 0, "start_seconds": 0, "end_seconds": 10,
                                         "raw_text": "done", "corrected_text": "done"}])
        self.assertTrue(transcript_output_complete(self.root, self.entry))


if __name__ == "__main__":
    unittest.main()
