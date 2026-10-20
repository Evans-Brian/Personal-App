import unittest

from migrate_productivity_scale import normalize_text


class ProductivityMigrationTests(unittest.TestCase):
    def test_normalizes_old_scores_and_marks_scale(self):
        for old, new in [('1', '1'), ('2', '3'), ('3', '6'), ('4', '8'), ('5', '10')]:
            original = f'Good day: 4\nProductive day: {old}\n\n### Reflection\n'
            updated = normalize_text(original)
            self.assertIn(f'Productive day: {new}\nProductivity scale: 10\n', updated)
            self.assertEqual(normalize_text(updated), updated)

    def test_marks_unrated_and_preserves_new_scores(self):
        self.assertIn('Productive day: unrated\nProductivity scale: 10\n', normalize_text('Productive day: unrated\n'))
        self.assertIn('Productive day: 9\nProductivity scale: 10\n', normalize_text('Productive day: 9\n'))

    def test_rejects_unknown_existing_scale(self):
        with self.assertRaises(ValueError):
            normalize_text('Productive day: 4\nProductivity scale: 7\n')


if __name__ == '__main__':
    unittest.main()
