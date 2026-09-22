import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from app import make_server
from journal import Journal, Conflict
from oura import OuraStore


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.journal = Journal(self.root / 'vault')

    def test_round_trip_preserves_other_section_and_unicode(self):
        first = self.journal.read('2026-09-17')
        saved = self.journal.save(first['date'], 'morning', 'Feeling hopeful ☀️', first['revision'])
        saved = self.journal.save(first['date'], 'evening', 'A good walk.', saved['revision'])
        saved = self.journal.save(first['date'], 'morning', 'Feeling rested', saved['revision'])
        self.assertIn('A good walk.', saved['markdown'])
        self.assertEqual(saved['markdown'].count('## Morning'), 1)
        self.assertTrue(saved['markdown'].startswith('---\ndate: 2026-09-17'))
        self.assertEqual(len(list((self.root/'vault'/'Journal').glob('*.md'))), 1)

    def test_preserves_existing_frontmatter_and_unmanaged_text(self):
        path = self.journal.path('2026-09-17')
        path.parent.mkdir(parents=True)
        original = '---\ncustom: keep-me\n---\n\nPersonal notes\n\n## Morning\nold\n\n## Other\nKeep this.\n'
        path.write_bytes(original.encode('utf-8'))
        record = self.journal.read('2026-09-17')
        saved = self.journal.save(record['date'], 'morning', 'new', record['revision'])
        from day_context import add_day_context
        self.assertEqual(saved['markdown'], add_day_context(original.replace('old', 'new'), saved['date']))

    def test_external_edit_conflicts_without_losing_text(self):
        record = self.journal.read('2026-09-17')
        saved = self.journal.save(record['date'], 'morning', 'initial', record['revision'])
        path = self.journal.path(record['date'])
        path.write_text('Edited in Obsidian', encoding='utf-8')
        with self.assertRaises(Conflict):
            self.journal.save(record['date'], 'morning', 'stale draft', saved['revision'])
        self.assertEqual(path.read_text(), 'Edited in Obsidian')

    def test_date_and_heading_validation(self):
        for day in ['../secret', '2026-02-30', '20260917']:
            with self.assertRaises(ValueError):
                self.journal.read(day)
        record = self.journal.read('2026-09-17')
        with self.assertRaises(ValueError):
            self.journal.save(record['date'], 'morning', '## Evening\nOops', record['revision'])

    def test_range_and_separate_oura_storage(self):
        for day in ['2026-09-16','2026-09-17','2026-09-18']:
            record = self.journal.read(day)
            self.journal.save(day, 'morning', 'Hello', record['revision'])
        self.assertEqual(len(self.journal.read_range('2026-09-16','2026-09-17')),2)
        store = OuraStore(self.root/'data'/'oura.sqlite3')
        store.upsert('sleep', {'id':'one','day':'2026-09-17','score':80})
        store.upsert('sleep', {'id':'one','day':'2026-09-17','score':85})
        rows = store.read_range('2026-09-17','2026-09-17')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['data']['score'],85)
        with self.assertRaises(ValueError):
            make_server(self.root/'vault', self.root/'vault'/'oura.sqlite3', 0)

    def test_http_flow_and_cross_origin_protection(self):
        server = make_server(self.root/'vault', self.root/'data'/'oura.sqlite3',0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        conn = http.client.HTTPConnection('127.0.0.1', server.server_port)
        self.addCleanup(conn.close)
        conn.request('GET','/api/entry?date=2026-09-17')
        response = conn.getresponse()
        self.assertEqual(response.status,200)
        entry = json.loads(response.read())
        body = json.dumps(dict(date=entry['date'],period='morning',content='HTTP test',revision=entry['revision']))
        conn.request('POST','/api/entry',body,{'Content-Type':'application/json'})
        response = conn.getresponse()
        self.assertEqual(response.status,200)
        self.assertIn('HTTP test',json.loads(response.read())['markdown'])
        conn.request('POST','/api/entry',body,{'Content-Type':'application/json'})
        response = conn.getresponse()
        self.assertEqual(response.status,409)
        response.read()
        conn.request('POST','/api/entry',body,{'Content-Type':'application/json','Origin':'https://example.com'})
        response = conn.getresponse()
        self.assertEqual(response.status,403)
        response.read()


if __name__ == '__main__':
    unittest.main()
