import unittest

from migrate_day_satisfaction_scale import normalize_text


class DaySatisfactionMigrationTests(unittest.TestCase):
    def test_renames_normalizes_and_marks_old_scores(self):
        for old, new in [('1', '1'), ('2', '3'), ('3', '6'), ('4', '8'), ('5', '10')]:
            original = f'Good day: {old}\nProductive day: 8\nProductivity scale: 10\n'
            updated = normalize_text(original)
            self.assertIn(f'Day satisfaction: {new}\nDay satisfaction scale: 10\n', updated)
            self.assertNotIn('Good day:', updated)
            self.assertEqual(normalize_text(updated), updated)

    def test_marks_unrated_and_preserves_new_scores(self):
        self.assertIn('Day satisfaction: unrated\nDay satisfaction scale: 10\n', normalize_text('Good day: unrated\n'))
        self.assertIn('Day satisfaction: 9\nDay satisfaction scale: 10\n', normalize_text('Day satisfaction: 9\n'))

    def test_renames_already_scaled_legacy_label_without_remapping(self):
        original = 'Good day: 4\nDay satisfaction scale: 10\n'
        self.assertEqual(normalize_text(original), 'Day satisfaction: 4\nDay satisfaction scale: 10\n')

    def test_rejects_unknown_existing_scale(self):
        with self.assertRaises(ValueError):
            normalize_text('Day satisfaction: 4\nDay satisfaction scale: 7\n')


if __name__ == '__main__':
    unittest.main()
