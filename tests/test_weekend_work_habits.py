from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import quote, unquote

from migrate_weekend_work_habits import normalize_text, migrate

KEYS = ['phone_game_before_morning_work', 'phone_game_before_afternoon_work']

def habits(value):
    return '<!-- evening-habits: ' + quote(json.dumps(value, ensure_ascii=False), safe='') + ' -->'


class WeekendWorkHabitTests(unittest.TestCase):
    def test_only_weekend_work_flags_are_removed(self):
        value = {KEYS[0]: True, KEYS[1]: False, 'caffeine_last_intake': '17:00', 'custom': ['keep', 'café']}
        text = 'A reflection.\n\n' + habits(value) + '\n<!-- evening-jo: %7B%22jo%22%3Afalse%7D -->\n'
        for day in ['2026-11-07', '2026-11-08']:
            updated = normalize_text(text, day)
            payload = json.loads(unquote(updated.split('<!-- evening-habits: ')[1].split(' -->')[0]))
            self.assertEqual(payload, {'caffeine_last_intake': '17:00', 'custom': ['keep', 'café']})
            self.assertTrue(updated.startswith('A reflection.\n\n'))
            self.assertTrue(updated.endswith('\n<!-- evening-jo: %7B%22jo%22%3Afalse%7D -->\n'))
            self.assertEqual(normalize_text(updated, day), updated)
        # Weekday holidays still retain these work questions.
        for day in ['2026-11-06', '2026-11-09', '2026-11-11']:
            self.assertEqual(normalize_text(text, day), text)

    def test_empty_metadata_and_malformed_metadata(self):
        self.assertEqual(normalize_text(habits({KEYS[0]: False}), '2026-11-07'), '')
        untouched = habits({'caffeine_after_4pm': True})
        self.assertEqual(normalize_text(untouched, '2026-11-07'), untouched)
        with self.assertRaises(ValueError):
            normalize_text('<!-- evening-habits: invalid-json -->', '2026-11-07')

    def test_backup_and_weekday_and_morning_preservation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            vault, backup = root / 'vault', root / 'backup'
            journal = vault / 'Journal'
            journal.mkdir(parents=True)
            original = ('---\r\ncustom: keep\r\n---\r\n## Morning\r\nKeep morning.\r\n\r\n## Evening\r\nA reflection.\r\n' + habits({KEYS[0]: True, KEYS[1]: False, 'caffeine_last_intake': '16:00'}) + '\r\n').encode('utf-8')
            for day in ['2026-11-06', '2026-11-07', '2026-11-08']:
                (journal / (day + '.md')).write_bytes(original)
            self.assertEqual(migrate(vault, backup), 2)
            self.assertEqual((journal / '2026-11-06.md').read_bytes(), original)
            for day in ['2026-11-07', '2026-11-08']:
                self.assertEqual((backup / (day + '.md')).read_bytes(), original)
                updated = (journal / (day + '.md')).read_bytes()
                self.assertEqual(updated.split(b'## Evening')[0], original.split(b'## Evening')[0])
                self.assertNotIn(KEYS[0].encode(), unquote(updated.decode()).encode())
                self.assertIn(b'caffeine_last_intake', unquote(updated.decode()).encode())
            self.assertEqual(migrate(vault, root / 'second-backup'), 0)

    def test_older_clients_cannot_restore_weekend_flags(self):
        from journal import Journal
        with tempfile.TemporaryDirectory() as folder:
            journal = Journal(folder)
            for day in ['2026-11-06', '2026-11-07', '2026-11-08']:
                before = journal.read(day)
                saved = journal.save(day, 'evening', 'A reflection.\n' + habits({KEYS[0]: True, KEYS[1]: False}), before['revision'])
                has_flags = 'phone_game_before' in unquote(saved['sections']['evening'])
                self.assertEqual(has_flags, date.fromisoformat(day).weekday() < 5)
