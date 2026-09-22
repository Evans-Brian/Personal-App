"""People and dated notes: local vault storage with append-only note creation."""
import json
import os
import tempfile
import threading
from datetime import date
from pathlib import Path
from uuid import UUID


class People:
    def __init__(self, vault):
        self.vault = Path(vault).resolve()
        self.path = self.vault / 'People' / 'people.json'
        self.lock = threading.Lock()

    def read(self):
        if not self.path.resolve().is_relative_to(self.vault):
            raise ValueError('People storage must stay in the vault.')
        return json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {'version': 1, 'people': []}

    @staticmethod
    def text(value, label, maximum):
        if not isinstance(value, str) or not value.strip() or len(value) > maximum:
            raise ValueError(f'Enter {label} (up to {maximum} characters).')
        return value.strip()

    def add(self, data):
        identifier = data.get('id')
        if not isinstance(identifier, str):
            raise ValueError('Missing entry ID.')
        UUID(identifier)
        action = data.get('action')
        if action == 'person':
            record = {'id': identifier, 'name': self.text(data.get('name'), 'a name', 200),
                      'relation': self.text(data.get('relation'), 'a relation', 300), 'notes': []}
        elif action == 'relation':
            record = {'relation': self.text(data.get('relation'), 'a relation', 300)}
        elif action == 'note':
            day = data.get('date')
            if not isinstance(day, str) or len(day) != 10:
                raise ValueError('Choose a note date.')
            date.fromisoformat(day)
            record = {'id': identifier, 'date': day, 'text': self.text(data.get('text'), 'a note', 40000)}
        else:
            raise ValueError('Unknown People action.')
        with self.lock:
            current = self.read()
            if action == 'person':
                target = current['people']
            else:
                person = next((p for p in current['people'] if p['id'] == data.get('person_id')), None)
                if person is None:
                    raise ValueError('That person no longer exists. Reload People before saving.')
                target = person['notes']
            if action == 'relation':
                if person['relation'] != record['relation'] and person['relation'] != data.get('previous_relation'):
                    raise ValueError('This relation changed elsewhere. Reload People before trying again.')
                person['relation'] = record['relation']
            existing = next((r for r in target if r['id'] == identifier), None) if action != 'relation' else None
            if existing:
                if any(existing[k] != v for k, v in record.items() if k != 'notes'):
                    raise ValueError('This entry ID was already saved with different content. Reload before retrying.')
                return current
            if action != 'relation':
                target.append(record)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix='.people-', suffix='.tmp', dir=self.path.parent)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                    json.dump(current, handle, ensure_ascii=False, indent=2)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, self.path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            return current
