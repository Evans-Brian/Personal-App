from pathlib import Path
import tempfile
import unittest

from evening_feelings import NEGATIVE_PROMPT, with_negative_feelings, negative_answer, move_reviewed_passages

COMBINED = 'What made me happy, grateful, engaged, or connected?'
PROUD = 'What am I proud of today?'
DIFFERENT = 'What would I do differently if I replayed today?'
BASE = f'### {COMBINED}\n\nHappy / grateful:\nA quiet walk.\n\n### {PROUD}\n\nFinished a project. I felt discouraged after a setback. Kept going.\n\n### {DIFFERENT}\n\nTake a break.\n\n<!-- evening-habits: %7B%22caffeine_last_intake%22%3A%2216%3A00%22%7D -->\n'


class EveningFeelingsTests(unittest.TestCase):
    def test_adds_one_question_without_reclassifying_answers(self):
        expected = BASE.replace('### ' + PROUD, '### Negative feelings today\n\n\n### ' + PROUD)
        self.assertEqual(with_negative_feelings(BASE), expected)
        self.assertEqual(with_negative_feelings(expected), expected)
        positive = BASE.replace('A quiet walk.', 'I feel less stressed and more hopeful.')
        self.assertIn('I feel less stressed and more hopeful.', with_negative_feelings(positive))
        self.assertEqual(negative_answer(with_negative_feelings(positive)), '')
        self.assertEqual(with_negative_feelings('A custom freeform note.'), 'A custom freeform note.')

    def test_moves_only_reviewed_words_and_keeps_other_answers_and_metadata(self):
        moves = [{'question': PROUD, 'excerpt': 'I felt discouraged after a setback. '}]
        updated = move_reviewed_passages(BASE, moves)
        self.assertEqual(negative_answer(updated), 'I felt discouraged after a setback.')
        self.assertIn('Finished a project. Kept going.', updated)
        self.assertIn('Happy / grateful:\nA quiet walk.', updated)
        self.assertIn('Take a break.', updated)
        self.assertTrue(updated.endswith('<!-- evening-habits: %7B%22caffeine_last_intake%22%3A%2216%3A00%22%7D -->\n'))
        self.assertEqual(move_reviewed_passages(updated, moves), updated)

    def test_empty_historical_label_and_existing_negative_answer(self):
        text = BASE.replace('Happy / grateful:\nA quiet walk.', 'Happy / grateful:\nA difficult moment left me upset.')
        updated = move_reviewed_passages(with_negative_feelings(text, 'An earlier feeling.'),
            [{'question': COMBINED, 'excerpt': 'A difficult moment left me upset.'}])
        self.assertEqual(negative_answer(updated), 'An earlier feeling.\n\nA difficult moment left me upset.')
        self.assertNotIn('Happy / grateful:', updated)

    def test_fenced_heading_is_not_a_question_and_newlines_are_preserved(self):
        raw = BASE.replace('A quiet walk.', 'A code sample:\n```markdown\n### Negative feelings today\n```').replace('\n', '\r\n')
        updated = with_negative_feelings(raw)
        self.assertEqual(updated.count('### Negative feelings today'), 2)
        self.assertIn('\r\n### Negative feelings today\r\n\r\n\r\n### ' + PROUD, updated)

    def test_ambiguous_or_missing_passage_fails_safely(self):
        with self.assertRaises(ValueError):
            move_reviewed_passages(BASE, [{'question': PROUD, 'excerpt': 'Not in this note.'}])
        with self.assertRaises(ValueError):
            move_reviewed_passages(BASE.replace('Kept going.', 'Kept going. Kept going.'), [{'question': PROUD, 'excerpt': 'Kept going.'}])

    def test_old_client_omission_keeps_saved_feelings_and_explicit_clear_works(self):
        from journal import Journal
        with tempfile.TemporaryDirectory() as folder:
            journal = Journal(folder)
            current = journal.read('2026-11-09')
            saved = journal.save(current['date'], 'evening', with_negative_feelings(BASE, 'A difficult feeling.'), current['revision'])
            updated = journal.save(current['date'], 'evening', BASE, saved['revision'])
            self.assertEqual(negative_answer(updated['sections']['evening']), 'A difficult feeling.')
            cleared = journal.save(current['date'], 'evening', with_negative_feelings(BASE), updated['revision'])
            self.assertEqual(negative_answer(cleared['sections']['evening']), '')
