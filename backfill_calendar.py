"""One-time, backed-up metadata migration for existing journal notes."""
from pathlib import Path
from datetime import datetime
import os
import tempfile
from app import configured_vault, ROOT
from day_context import add_day_context

vault=configured_vault()
backup=ROOT/'data'/'backups'/('calendar-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
count=0
for path in sorted((vault/'Journal').glob('????-??-??.md')):
    if not path.resolve().is_relative_to(vault.resolve()):
        raise ValueError('Note path is outside the vault')
    raw=path.read_bytes()
    updated=add_day_context(raw.decode('utf-8'),path.stem).encode('utf-8')
    if updated==raw:
        continue
    backup.mkdir(parents=True,exist_ok=True)
    (backup/path.name).write_bytes(raw)
    fd,temp=tempfile.mkstemp(prefix='.calendar-',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as handle:
            handle.write(updated)
            handle.flush()
            os.fsync(handle.fileno())
        if path.read_bytes()!=raw:
            raise RuntimeError('Note changed during migration; stopped without overwriting it.')
        os.replace(temp,path)
        count+=1
    finally:
        if os.path.exists(temp): os.unlink(temp)
print(f'Updated {count} notes; original copies backed up in {backup}')
