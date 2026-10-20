"""One-time, backed-up migration from 1–5 to 1–10 productivity ratings."""
from datetime import datetime
import os
from pathlib import Path
import re
import tempfile


MAPPING = {'1': '1', '2': '3', '3': '6', '4': '8', '5': '10'}
RATING = re.compile(r'^(Productive day: )(10|[1-9]|unrated)(\r?\n)', re.M)
SCALE = re.compile(r'^Productivity scale: (\d+)\r?$', re.M)


def normalize_text(text):
    scale = SCALE.search(text)
    if scale:
        if scale.group(1) != '10':
            raise ValueError(f'Unsupported productivity scale: {scale.group(1)}')
        return text

    def replace(match):
        value = match.group(2)
        normalized = MAPPING.get(value, value)
        return f'{match.group(1)}{normalized}{match.group(3)}Productivity scale: 10{match.group(3)}'

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
        fd, temporary = tempfile.mkstemp(prefix='.productivity-', suffix='.tmp', dir=path.parent)
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

    target = ROOT / 'data' / 'backups' / ('productivity-scale-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    count = migrate(configured_vault(), target)
    print(f'Updated {count} notes; original copies backed up in {target}')
