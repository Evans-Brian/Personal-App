import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit, parse_qs
from journal import Journal, PROMPTS
from oura import OuraStore
from oura_sync import OuraSync
from secrets_store import SecretStore


class DailyUseTests(unittest.TestCase):
    def test_carryover_both_lists_excludes_done_and_current_date(self):
        journal=Journal(self.root/'vault')
        entry=journal.read('2026-09-16')
        morning='### What would make today feel like a good day?\n\n- Walk\n- Read\n\n### What would be great to do today, if I have time?\n\n- Cook\n'
        entry=journal.save(entry['date'],'morning',morning,entry['revision'])
        self.assertEqual(journal.carryover('2026-09-16')['items'],[])
        self.assertFalse(journal.carryover('2026-09-17')['reviewed'])
        journal.save(entry['date'],'evening','### Morning plans — evening check-in\n\n- [x] Walk\n- [ ] Read\n- [ ] [If time] Cook\n',entry['revision'])
        result=journal.carryover('2026-09-18')
        self.assertEqual(result['items'],['Read','[If time] Cook'])
        self.assertEqual(result['source'],'2026-09-16')
        self.assertTrue(result['reviewed'])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = OuraStore(self.root / 'oura.sqlite3')
        self.sync = OuraSync(self.store, self.root / 'secrets.bin', 8766)

    def test_history_distinguishes_blank_missing_written(self):
        journal = Journal(self.root / 'vault')
        record = journal.read('2026-09-17')
        record = journal.save(record['date'], 'morning', PROMPTS['morning'], record['revision'])
        self.assertEqual(journal.history()[0], {'date':'2026-09-17','morning':'blank','evening':'missing','good':None,'productive':None})
        journal.save(record['date'], 'evening', PROMPTS['evening']+'A good walk.', record['revision'])
        self.assertEqual(journal.history()[0]['evening'], 'written')

    def test_secrets_encrypted_and_round_trip(self):
        vault = SecretStore(self.root/'private.bin')
        vault.write({'access_token':'dummy-private-test-token'})
        self.assertNotIn(b'dummy-private-test-token', vault.path.read_bytes())
        self.assertEqual(vault.read()['access_token'],'dummy-private-test-token')
        vault.write({'access_token':'replacement'})
        self.assertEqual(vault.read()['access_token'],'replacement')

    def test_oauth_cookie_state_and_single_use(self):
        self.sync.configure('test-client', 'test-secret')
        start = self.sync.begin()
        ticket = parse_qs(urlsplit(start).query)['ticket'][0]
        target, cookie = self.sync.authorize(ticket)
        query = parse_qs(urlsplit(target).query)
        self.assertEqual(query['scope'], ['daily'])
        self.assertEqual(query['redirect_uri'], ['http://localhost:8766/api/oura/callback'])
        with self.assertRaises(ValueError):
            self.sync.authorize(ticket)
        with patch('oura_sync.fetch_json') as fetch:
            with self.assertRaises(ValueError):
                self.sync.callback(query['state'][0], 'wrong-cookie', 'code')
            fetch.assert_not_called()
        start = self.sync.begin()
        target, cookie = self.sync.authorize(parse_qs(urlsplit(start).query)['ticket'][0])
        state = parse_qs(urlsplit(target).query)['state'][0]
        with patch('oura_sync.fetch_json', return_value={'access_token':'access','refresh_token':'refresh','expires_in':3600}):
            self.sync.callback(state, cookie, 'code')
        self.assertTrue(self.sync.status()['connected'])
        self.assertNotIn('access_token', self.sync.status())
        with self.assertRaises(ValueError):
            self.sync.callback(state, cookie, 'code')

    def test_import_is_validated_atomic_and_repeatable(self):
        self.store.import_records('daily_sleep', [{'id':'1','day':'2026-09-17','score':70}])
        self.store.import_records('daily_sleep', [{'id':'1','day':'2026-09-17','score':80}])
        with self.assertRaises(ValueError):
            self.store.import_records('daily_sleep', [{'id':'2','day':'2026-09-17'}, {'id':'3','day':'bad'}])
        rows = self.store.read_range('2026-09-17','2026-09-17')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['data']['score'],80)

    def test_sync_refreshes_rotating_token_and_paginates(self):
        self.sync.secrets.write({'client_id':'id','client_secret':'secret','access_token':'expired',
                                 'refresh_token':'old-refresh','expires_at':0})
        responses = [
            {'access_token':'new-access','refresh_token':'new-refresh','expires_in':3600},
            {'data':[{'id':'s1','day':'2026-09-17','score':80}], 'next_token':'page2'},
            {'data':[{'id':'s2','day':'2026-09-16','score':70}], 'next_token':None},
            {'data':[{'id':'r1','day':'2026-09-17','score':85}]},
            {'data':[{'id':'a1','day':'2026-09-17','score':90,'steps':1234}]},
            {'data':[{'id':'sleep1','day':'2026-09-17','type':'long_sleep','average_hrv':42,'lowest_heart_rate':50,'total_sleep_duration':27000}]},
        ]
        with patch('oura_sync.fetch_json', side_effect=responses) as fetch:
            self.assertEqual(self.sync.sync(),5)
            self.assertIn('next_token=page2', fetch.call_args_list[2].args[0].full_url)
        self.assertEqual(self.sync.secrets.read()['refresh_token'],'new-refresh')
        self.assertIsNotNone(self.sync.status()['last_sync'])
        self.assertEqual(len(self.store.read_range('2026-09-16','2026-09-17')),5)
        self.sync.disconnect()
        self.assertFalse(self.sync.status()['connected'])
        self.assertEqual(len(self.store.read_range('2026-09-16','2026-09-17')),5)

    def test_sleep_backfill_and_multiple_periods(self):
        from datetime import date, timedelta
        self.sync.secrets.write({'client_id':'id','client_secret':'secret','access_token':'access',
                                'refresh_token':'refresh','expires_at':time.time()+3600,'last_sync':'previous'})
        records=[{'id':'night','day':'2026-09-17','type':'long_sleep','average_hrv':None},
                 {'id':'nap','day':'2026-09-17','type':'late_nap','average_hrv':0}]
        with patch('oura_sync.fetch_json',side_effect=[{'data':[]},{'data':[]},{'data':[]},{'data':records}]) as fetch:
            self.assertEqual(self.sync.sync(),2)
            query=parse_qs(urlsplit(fetch.call_args_list[3].args[0].full_url).query)
            self.assertEqual(query['start_date'],[(date.today()-timedelta(days=90)).isoformat()])
        self.assertTrue(self.sync.secrets.read()['sleep_details_imported'])
        self.assertEqual(len(self.store.read_range('2026-09-17','2026-09-17')),2)
        with patch('oura_sync.fetch_json',return_value={'data':[]}) as fetch:
            self.sync.sync()
            query=parse_qs(urlsplit(fetch.call_args_list[3].args[0].full_url).query)
            self.assertEqual(query['start_date'],[(date.today()-timedelta(days=30)).isoformat()])

    def test_failed_sync_does_not_claim_success(self):
        self.sync.secrets.write({'client_id':'id','client_secret':'secret','access_token':'access',
                                 'refresh_token':'refresh','expires_at':time.time()+3600})
        with patch('oura_sync.fetch_json', side_effect=ValueError('Offline')):
            with self.assertRaises(ValueError):
                self.sync.sync()
        self.assertIsNone(self.sync.status()['last_sync'])
        self.assertEqual(self.sync.status()['error'],'Offline')
        self.assertFalse(self.sync.status()['syncing'])
