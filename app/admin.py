from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import QueryOptions, SearchAuditEvent

DATA_DIR = Path('.appdata')
USERS_FILE = DATA_DIR / 'users.json'
AUDIT_FILE = DATA_DIR / 'audit.jsonl'
DEFAULTS_FILE = DATA_DIR / 'defaults.json'


def _ensure_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def create_account(username: str, role: str, account_type: str = 'human') -> dict[str, Any]:
    _ensure_dir()
    users = []
    if USERS_FILE.exists():
        users = json.loads(USERS_FILE.read_text())
    entry = {
        'username': username,
        'role': role,
        'account_type': account_type,
        'created_at': datetime.utcnow().isoformat(),
    }
    users.append(entry)
    USERS_FILE.write_text(json.dumps(users, indent=2))
    return entry


def append_audit(event: SearchAuditEvent) -> None:
    _ensure_dir()
    with AUDIT_FILE.open('a', encoding='utf-8') as f:
        f.write(json.dumps(asdict(event)) + '\n')


def audit_window(start_iso: str, end_iso: str) -> list[dict[str, Any]]:
    if not AUDIT_FILE.exists():
        return []
    start = datetime.fromisoformat(start_iso)
    end = datetime.fromisoformat(end_iso)
    rows: list[dict[str, Any]] = []
    for line in AUDIT_FILE.read_text().splitlines():
        obj = json.loads(line)
        ts = datetime.fromisoformat(obj['timestamp_iso'])
        if start <= ts <= end:
            rows.append(obj)
    return rows


def set_defaults(options: QueryOptions) -> dict[str, Any]:
    _ensure_dir()
    payload = asdict(options)
    DEFAULTS_FILE.write_text(json.dumps(payload, indent=2))
    return payload


def load_defaults() -> QueryOptions:
    if not DEFAULTS_FILE.exists():
        return QueryOptions()
    data = json.loads(DEFAULTS_FILE.read_text())
    return QueryOptions(**data)
