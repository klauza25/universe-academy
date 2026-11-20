"""Synchronise Google Sheets au plus une fois tous les trois jours."""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

INTERVAL = timedelta(days=3)
STATE_FILE = (
    Path.home() / '.local' / 'state' / 'academy'
    / 'google-sheets-sync-last-success'
)
PROJECT_DIR = Path(__file__).resolve().parents[1]


def run_sync(state_file: Path, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    if state_file.exists():
        last_success = datetime.fromisoformat(
            state_file.read_text(encoding='utf-8').strip())
        next_sync = last_success + INTERVAL
        if now < next_sync:
            print(f'Synchronisation non due avant {next_sync.isoformat()}.')
            return 0

    commands = (
        [sys.executable, str(PROJECT_DIR / 'manage.py'), 'migrer'],
        [sys.executable, str(PROJECT_DIR / 'manage.py'),
         'synchroniser_classeurs', '--ecrire'],
    )
    for command in commands:
        subprocess.run(command, cwd=PROJECT_DIR, check=True)

    state_file.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = state_file.with_name(
        f'.{state_file.name}.{os.getpid()}.tmp')
    try:
        temporary_file.write_text(now.isoformat(), encoding='utf-8')
        temporary_file.replace(state_file)
    finally:
        temporary_file.unlink(missing_ok=True)

    print(f'Synchronisation réussie à {now.isoformat()}.')
    return 0


if __name__ == '__main__':
    raise SystemExit(run_sync(STATE_FILE))
