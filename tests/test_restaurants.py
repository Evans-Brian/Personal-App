import tempfile
import unittest
from pathlib import Path
from restaurants import Restaurants
from journal import Conflict

class RestaurantTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Restaurants(Path(self.tmp.name))
    def row(self):
        return {'id':'r1','name':'Cafe','date':'2026-09-19','you':{'score':4,'review':'Good','thoughts':'Return'},'ashley':{'score':5,'review':'Loved it','thoughts':'Patio'},'dishes':[{'id':'d1','name':'Soup','you':{'score':3,'review':'Nice','thoughts':'Warm'},'ashley':None}]}
    def test_roundtrip_and_conflict(self):
        original=self.store.read();saved=self.store.save([self.row()],original['revision'])
        self.assertEqual(saved['restaurants'],[self.row()])
        self.assertEqual(Restaurants(self.store.vault).read(),saved)
        with self.assertRaises(Conflict):self.store.save([],original['revision'])
    def test_invalid_data_does_not_replace_saved_data(self):
        initial=self.store.save([self.row()],self.store.read()['revision'])
        for key,value in [('date','2026-02-30'),('name','')]:
            row=self.row();row[key]=value
            with self.assertRaises(ValueError):self.store.save([row],initial['revision'])
        row=self.row();row['you']['score']=6
        with self.assertRaises(ValueError):self.store.save([row],initial['revision'])
        self.assertEqual(self.store.read(),initial)
