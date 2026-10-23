import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import quote
import http.client
import threading

from journal import Journal
from oura import OuraStore
from sleep_analysis import analyze, session, caffeine_log


def sleep(**overrides):
    value = {'id':'night','day':'2026-10-22','type':'long_sleep',
             'bedtime_start':'2026-10-21T22:00:00-04:00','bedtime_end':'2026-10-21T23:00:00-04:00',
             'time_in_bed':3600,'total_sleep_duration':2160,'awake_time':1440,'latency':120,
             'sleep_phase_30_sec':'4'*4+'1'*20+'4'*40+'2'*52+'4'*4}
    return {**value, **overrides}


class SleepAnalysisTests(unittest.TestCase):
    def test_manual_illustrative_stages_preserve_times_not_measured_stage_totals(self):
        record=sleep(data_source='manual',stages_estimated=True,latency=None,
                     deep_sleep_duration=600,light_sleep_duration=1560,rem_sleep_duration=0)
        value=session(record)
        self.assertEqual(value['data_source'],'manual')
        self.assertTrue(value['stages_estimated'])
        self.assertEqual(value['asleep_minutes'],36)
        self.assertEqual(value['waso_minutes'],20)
        self.assertEqual(value['onset_source'],'self-reported times; illustrative stages')
        self.assertTrue(value['stages'])
        for key in ('deep_minutes','light_minutes','rem_minutes','heart_rate','hrv','latency_minutes'):
            self.assertIsNone(value[key],key)
        with tempfile.TemporaryDirectory() as directory:
            store=OuraStore(Path(directory)/'oura.sqlite3')
            store.import_records('sleep',[record])
            store.import_records('daily_sleep',[{'id':'summary','day':record['day'],'score':80}])
            store.import_records('daily_readiness',[{'id':'readiness','day':record['day'],'temperature_deviation':.2}])
            store.import_records('daily_spo2',[{'id':'oxygen','day':record['day'],'spo2_percentage':{'average':97}}])
            result=analyze(store,start=record['day'],end=record['day'])
            night=result['nights'][0]
            for key in ('sleep_score','temperature_deviation','spo2'):
                self.assertIsNone(night[key],key)
            self.assertEqual(result['summary']['deep_minutes']['n'],0)
            self.assertEqual(result['summary']['asleep_minutes']['mean'],36)

    def test_caffeine_intake_distinguishes_times_none_unknown_and_legacy(self):
        for intake, after in [('00:00',False),('08:45',False),('15:00',False),('16:00',False),('16:01',True),('17:00',True),('19:00',True),('23:59',True),('none',False),(None,None),('25:00',None),('7 p.m.',None),('17:00\n',None),(1700,None)]:
            with self.subTest(intake=intake):
                habits={'caffeine_last_intake':intake,'caffeine_after_4pm':True}
                self.assertEqual(caffeine_log(habits),(intake if after is not None else None,after))
        self.assertEqual(caffeine_log({}),(None,None))
        self.assertEqual(caffeine_log({'caffeine_after_4pm':True}),(None,True))
        self.assertEqual(caffeine_log({'caffeine_after_4pm':False}),(None,False))

    def test_exact_caffeine_time_reaches_sleep_analysis_from_previous_evening(self):
        with tempfile.TemporaryDirectory() as directory:
            store=OuraStore(Path(directory)/'oura.sqlite3')
            journal=Journal(Path(directory)/'vault')
            store.import_records('sleep',[sleep(bedtime_start='2026-10-22T02:00:00-04:00',bedtime_end='2026-10-22T03:00:00-04:00')])
            record=journal.read('2026-10-21')
            for intake, after in [('15:00',False),('16:00',False),('17:00',True),('18:35',True),('none',False),(None,None)]:
                content='<!-- evening-habits: '+quote(json.dumps({'caffeine_last_intake':intake}))+' -->'
                record=journal.save(record['date'],'evening',content,record['revision'])
                night=analyze(store,journal,'2026-10-22','2026-10-22')['nights'][0]
                self.assertEqual(night['caffeine_day'],'2026-10-21')
                self.assertEqual(night['caffeine_last_intake'],intake)
                self.assertIs(night['caffeine_after_4pm'],after)

    def test_awakenings_exclude_latency_and_terminal_awake(self):
        value = session(sleep())
        self.assertEqual(value['waso_minutes'],20)
        self.assertEqual(value['longest_wake_minutes'],20)
        self.assertEqual(value['awake_minutes'],24)
        self.assertEqual(value['awakenings_5m'],1)
        self.assertEqual(value['onset'],'2026-10-21T22:02:00-04:00')
        self.assertEqual(value['final_wake'],'2026-10-21T22:58:00-04:00')
        self.assertEqual(value['awakenings'][0]['start'],'2026-10-21T22:12:00-04:00')

    def test_five_minute_fallback_and_missing_or_bad_coverage(self):
        value = session(sleep(sleep_phase_30_sec=None,sleep_phase_5_min='412444222224'))
        self.assertEqual(value['stage_resolution_seconds'],300)
        self.assertEqual(value['waso_minutes'],15)
        for phases in (None, '111', 'xx4'):
            value = session(sleep(sleep_phase_30_sec=phases))
            self.assertIsNone(value['waso_minutes'])
            self.assertEqual(value['onset_source'],'bedtime + reported latency')

    def test_all_awake_and_all_sleep_do_not_invent_events(self):
        value = session(sleep(sleep_phase_30_sec='4'*120,latency=None))
        self.assertIsNone(value['waso_minutes'])
        self.assertIsNone(value['onset'])
        value = session(sleep(sleep_phase_30_sec='2'*120))
        self.assertEqual(value['waso_minutes'],0)
        self.assertEqual(value['awakenings_5m'],0)

    def test_disrupted_windows_preserve_brief_sleep_rather_than_counting_it_awake(self):
        value = session(sleep(sleep_phase_30_sec='2'*10+'4'*30+'2'*4+'4'*30+'2'*46))
        self.assertEqual(value['longest_wake_minutes'],15)
        self.assertEqual(value['waso_minutes'],30)
        self.assertEqual(value['disrupted_windows'][0]['span_minutes'],32)
        self.assertEqual(value['disrupted_windows'][0]['awake_minutes'],30)

    def test_offset_change_uses_elapsed_duration_and_reports_offset_caveat(self):
        value = session(sleep(bedtime_start='2026-11-01T00:00:00-04:00',
                              bedtime_end='2026-11-01T03:00:00-05:00',
                              time_in_bed=14400,sleep_phase_30_sec='2'*480))
        self.assertTrue(value['offset_changed'])
        self.assertEqual(value['stage_coverage'],1)
        self.assertEqual(value['waso_minutes'],0)

    def test_naps_deleted_records_and_unknown_caffeine_are_handled(self):
        with tempfile.TemporaryDirectory() as directory:
            store=OuraStore(Path(directory)/'oura.sqlite3')
            journal=Journal(Path(directory)/'vault')
            store.import_records('sleep',[sleep(),sleep(id='nap',type='sleep',total_sleep_duration=300),
                                          sleep(id='deleted',type='deleted',total_sleep_duration=5000)])
            value=analyze(store,journal,'2026-10-21','2026-10-22')
            self.assertEqual(value['coverage']['nights'],1)
            self.assertEqual(value['nights'][0]['id'],'night')
            self.assertEqual(value['nights'][0]['period_count'],2)
            self.assertIsNone(value['nights'][0]['caffeine_after_4pm'])
            record=journal.read('2026-10-21')
            journal.save(record['date'],'evening','<!-- evening-habits: '+quote(json.dumps({'caffeine_after_4pm':False}))+' -->',record['revision'])
            self.assertIs(analyze(store,journal,'2026-10-21','2026-10-22')['nights'][0]['caffeine_after_4pm'],False)
            with self.assertRaises(ValueError):
                analyze(store,journal,'2026-10-22','2026-10-21')

    def test_after_midnight_caffeine_links_to_previous_evening(self):
        with tempfile.TemporaryDirectory() as directory:
            store=OuraStore(Path(directory)/'oura.sqlite3')
            journal=Journal(Path(directory)/'vault')
            store.import_records('sleep',[sleep(bedtime_start='2026-10-22T02:00:00-04:00',bedtime_end='2026-10-22T03:00:00-04:00')])
            value=analyze(store,journal,'2026-10-22','2026-10-22')
            self.assertEqual(value['nights'][0]['caffeine_day'],'2026-10-21')

    def test_analysis_baseline_excludes_earlier_records_from_every_rollup(self):
        with tempfile.TemporaryDirectory() as directory:
            store=OuraStore(Path(directory)/'oura.sqlite3')
            store.import_records('sleep',[
                sleep(id='before',day='2026-09-07',total_sleep_duration=600),
                sleep(id='on-baseline',day='2026-09-08'),
            ])
            value=analyze(store,start='2026-08-01',end='2026-09-09',analysis_start='2026-09-08')
            self.assertEqual(value['start'],'2026-09-08')
            self.assertEqual(value['analysis_start'],'2026-09-08')
            self.assertEqual([night['day'] for night in value['nights']],['2026-09-08'])
            self.assertEqual([item['id'] for item in value['sessions']],['on-baseline'])
            self.assertEqual(value['summary']['asleep_minutes']['mean'],36)
            self.assertEqual(value['monthly'][0]['n'],1)
            self.assertEqual(value['coverage']['calendar_days'],2)
            self.assertEqual(value['coverage']['missing_days'],1)
            self.assertEqual(value['inventory'][0]['start'],'2026-09-08')
            self.assertEqual(value['inventory'][0]['count'],1)
            self.assertEqual(len(store.read_range('2026-08-01','2026-09-09')),2)
            with self.assertRaisesRegex(ValueError,'Earlier data is ignored'):
                analyze(store,start='2026-08-01',end='2026-09-07',analysis_start='2026-09-08')

    def test_analysis_http_route_and_invalid_range(self):
        from app import make_server
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            server=make_server(root/'vault',root/'data'/'oura.sqlite3',0,sleep_start='2026-09-08')
            store=OuraStore(root/'data'/'oura.sqlite3')
            store.import_records('sleep',[sleep()])
            threading.Thread(target=server.serve_forever,daemon=True).start()
            try:
                connection=http.client.HTTPConnection('127.0.0.1',server.server_port)
                connection.request('GET','/api/oura/sleep-analysis?start=2026-10-21&end=2026-10-22')
                response=connection.getresponse()
                self.assertEqual(response.status,200)
                self.assertEqual(json.loads(response.read())['nights'][0]['waso_minutes'],20)
                connection.request('GET','/api/oura/sleep-analysis?start=2015-01-01&end=2026-10-22')
                response=connection.getresponse()
                self.assertEqual(response.status,200)
                self.assertEqual(json.loads(response.read())['start'],'2026-09-08')
                connection.request('GET','/api/oura/sleep-analysis?start=2026-10-22&end=2026-10-21')
                response=connection.getresponse()
                self.assertEqual(response.status,400)
                response.read()
                connection.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
