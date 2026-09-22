"""Completion archive in the vault, with lineage from explicit carry decisions."""
import json
import os
import re
import tempfile
from hashlib import sha256
from urllib.parse import unquote

TITLES = [('What would make today feel like a good day?', ''),
          ('What would be great to do today, if I have time?', '[If time] ')]
MARKER = '<!-- journal-task-history: '


def plans(text):
    result = []
    for title, prefix in TITLES:
        match = re.search(r'^### '+re.escape(title)+r'\s*\r?\n([\s\S]*?)(?=^### |\Z)', text, re.M)
        if match:
            lines = [s.strip() for s in match[1].splitlines() if s.strip()]
            result.extend(prefix+re.sub(r'^(?:[-*+]\s+(?:\[[ xX]\]\s+)?|\d+[.)]\s+)', '', s) for s in lines)
    return result


def evening_tasks(text):
    block = re.search(r'^### Morning plans — evening check-in\s*\n([\s\S]*?)(?=^### |\Z)', text, re.M)
    result = []
    for checked, description in re.findall(r'^- \[([ xX])\] (.+?)\r?$', block[1], re.M) if block else []:
        meta = {}
        match = re.search(r' <!-- task-meta: (.*?) -->$', description)
        if match:
            try:
                decoded = json.loads(unquote(match[1]))
                if isinstance(decoded, dict):
                    meta = {k: v for k, v in decoded.items() if k in ('original', 'followup', 'parent') and isinstance(v, str)}
                    description = description[:match.start()]
            except (ValueError, TypeError):
                pass
        result.append({**meta, 'text': description, 'done': checked.lower() == 'x'})
    return result


def completions(journal):
    origins, completed = {}, {}
    for path in sorted((journal.vault / 'Journal').glob('????-??-??.md')):
        day = path.stem
        record = journal.read(day)
        morning, evening = record['sections']['morning'], record['sections']['evening']
        choices = {}
        match = re.match(r'<!-- carry-review: (.*?) -->', morning)
        if match:
            try:
                decoded = json.loads(unquote(match[1]))
                if isinstance(decoded, dict):
                    choices = decoded
            except (ValueError, TypeError):
                pass
        carried = {}
        for source, action in choices.items():
            origin = origins.get(source)
            if not origin or source[:10] >= day:
                continue
            text = source[11:].removeprefix('[If time] ')
            if action in ('Added to good-day plans', 'Added to if-time'):
                target = ('[If time] ' if action == 'Added to if-time' else '') + text
                carried[target] = origin
            elif action == 'Completed':
                add_completion(completed, origin, day, 'morning')
        for text in plans(morning):
            key = day+':'+text
            origins[key] = carried.get(text, {'id': sha256(key.encode()).hexdigest()[:24],
                                             'text': text.removeprefix('[If time] '), 'created': day})
        for task in evening_tasks(evening):
            text = task['text']
            key = day+':'+text
            original = day+':'+task.get('original', text)
            identity = day+':followup:'+task['followup'] if task.get('followup') else original
            origin = origins.get(original) if not task.get('followup') else None
            origin = dict(origin or {'id': sha256(identity.encode()).hexdigest()[:24], 'created': day})
            origin['text'] = text.removeprefix('[If time] ')
            if task.get('original') and task['original'] != text:
                origin['original_text'] = task['original'].removeprefix('[If time] ')
            if task.get('parent'):
                origin['followup_to'] = task['parent'].removeprefix('[If time] ')
            origins[key] = origin
            if task['done']:
                add_completion(completed, origin, day, 'evening')
    return completed


def add_completion(records, origin, day, period):
    key = origin['id']+':'+day+':'+period
    records[key] = {**origin, 'completed': day, 'period': period}


def archive(journal, write=False):
    path = journal.vault / 'Tasks' / 'Completed tasks.md'
    if not path.resolve().is_relative_to(journal.vault):
        raise ValueError('Task history must stay inside the vault.')
    previous = {}
    if path.exists():
        text = path.read_text(encoding='utf-8')
        if not text.startswith(MARKER):
            raise ValueError('Tasks/Completed tasks.md already exists and is not an app archive. Please rename it first.')
        previous = json.loads(text[len(MARKER):text.index(' -->')])
    current = completions(journal)
    # Keep audit records even if a note is later changed or removed.
    merged = {**previous, **current}
    rows = sorted(merged.values(), key=lambda row: (row['completed'], row['text']), reverse=True)
    if write and (merged != previous or not path.exists()):
        body = MARKER+json.dumps(merged, ensure_ascii=True).replace('--', '\\u002d\\u002d')+' -->\n'
        body += '# Completed tasks\n\nCompletion history maintained by the journal app. Dates use the selected journal date. '
        body += 'Records remain here if a checkbox is later cleared or a note removed. Identical tasks on different days are separate unless explicitly carried forward.\n\n'
        for row in rows:
            safe = row['text'].replace('\n', ' ')
            body += f"- [x] {safe} — Created: {row['created']} · Completed: {row['completed']} ({row['period']})\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.tasks-', suffix='.tmp', dir=path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return rows
