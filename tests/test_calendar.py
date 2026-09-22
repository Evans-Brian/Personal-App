import unittest
from day_context import day_context, add_day_context

class CalendarTests(unittest.TestCase):
    def test_weekend_and_observed_holidays(self):
        self.assertTrue(day_context('2026-09-19')['is_weekend'])
        self.assertFalse(day_context('2026-09-19')['is_work_holiday'])
        self.assertTrue(day_context('2026-07-03')['is_work_holiday'])
        self.assertEqual(day_context('2026-07-04')['holiday_names'],['Independence Day'])
        self.assertFalse(day_context('2026-07-04')['is_work_holiday'])
        self.assertTrue(day_context('2021-12-31')['is_work_holiday'])
        self.assertTrue(day_context('2026-11-26')['is_work_holiday'])
        self.assertFalse(day_context('2020-06-19')['is_work_holiday'])
    def test_preserves_frontmatter_and_body_and_is_idempotent(self):
        for nl in ['\n','\r\n']:
            original=nl.join(['---','date: 2026-09-19','tags:','  - journal','custom: keep','---','','## Morning','My words.',''])
            updated=add_day_context(original,'2026-09-19')
            self.assertIn('custom: keep'+nl,updated)
            self.assertEqual(updated.split('## Morning')[1],original.split('## Morning')[1])
            self.assertEqual(add_day_context(updated,'2026-09-19'),updated)
