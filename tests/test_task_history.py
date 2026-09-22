import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import quote
from journal import Journal


class TaskHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.j = Journal(Path(self.temp.name))

    def save(self, day, period, body):
        return self.j.save(day, period, body, self.j.read(day)['revision'])

    def morning(self, task, choices=None, optional=False):
        return '<!-- carry-review: '+quote(json.dumps(choices or {}))+' -->\n### '+('What would be great to do today, if I have time?' if optional else 'What would make today feel like a good day?')+'\n\n- '+task+'\n'

    def test_lineage_across_categories_and_days_and_recurring_task(self):
        self.save('2026-09-15','morning',self.morning('Read'))
        self.save('2026-09-16','morning',self.morning('Read',{'2026-09-15:Read':'Added to if-time'},True))
        self.save('2026-09-17','morning',self.morning('Read',{'2026-09-16:[If time] Read':'Added to good-day plans'}))
        self.save('2026-09-17','evening','### Morning plans — evening check-in\n\n- [x] Read\n')
        rows=self.j.task_history()
        self.assertEqual(len(rows),1)
        self.assertEqual((rows[0]['created'],rows[0]['completed']),('2026-09-15','2026-09-17'))
        self.save('2026-09-18','morning',self.morning('Read'))
        self.save('2026-09-18','evening','### Morning plans — evening check-in\n\n- [x] Read\n')
        self.assertEqual(len(self.j.task_history()),2)
        self.assertEqual(self.j.task_history()[0]['created'],'2026-09-18')
        self.assertTrue((self.j.vault/'Tasks'/'Completed tasks.md').exists())
        self.save('2026-09-18','evening','### Morning plans — evening check-in\n\n- [ ] Read\n')
        self.assertEqual(len(self.j.task_history()),2)  # historical completion retained

    def test_already_done_does_not_rewrite_previous_night_or_reappear(self):
        self.save('2026-09-15','morning',self.morning('Read'))
        old=self.save('2026-09-15','evening','### Morning plans — evening check-in\n\n- [ ] Read\n')
        self.save('2026-09-16','morning','<!-- carry-review: '+quote(json.dumps({'2026-09-15:Read':'Completed'}))+' -->\n')
        self.assertEqual(self.j.read('2026-09-15')['revision'],old['revision'])
        self.assertEqual(self.j.carryover('2026-09-17')['items'],[])
        rows=self.j.task_history()
        self.assertEqual((rows[0]['created'],rows[0]['completed']),('2026-09-15','2026-09-16'))
        self.assertEqual(len(self.j.task_history(write=True)),1)

    def test_existing_user_file_is_not_overwritten(self):
        target=self.j.vault/'Tasks'/'Completed tasks.md'
        target.parent.mkdir()
        target.write_text('My own notes',encoding='utf-8')
        result=self.save('2026-09-15','morning',self.morning('Read'))
        self.assertIn('warning',result)
        self.assertEqual(target.read_text(),'My own notes')

    def test_optional_list_over_four_carries_and_archives(self):
        tasks = [f'Extra {n}' for n in range(7)]
        self.save('2026-09-15', 'morning', '### What would be great to do today, if I have time?\n\n'+ '\n'.join('- '+t for t in tasks))
        self.assertEqual(len(self.j.carryover('2026-09-16')['items']), 7)
        self.save('2026-09-15', 'evening', '### Morning plans — evening check-in\n\n- [x] [If time] Extra 6\n')
        self.assertEqual(len(self.j.carryover('2026-09-16')['items']), 6)
        self.assertEqual(self.j.task_history()[0]['text'], 'Extra 6')

    def test_evening_edit_and_followup_preserve_origin_and_carry(self):
        self.save('2026-09-15','morning',self.morning('Build app'))
        meta=quote(json.dumps({'original':'Build app'}))
        follow=quote(json.dumps({'original':'Finish tests','followup':'test-id','parent':'Build app'}))
        evening='### Morning plans — evening check-in\n\n- [x] Built screen <!-- task-meta: '+meta+' -->\n- [ ] Finish tests <!-- task-meta: '+follow+' -->\n'
        self.save('2026-09-15','evening',evening)
        self.assertEqual(self.j.carryover('2026-09-16')['items'],['Finish tests'])
        done=self.j.task_history()[0]
        self.assertEqual(done['text'],'Built screen')
        self.assertEqual(done['original_text'],'Build app')
        self.assertIn('Build app',self.j.read('2026-09-15')['sections']['morning'])
        self.save('2026-09-16','morning',self.morning('Finish tests',{'2026-09-15:Finish tests':'Added to good-day plans'}))
        self.save('2026-09-16','evening','### Morning plans — evening check-in\n\n- [x] Finish tests\n')
        task=next(r for r in self.j.task_history() if r['text']=='Finish tests')
        self.assertEqual(task['created'],'2026-09-15')
        self.assertEqual(task['followup_to'],'Build app')
    def test_snoozed_tasks_survive_intervening_plans_and_reschedule(self):
        key='2026-09-15:Read'
        self.save('2026-09-15','morning',self.morning('Read'))
        self.save('2026-09-16','morning',self.morning('Other',{key:'Skipped today'}))
        self.assertIn('Read',self.j.carryover('2026-09-17')['items'])
        self.save('2026-09-17','morning',self.morning('New',{key:'Skipped until 2026-09-24'}))
        self.assertNotIn('Read',self.j.carryover('2026-09-23')['items'])
        self.assertIn('Read',self.j.carryover('2026-09-24')['items'])
        self.assertIn('Read',self.j.carryover('2026-09-26')['items'])
        self.save('2026-09-26','morning',self.morning('Read',{key:'Added to good-day plans'}))
        self.assertEqual(self.j.carryover('2026-09-27')['items'].count('Read'),1)
        self.save('2026-09-26','evening','### Morning plans — evening check-in\n\n- [x] Read\n')
        self.assertNotIn('Read',self.j.carryover('2026-09-27')['items'])

    def test_snooze_completed_and_custom_days(self):
        key='2026-09-15:Read'
        self.save('2026-09-15','morning',self.morning('Read'))
        self.save('2026-09-16','morning',self.morning('Other',{key:'Skipped until 2026-09-19'}))
        self.assertNotIn('Read',self.j.carryover('2026-09-18')['items'])
        self.assertIn('Read',self.j.carryover('2026-09-19')['items'])
        self.save('2026-09-19','morning',self.morning('Other',{key:'Completed'}))
        self.assertNotIn('Read',self.j.carryover('2026-09-20')['items'])
    def test_more_than_four_good_day_plans(self):
        tasks=[f'Plan {i}' for i in range(7)]
        self.save('2026-09-15','morning',self.morning('\n- '.join(tasks)))
        self.assertEqual(self.j.carryover('2026-09-16')['items'],tasks)
        self.save('2026-09-15','evening','### Morning plans — evening check-in\n\n- [x] Plan 6\n')
        self.assertEqual(self.j.task_history()[0]['text'],'Plan 6')
        self.assertEqual(len(self.j.carryover('2026-09-16')['items']),6)
    def test_optional_do_later_date_survives_other_days(self):
        key='2026-09-15:[If time] Buy weights'
        self.save('2026-09-15','morning',self.morning('Buy weights',{key:'Skipped until 2026-09-20'},True))
        self.assertNotIn('[If time] Buy weights',self.j.carryover('2026-09-16')['items'])
        self.save('2026-09-17','morning',self.morning('Something else'))
        self.assertNotIn('[If time] Buy weights',self.j.carryover('2026-09-19')['items'])
        due=self.j.carryover('2026-09-20')
        self.assertIn('[If time] Buy weights',due['items'])
        self.assertEqual(next(i for i in due['entries'] if i['text']=='[If time] Buy weights')['key'],key)
        self.assertIn('[If time] Buy weights',self.j.carryover('2026-09-22')['items'])
