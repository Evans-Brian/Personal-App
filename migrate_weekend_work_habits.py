"""Remove work-specific phone/game answers from Saturday and Sunday evenings."""
from datetime import date, datetime, timezone
import json
from pathlib import Path
import re
from urllib.parse import quote, unquote

from migrate_evening_prompts import migrate as migrate_sections, plan_changes as plan_sections

WORK_KEYS = ('phone_game_before_morning_work', 'phone_game_before_afternoon_work')
HABITS = re.compile(r'<!-- evening-habits: (.*?) -->')


def normalize_text(text, day):
    try:
        weekend = date.fromisoformat(day).weekday() >= 5
    except (TypeError, ValueError) as error:
        raise ValueError('Choose a valid journal date.') from error
    if not weekend:
        return text

    def clean(match):
        try:
            value = json.loads(unquote(match[1]))
        except (ValueError, TypeError) as error:
            raise ValueError('Repair invalid evening habit metadata before updating it.') from error
        if not isinstance(value, dict):
            raise ValueError('Evening habit metadata must be an object.')
        if not any(key in value for key in WORK_KEYS):
            return match[0]
        value = {key: answer for key, answer in value.items() if key not in WORK_KEYS}
        if not value:
            return ''
        encoded = quote(json.dumps(value, ensure_ascii=False, separators=(',', ':')), safe="~()*!.'-")
        return '<!-- evening-habits: ' + encoded + ' -->'

    return HABITS.sub(clean, text)


def plan_changes(vault):
    return plan_sections(vault, normalize_text)


def migrate(vault, backup_root):
    return migrate_sections(vault, backup_root, normalize_text)


if __name__ == '__main__':
    import argparse
    from app import configured_vault, ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vault', type=Path)
    parser.add_argument('--backup-root', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    vault = args.vault or configured_vault()
    if args.apply:
        backup = args.backup_root or ROOT / 'data/backups' / ('weekend-work-habits-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        print(f'Updated {migrate(vault, backup)} weekend notes. Original copies: {backup}')
    else:
        print(f'{len(plan_changes(vault))} weekend notes would be updated. No files changed.')
