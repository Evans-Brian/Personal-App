"""One-time, backed-up migration from Good day 1–5 to Day satisfaction 1–10."""
from datetime import datetime
import os
from pathlib import Path
import re
import tempfile


MAPPING = {'1': '1', '2': '3', '3': '6', '4': '8', '5': '10'}
RATING = re.compile(r'^(Good day|Day satisfaction): (10|[1-9]|unrated)(\r?\n)', re.M)
SCALE = re.compile(r'^Day satisfaction scale: (\d+)\r?$', re.M)


def normalize_text(text):
    scale = SCALE.search(text)
    if scale:
        if scale.group(1) != '10':
            raise ValueError(f'Unsupported day satisfaction scale: {scale.group(1)}')
        return re.sub(r'^Good day:', 'Day satisfaction:', text, count=1, flags=re.M)

    def replace(match):
        value = MAPPING.get(match.group(2), match.group(2))
        newline = match.group(3)
        return f'Day satisfaction: {value}{newline}Day satisfaction scale: 10{newline}'

    return RATING.sub(replace, text, count=1)


def migrate(vault, backup_root):
    vault = Path(vault).resolve()
    journal = vault / 'Journal'
    backup = Path(backup_root).resolve()
    changed = 0
    for path in sorted(journal.glob('????-??-??.md')):
        if not path.resolve().is_relative_to(vault):
            raise ValueError('Note path is outside the vault')
        raw = path.read_bytes()
        updated = normalize_text(raw.decode('utf-8')).encode('utf-8')
        if updated == raw:
            continue
        backup.mkdir(parents=True, exist_ok=True)
        (backup / path.name).write_bytes(raw)
        fd, temporary = tempfile.mkstemp(prefix='.day-satisfaction-', suffix='.tmp', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as handle:
                handle.write(updated)
                handle.flush()
                os.fsync(handle.fileno())
            if path.read_bytes() != raw:
                raise RuntimeError('Note changed during migration; stopped without overwriting it.')
            os.replace(temporary, path)
            changed += 1
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return changed


if __name__ == '__main__':
    from app import configured_vault, ROOT

    target = ROOT / 'data' / 'backups' / ('day-satisfaction-scale-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    count = migrate(configured_vault(), target)
    print(f'Updated {count} notes; original copies backed up in {target}')
