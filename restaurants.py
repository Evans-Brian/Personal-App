"""Local restaurant collection stored separately from daily journal notes."""
from datetime import date
import json
import os
import tempfile
import threading
from hashlib import sha256
from pathlib import Path
from journal import Conflict


class Restaurants:
    def __init__(self, vault):
        self.vault = Path(vault).resolve()
        self.path = self.vault / 'Restaurants' / 'restaurants.json'
        self.lock = threading.Lock()

    def read(self):
        if not self.path.resolve().is_relative_to(self.vault):
            raise ValueError('Restaurant storage must stay inside the vault.')
        raw = self.path.read_bytes() if self.path.exists() else b''
        return {'restaurants': json.loads(raw)['restaurants'] if raw else [], 'revision': sha256(raw).hexdigest()}

    @staticmethod
    def validate(rows):
        if not isinstance(rows, list) or len(rows) > 2000:
            raise ValueError('Invalid restaurant list.')
        ids = set()
        def item(value, restaurant=False):
            if not isinstance(value, dict):
                raise ValueError('Invalid restaurant or dish.')
            identifier = value.get('id')
            if not isinstance(identifier, str) or not identifier or len(identifier) > 80 or identifier in ids:
                raise ValueError('Each restaurant and dish needs a unique ID.')
            ids.add(identifier)
            name = value.get('name')
            if not isinstance(name, str) or not name.strip() or len(name) > 200:
                raise ValueError('Enter a name (up to 200 characters) for each restaurant and dish.')
            result = {'id': identifier, 'name': name.strip()}
            for person in ('you', 'ashley'):
                review = value.get(person)
                if review is None and person == 'ashley':
                    result[person] = None
                    continue
                if not isinstance(review, dict):
                    raise ValueError('Invalid review.')
                score = review.get('score')
                if score is not None and (type(score) is not int or score not in range(1, 6)):
                    raise ValueError('Scores must be from 1 to 5, or left unrated.')
                result[person] = {'score': score}
                for field in ('review', 'thoughts'):
                    text = review.get(field, '')
                    if not isinstance(text, str) or len(text) > (40000 if field == 'thoughts' else 20000):
                        raise ValueError('Thoughts must be text, up to 40,000 characters.')
                    result[person][field] = text
            if restaurant:
                visit_date = value.get('date')
                if not isinstance(visit_date, str) or len(visit_date) != 10:
                    raise ValueError('Choose a restaurant visit date.')
                date.fromisoformat(visit_date)
                result['date'] = visit_date
                dishes = value.get('dishes')
                if not isinstance(dishes, list) or len(dishes) > 2000:
                    raise ValueError('Invalid dish list.')
                result['dishes'] = [item(dish) for dish in dishes]
            return result
        return [item(row, True) for row in rows]

    def save(self, rows, revision):
        rows = self.validate(rows)
        with self.lock:
            if self.read()['revision'] != revision:
                raise Conflict('Restaurants changed in another tab. Your draft is safe; copy your changes before reloading.')
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix='.restaurants-', suffix='.tmp', dir=self.path.parent)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                    json.dump({'version': 1, 'restaurants': rows}, handle, indent=2, ensure_ascii=False)
                    handle.flush()
                    os.fsync(handle.fileno())
                if self.read()['revision'] != revision:
                    raise Conflict('Restaurants changed during saving. Your draft has not overwritten them.')
                os.replace(temporary, self.path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            return self.read()
