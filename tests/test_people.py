import unittest
import tempfile
from pathlib import Path
from uuid import uuid4
from people import People

class PeopleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=People(Path(self.temp.name))
        self.person={'action':'person','id':str(uuid4()),'name':'Alex','relation':'Friend'}
    def test_multiple_notes_dates_and_retry(self):
        self.store.add(self.person)
        for day,text in [('2026-09-21','First'),('2026-09-01','Earlier'),('2026-09-21','Second')]:
            payload={'action':'note','id':str(uuid4()),'person_id':self.person['id'],'date':day,'text':text}
            self.store.add(payload);self.store.add(payload)
        self.store.add(self.person)
        saved=People(self.store.vault).read()['people']
        self.assertEqual(len(saved),1);self.assertEqual(len(saved[0]['notes']),3)
        self.assertEqual(saved[0]['notes'][1]['date'],'2026-09-01')
        self.assertEqual(saved[0]['relation'],'Friend')
    def test_validation_preserves_notes(self):
        original=self.store.add(self.person)
        for extra in [{'date':'2026-02-30','text':'Note'},{'date':'2026-09-21','text':' '}]:
            with self.assertRaises(ValueError):self.store.add({'action':'note','id':str(uuid4()),'person_id':self.person['id'],**extra})
        self.assertEqual(self.store.read(),original)
    def test_independent_people_do_not_overwrite_each_other(self):
        self.store.add(self.person)
        self.store.add({'action':'person','id':str(uuid4()),'name':'Sam','relation':'Coworker'})
        self.assertEqual(len(self.store.read()['people']),2)
    def test_relation_edit_preserves_notes_and_rejects_stale_edit(self):
        self.store.add(self.person)
        self.store.add({'action':'note','id':str(uuid4()),'person_id':self.person['id'],'date':'2026-09-21','text':'Keep this note'})
        payload={'action':'relation','id':str(uuid4()),'person_id':self.person['id'],'previous_relation':'Friend','relation':'Capital One Coworker'}
        self.store.add(payload)
        self.store.add(payload)
        saved=self.store.read()['people'][0]
        self.assertEqual(saved['relation'],'Capital One Coworker')
        self.assertEqual(saved['notes'][0]['text'],'Keep this note')
        with self.assertRaises(ValueError):
            self.store.add({**payload,'relation':'Other'})
