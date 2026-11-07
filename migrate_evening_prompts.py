"""Combine evening reflection prompts, with private backups for stored notes."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile

COMBINED_PROMPT = 'What made me happy, grateful, engaged, or connected?'
MERGED_PROMPTS = {
    'What made me happy or grateful today?': 'Happy / grateful',
    'When did I feel most engaged or connected today?': 'Engaged / connected',
    'What moment would I like to remember?': 'Memory',
    'What did I learn today—about myself, someone else, or the world?': 'Something learned',
}


def normalize_text(text):
    """Retain answers and control metadata; combine only recognized questions."""
    boundaries, offset, fence = [], 0, None
    for line in text.splitlines(keepends=True):
        plain = line.rstrip('\r\n')
        if fence:
            if re.fullmatch(r' {0,3}' + re.escape(fence[0]) + '{' + str(fence[1]) + r',}[ \t]*', plain):
                fence = None
        else:
            opening = re.match(r' {0,3}(`{3,}|~{3,})', plain)
            heading = re.fullmatch(r'### (.+)', plain)
            control = re.fullmatch(r'<!-- (?:evening-habits|evening-jo): .*? -->[ \t]*', plain)
            if opening:
                fence = (opening[1][0], len(opening[1]))
            elif heading or control:
                boundaries.append((offset, offset + len(line), heading[1].strip() if heading else None))
        offset += len(line)
    targets = set(MERGED_PROMPTS) | {COMBINED_PROMPT}
    selected = [title for _, _, title in boundaries if title in targets]
    if not selected or (selected == [COMBINED_PROMPT]):
        return text
    blocks = [(start, body, boundaries[index+1][0] if index+1 < len(boundaries) else len(text), title)
              for index, (start, body, title) in enumerate(boundaries)]
    combined, answers = [], {title: [] for title in MERGED_PROMPTS}
    for start, body, end, title in blocks:
        answer = text[body:end].strip()
        if not answer:
            continue
        if title == COMBINED_PROMPT:
            combined.append(answer)
        elif title in answers:
            answers[title].append(answer)
    newline = '\r\n' if '\r\n' in text else '\n'
    for title, label in MERGED_PROMPTS.items():
        if answers[title]:
            combined.append(label + ':' + newline + (newline * 2).join(answers[title]))
    merged = '### ' + COMBINED_PROMPT + newline * 2 + (newline * 2).join(combined) + newline * 2
    output, inserted = [text[:boundaries[0][0]]], False
    for start, body, end, title in blocks:
        if title in targets:
            if not inserted:
                output.append(merged)
                inserted = True
        else:
            output.append(text[start:end])
    return ''.join(output)


def plan_changes(vault):
    from journal import Journal
    vault = Path(vault).resolve()
    changes = []
    for path in sorted((vault / 'Journal').glob('????-??-??.md')):
        if not path.resolve().is_relative_to(vault / 'Journal'):
            raise ValueError('Journal path is outside the journal folder.')
        raw = path.read_bytes()
        text = raw.decode('utf-8')
        start, end = Journal.bounds(text, 'evening')
        if start is None:
            continue
        updated = (text[:start] + normalize_text(text[start:end]) + text[end:]).encode('utf-8')
        if updated != raw:
            changes.append((path, raw, updated))
    return changes


def migrate(vault, backup_root):
    changes = plan_changes(vault)
    if not changes:
        return 0
    backup = Path(backup_root).resolve()
    if backup.is_relative_to((Path(vault).resolve() / 'Journal')):
        raise ValueError('Keep migration backups outside the journal folder.')
    backup.mkdir(parents=True, exist_ok=False)
    # Back up every original before changing the first note. Never overwrite a backup.
    manifest = {}
    for path, raw, updated in changes:
        (backup / path.name).write_bytes(raw)
        manifest[path.name] = {'before_sha256': sha256(raw).hexdigest(), 'after_sha256': sha256(updated).hexdigest()}
    (backup / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    for path, raw, updated in changes:
        fd, temporary = tempfile.mkstemp(prefix='.evening-prompts-', suffix='.tmp', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as handle:
                handle.write(updated)
                handle.flush()
                os.fsync(handle.fileno())
            if path.read_bytes() != raw:
                raise RuntimeError('Note changed during migration; stopped without overwriting that note.')
            os.replace(temporary, path)
            assert path.read_bytes() == updated
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return len(changes)


if __name__ == '__main__':
    import argparse
    from app import configured_vault, ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vault', type=Path)
    parser.add_argument('--backup-root', type=Path)
    parser.add_argument('--apply', action='store_true', help='Back up and update notes; otherwise preview the count only.')
    args = parser.parse_args()
    vault = args.vault or configured_vault()
    if args.apply:
        backup = args.backup_root or ROOT / 'data' / 'backups' / ('evening-prompts-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        print(f'Updated {migrate(vault, backup)} notes. Original copies: {backup}')
    else:
        print(f'{len(plan_changes(vault))} evening notes would be updated. No files changed.')
