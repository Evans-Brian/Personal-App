from pathlib import Path
import tempfile
import unittest

from oura import OuraStore
from sleep_analysis import analyze, session


def measured():
    return {'id': 'ring', 'day': '2026-10-22', 'type': 'long_sleep',
            'bedtime_start': '2026-10-22T01:00:00-04:00', 'bedtime_end': '2026-10-22T06:00:00-04:00',
            'time_in_bed': 18000, 'total_sleep_duration': 18000, 'awake_time': 0,
            'latency': 0, 'sleep_phase_30_sec': '2' * 600, 'average_heart_rate': 60}


def manual(start='07:00', end='09:00'):
    first, last = '2026-10-22T' + start + ':00-04:00', '2026-10-22T' + end + ':00-04:00'
    return {'id': 'report', 'day': '2026-10-22', 'type': 'sleep', 'data_source': 'manual',
            'bedtime_start': first, 'bedtime_end': last, 'time_in_bed': 7200, 'total_sleep_duration': 7200,
            'reported_sleep_window': {'start': first, 'end': last},
            'reported_awake_before_sleep': {'start': '2026-10-22T06:00:00-04:00', 'end': first,
                                           'duration_seconds': 3600}}


class MixedSleepTests(unittest.TestCase):
    def test_manual_times_and_preceding_wake_do_not_invent_stages_or_physiology(self):
        result = session(manual())
        self.assertEqual(result['onset'], '2026-10-22T07:00:00-04:00')
        self.assertEqual(result['final_wake'], '2026-10-22T09:00:00-04:00')
        self.assertEqual(result['onset_source'], 'self-reported times')
        self.assertEqual(result['reported_awake_before_sleep']['minutes'], 60)
        self.assertEqual(result['stages'], [])
        for key in ['deep_minutes', 'rem_minutes', 'light_minutes', 'heart_rate', 'hrv', 'waso_minutes']:
            self.assertIsNone(result[key])
        invalid = manual()
        invalid['reported_sleep_window']['end'] = '2026-10-23T09:00:00-04:00'
        invalid['reported_awake_before_sleep']['duration_seconds'] = 999
        self.assertIsNone(session(invalid)['final_wake'])
        self.assertIsNone(session(invalid)['reported_awake_before_sleep'])

    def test_mixed_night_totals_and_latest_wake_include_manual_period(self):
        with tempfile.TemporaryDirectory() as folder:
            store = OuraStore(Path(folder) / 'oura.sqlite3')
            store.import_records('sleep', [measured(), manual()])
            original = store.read_range('2026-10-22', '2026-10-22')
            result = analyze(store, start='2026-10-22', end='2026-10-22')
            night, = result['nights']
            self.assertEqual(night['id'], 'ring')
            self.assertEqual(night['asleep_minutes'], 300)
            self.assertEqual(night['all_sleep_minutes'], 420)
            self.assertEqual(result['summary']['all_sleep_minutes']['mean'], 420)
            self.assertEqual(night['last_wake'], '2026-10-22T09:00:00-04:00')
            self.assertEqual(result['summary']['last_wake_clock']['median'], 540)
            self.assertEqual(night['heart_rate'], 60)
            self.assertEqual(night['period_count'], 2)
            self.assertFalse(night['overlapping_periods'])
            self.assertEqual(store.read_range('2026-10-22', '2026-10-22'), original)

    def test_overlapping_sources_remain_visible_without_double_counting(self):
        with tempfile.TemporaryDirectory() as folder:
            store = OuraStore(Path(folder) / 'oura.sqlite3')
            store.import_records('sleep', [measured(), manual('05:00', '07:00')])
            result = analyze(store, start='2026-10-22', end='2026-10-22')
            self.assertEqual(len(result['sessions']), 2)
            self.assertTrue(result['nights'][0]['overlapping_periods'])
            self.assertIsNone(result['nights'][0]['all_sleep_minutes'])
            self.assertEqual(result['summary']['all_sleep_minutes']['n'], 0)

    def test_manual_only_period_is_visible_without_an_oura_main_session(self):
        with tempfile.TemporaryDirectory() as folder:
            store = OuraStore(Path(folder) / 'oura.sqlite3')
            store.import_records('sleep', [manual()])
            result = analyze(store, start='2026-10-22', end='2026-10-22')
            self.assertEqual(result['coverage']['nights'], 1)
            self.assertEqual(result['nights'][0]['all_sleep_minutes'], 120)
            self.assertEqual(result['nights'][0]['main_period_count'], 0)
