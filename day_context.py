"""Modern US federal calendar; standard Monday-Friday observed dates (OPM)."""
from datetime import date, timedelta
import json
import re


def day_context(day):
    target = date.fromisoformat(day)
    holidays = []
    observed = []
    for year in range(max(1, target.year-1), min(9999, target.year+1)+1):
        def nth(month, weekday, number):
            first = date(year, month, 1)
            return first + timedelta(days=(weekday-first.weekday()) % 7 + 7*(number-1))
        fixed = [(1, 1, "New Year's Day"), (6, 19, 'Juneteenth National Independence Day'),
                 (7, 4, 'Independence Day'), (11, 11, 'Veterans Day'), (12, 25, 'Christmas Day')]
        dates = [(date(year,m,d), name) for m,d,name in fixed if m != 6 or year >= 2021]
        dates += [(nth(1,0,3), 'Martin Luther King Jr. Day'), (nth(2,0,3), "Washington's Birthday"),
                  (date(year,5,31)-timedelta(days=date(year,5,31).weekday()), 'Memorial Day'),
                  (nth(9,0,1),'Labor Day'), (nth(10,0,2),'Columbus Day'), (nth(11,3,4),'Thanksgiving Day')]
        for actual, name in dates:
            if target == actual:
                holidays.append(name)
            offset = -1 if actual.weekday() == 5 else 1 if actual.weekday() == 6 else 0
            if 1 <= actual.toordinal()+offset <= date.max.toordinal() and target.toordinal() == actual.toordinal()+offset:
                observed.append(name)
    return {'is_weekend': target.weekday() >= 5, 'is_work_holiday': bool(observed),
            'holiday_names': holidays, 'observed_holiday_names': observed,
            'holiday_calendar': 'US federal (standard Monday-Friday schedule)'}


def add_day_context(text, day):
    newline = '\r\n' if '\r\n' in text else '\n'
    block = 'journal_calendar:'+newline
    for key, value in day_context(day).items():
        block += '  '+key+': '+json.dumps(value, ensure_ascii=False)+newline
    front = re.match(r'\A---\r?\n([\s\S]*?)^---[ \t]*(?:\r?\n|\Z)', text, re.M)
    if not front:
        if text.startswith('---'):
            raise ValueError('Repair the YAML frontmatter before saving calendar metadata.')
        return '---'+newline+block+'---'+newline+text
    old = front[1]
    old = re.sub(r'^journal_calendar:[^\r\n]*\r?\n(?:[ \t]+[^\r\n]*\r?\n)*', '', old, flags=re.M)
    return text[:front.start(1)]+old+block+text[front.end(1):]
