import json
from pathlib import Path
import tempfile
import unittest

from migrate_evening_prompts import normalize_text, migrate

FIXTURES = json.loads((Path(__file__).parent / 'fixtures/evening_prompt_merge.json').read_text(encoding='utf-8'))


class EveningPromptMigrationTests(unittest.TestCase):
    def test_merge_and_idempotence(self):
        for case in FIXTURES:
            with self.subTest(case=case['name']):
                updated = normalize_text(case['before'])
                self.assertEqual(updated, case['after'])
                self.assertEqual(normalize_text(updated), updated)

    def test_backup_original_bytes_and_only_change_evening(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            vault, backup = root / 'vault', root / 'backup'
            journal = vault / 'Journal'
            journal.mkdir(parents=True)
            morning = '---\ncustom: keep\n---\n\n# A day\n\n## Morning\n\n### What moment would I like to remember?\n\nKeep morning exactly.\n\n'
            suffix = '## A separate section\n\nDo not edit.\n'
            original = (morning + '## Evening\n\n' + FIXTURES[0]['before'] + suffix).encode('utf-8')
            path = journal / '2026-10-01.md'
            path.write_bytes(original)
            untouched = journal / '2026-10-02.md'
            untouched.write_bytes(b'## Morning\n\nOnly morning.\n')
            self.assertEqual(migrate(vault, backup), 1)
            self.assertEqual((backup / path.name).read_bytes(), original)
            self.assertEqual(path.read_bytes(), (morning + '## Evening\n\n' + FIXTURES[0]['after'] + suffix).encode('utf-8'))
            self.assertEqual(untouched.read_bytes(), b'## Morning\n\nOnly morning.\n')
            self.assertEqual(migrate(vault, root / 'second-backup'), 0)

    def test_old_client_saves_cannot_reintroduce_retired_questions(self):
        from journal import Journal
        with tempfile.TemporaryDirectory() as folder:
            journal = Journal(folder)
            current = journal.read('2026-10-01')
            saved = journal.save(current['date'], 'evening', FIXTURES[0]['before'], current['revision'])
            self.assertEqual(saved['sections']['evening'].strip(), FIXTURES[0]['after'].strip())

    def test_existing_backup_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            vault, backup = root / 'vault', root / 'backup'
            (vault / 'Journal').mkdir(parents=True)
            path = vault / 'Journal/2026-10-01.md'
            original = ('## Evening\n' + FIXTURES[0]['before']).encode('utf-8')
            path.write_bytes(original)
            backup.mkdir()
            (backup / path.name).write_bytes(b'An earlier backup.')
            with self.assertRaises(FileExistsError):
                migrate(vault, backup)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual((backup / path.name).read_bytes(), b'An earlier backup.')


if __name__ == '__main__':
    unittest.main()
