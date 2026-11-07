"""Markdown is the source of truth; no journal database or index."""
from datetime import date, timedelta
from hashlib import sha256
from pathlib import Path
import os
import re
import tempfile
import threading
import json
from urllib.parse import unquote
from task_history import archive, evening_tasks
from day_context import day_context, add_day_context
from migrate_evening_prompts import COMBINED_PROMPT, normalize_text as combine_evening_prompts

PROMPTS = {
    "morning": "### How am I feeling this morning?\n\n\n### Priority Tasks\n\n\n### Secondary Tasks\n\n\n### What might get in the way, and what could help?\n\n",
    "evening": f"### {COMBINED_PROMPT}\n\n\n### What am I proud of today?\n\n\n### What would I do differently if I replayed today?\n\n",
}
RATING_1_TO_10 = {1: 1, 2: 3, 3: 6, 4: 8, 5: 10}


class Conflict(Exception):
    pass


class Journal:
    def carryover(self, day):
        result = self._latest_carryover(day)
        decisions = {}
        for path in sorted((self.vault / 'Journal').glob('????-??-??.md')):
            if path.stem >= day:
                continue
            sections = self.read(path.stem)['sections']
            for task in evening_tasks(sections['evening']):
                if task.get('deleted'):
                    decisions[path.stem + ':' + task['text']] = (path.stem, 'Deleted')
                elif task.get('cooldown'):
                    action = 'Completed' if task['done'] else 'Skipped until ' + str(task['cooldown'])
                    decisions[path.stem + ':' + task['text']] = (path.stem, action)
            morning = sections['morning']
            match = re.match(r'<!-- carry-review: (.*?) -->', morning)
            if not match:
                continue
            try:
                choices = json.loads(unquote(match[1]))
                if isinstance(choices, dict):
                    for key, action in choices.items():
                        decisions[key] = (path.stem, action)
            except (ValueError, TypeError):
                continue
        entries = []
        for item in result['items']:
            key = result['source'] + ':' + item
            action = decisions.get(key, (None, None))[1]
            if action in ('Completed', 'Deleted') or (isinstance(action, str) and action.startswith('Added')):
                continue
            entries.append({'key': key, 'text': item, 'source': result['source']})
        for key, (chosen, action) in decisions.items():
            due = None
            if action == 'Skipped today':
                due = (date.fromisoformat(chosen) + timedelta(days=1)).isoformat()
            elif isinstance(action, str) and action.startswith('Skipped until '):
                try:
                    due = date.fromisoformat(action[14:]).isoformat()
                except ValueError:
                    continue
            if due:
                entries = [item for item in entries if item['key'] != key]
                if due <= day and len(key) > 11 and key[10] == ':':
                    entries.append({'key': key, 'text': key[11:], 'source': key[:10]})
        result['entries'] = entries
        result['items'] = [item['text'] for item in entries]
        return result

    def _latest_carryover(self, day):
        self.path(day)
        resolved = set()
        for path in sorted((self.vault / 'Journal').glob('????-??-??.md'), reverse=True):
            if path.stem >= day:
                continue
            record = self.read(path.stem)
            morning = record['sections']['morning']
            match = re.match(r'<!-- carry-review: (.*?) -->', morning)
            if match:
                try:
                    choices = json.loads(unquote(match[1]))
                    if isinstance(choices, dict):
                        resolved.update(key for key, action in choices.items() if action in ('Completed', 'Deleted'))
                except (ValueError, TypeError):
                    pass
            plans = []
            for title, prefix in [('Priority Tasks', ''), ('Secondary Tasks', '[If time] '),
                                  ('What would make today feel like a good day?', ''),
                                  ('What would be great to do today, if I have time?', '[If time] ')]:
                match = re.search(r'^### '+re.escape(title)+r'\s*\r?\n([\s\S]*?)(?=^### |\Z)', morning, re.M)
                if match:
                    lines = [s.strip() for s in match[1].splitlines() if s.strip()]
                    plans.extend(prefix+re.sub(r'^(?:[-*+]\s+(?:\[[ xX]\]\s+)?|\d+[.)]\s+)', '', s) for s in lines)
            evening = record['sections']['evening']
            tasks = evening_tasks(evening)
            for task in tasks:
                original = task.get('original', task['text'])
                if not task.get('followup') and original in plans:
                    plans[plans.index(original)] = task['text']
                elif task['text'] not in plans:
                    plans.append(task['text'])
            if not plans:
                continue
            checks = re.search(r'^### Morning plans — evening check-in\s*\n([\s\S]*?)(?=^### |\Z)', evening, re.M)
            done = [task['text'] for task in tasks if task['done'] or task.get('deleted')]
            remaining = []
            for item in plans:
                if item in done:
                    done.remove(item)
                elif item not in remaining and path.stem+':'+item not in resolved:
                    remaining.append(item)
            return {'source': path.stem, 'items': remaining, 'reviewed': bool(checks)}
        return {'source': None, 'items': [], 'reviewed': False}

    def __init__(self, vault):
        self.vault = Path(vault).resolve()
        self.lock = threading.Lock()

    def path(self, day):
        if not isinstance(day, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
            raise ValueError("Choose a date in YYYY-MM-DD format.")
        date.fromisoformat(day)
        path = self.vault / "Journal" / f"{day}.md"
        if not path.resolve().is_relative_to(self.vault):
            raise ValueError("Journal path must stay inside the vault.")
        return path

    def read(self, day):
        path = self.path(day)
        raw = path.read_bytes() if path.exists() else b""
        text = raw.decode("utf-8")
        sections = {}
        for period in PROMPTS:
            start, end = self.bounds(text, period)
            sections[period] = text[start:end] if start is not None else PROMPTS[period]
        jo = {'jo': False, 'worth_it': False, 'why': ''}
        match = re.search(r'<!-- evening-jo: (.*?) -->', sections['evening'])
        if match:
            try:
                value = json.loads(unquote(match[1]))
                if isinstance(value, dict):
                    jo.update(value)
            except (ValueError, TypeError):
                pass
        return {"jo": jo, "date": day, "revision": sha256(raw).hexdigest(), "sections": sections,
                "exists": path.exists(), "path": str(path), "markdown": text, "calendar": day_context(day)}

    @staticmethod
    def bounds(text, period):
        # Ordinary headings keep entries directly editable in Obsidian.
        matches = list(re.finditer(r"^## " + period.capitalize() + r"[ \t]*\r?\n", text, re.M))
        if len(matches) > 1:
            raise ValueError(f"Multiple {period} headings: edit the note in Obsidian first.")
        if not matches:
            return None, None
        start = matches[0].end()
        following = re.search(r"^#{1,2} ", text[start:], re.M)
        return start, start + following.start() if following else len(text)

    def save(self, day, period, content, revision):
        if period not in PROMPTS or not isinstance(content, str):
            raise ValueError("Invalid journal section.")
        if period == 'evening':
            content = combine_evening_prompts(content)
        if len(content) > 200_000 or re.search(r"^#{1,2} ", content, re.M):
            raise ValueError("Use level-three headings (###) within an entry; maximum 200,000 characters.")
        with self.lock:
            current = self.read(day)
            if revision != current["revision"]:
                raise Conflict("This note changed since you opened it. Copy your draft, then reload to review the latest note.")
            text = current["markdown"]
            if not current["exists"]:
                text = f"---\ndate: {day}\ntype: journal\ntags:\n  - journal\n---\n\n# {day}\n\n"
            start, end = self.bounds(text, period)
            newline = "\r\n" if "\r\n" in text else "\n"
            body = content.replace("\r\n", "\n").rstrip().replace("\n", newline) + newline * 2
            if start is None:
                text = text + ("\n\n" if text and not text.endswith("\n\n") else "") + f"## {period.capitalize()}\n" + body
            else:
                text = text[:start] + body + text[end:]
            text = add_day_context(text, day)
            path = self.path(day)
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix=".journal-", suffix=".tmp", dir=path.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                    handle.write(text)
                    handle.flush()
                    os.fsync(handle.fileno())
                if self.read(day)["revision"] != revision:
                    raise Conflict("The note changed during saving. Your draft has not overwritten it.")
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            result = self.read(day)
            try:
                archive(self, write=True)
            except (ValueError, OSError) as exc:
                result['warning'] = 'Journal saved, but task history could not be updated: '+str(exc)
            return result

    def task_history(self, write=False):
        with self.lock:
            return archive(self, write=write)

    def read_range(self, start, end):
        self.path(start)
        self.path(end)
        if start > end:
            raise ValueError("Start date must precede end date.")
        return [self.read(p.stem) for p in sorted((self.vault / "Journal").glob("????-??-??.md"))
                if start <= p.stem <= end]

    def history(self):
        entries = []
        for path in sorted((self.vault / 'Journal').glob('????-??-??.md'), reverse=True):
            try:
                record = self.read(path.stem)
                statuses = {}
                for period in PROMPTS:
                    start, end = self.bounds(record['markdown'], period)
                    body = record['markdown'][start:end] if start is not None else ''
                    answer = re.sub(r'^#{3,6} .*$', '', body, flags=re.M).strip()
                    answer = re.sub(r'^<!-- evening-jo: .*? -->\r?\n?', '', answer, flags=re.M).strip()
                    answer = re.sub(r'^<!-- evening-habits: .*? -->\r?\n?', '', answer, flags=re.M).strip()
                    answer = re.sub(r'^<!-- morning-sleep: .*? -->\r?\n?', '', answer, flags=re.M).strip()
                    answer = re.sub(r'^<!-- carry-review: .*? -->\r?\n?', '', answer, flags=re.M).strip()
                    answer = re.sub(r'^(?:- \[ \] .*|(?:Good day|Day satisfaction|Productive day): unrated|(?:Day satisfaction|Productivity) scale: 10)\r?$', '', answer, flags=re.M).strip()
                    statuses[period] = 'written' if answer else ('blank' if start is not None else 'missing')
                evening = record['sections']['evening']
                ratings = re.search(r'^### Daily ratings\r?\n\s*(?:Good day|Day satisfaction): (10|[1-9]|unrated)(?:\r?\nDay satisfaction scale: (10))?\r?\nProductive day: (10|[1-9]|unrated)(?:\r?\nProductivity scale: (10))?', evening, re.M)
                if ratings:
                    good, good_scale, productive, productivity_scale = ratings.groups()
                    metrics = {'good': int(good) if good != 'unrated' else None,
                               'productive': int(productive) if productive != 'unrated' else None}
                    if good_scale is None and metrics['good'] is not None:
                        metrics['good'] = RATING_1_TO_10.get(metrics['good'], metrics['good'])
                    if productivity_scale is None and metrics['productive'] is not None:
                        metrics['productive'] = RATING_1_TO_10.get(metrics['productive'], metrics['productive'])
                else:
                    metrics = {'good':None,'productive':None}
                entries.append({'date': path.stem, **statuses, **metrics})
            except (ValueError, OSError):
                entries.append({'date': path.stem, 'morning': 'needs review', 'evening': 'needs review'})
        return entries
