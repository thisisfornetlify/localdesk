from __future__ import annotations

import csv
from contextlib import contextmanager
import hashlib
import importlib
import io
import json
import os
import re
import secrets
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get('LOCALDESK_DATA', str(BASE / 'data'))).resolve()
LOCK = threading.RLock()


class ToolError(ValueError):
    pass


def initialize():
    for folder in ('exports', 'uploads', 'trash'):
        (DATA / folder).mkdir(parents=True, exist_ok=True)
    with connection() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS records (
          id TEXT PRIMARY KEY, kind TEXT NOT NULL, created REAL NOT NULL, body TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS records_kind ON records(kind, created);
        CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY, name TEXT, tool TEXT, payload TEXT, interval REAL,
          next_run REAL, enabled INTEGER, last_run REAL, status TEXT, result TEXT);
        ''')


@contextmanager
def connection():
    db = sqlite3.connect(DATA / 'localdesk.sqlite3', timeout=20)
    db.row_factory = sqlite3.Row
    try:
        db.execute('PRAGMA journal_mode=WAL')
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def add(kind, body, identifier=None):
    identifier = identifier or secrets.token_hex(12)
    with connection() as db:
        db.execute('INSERT INTO records VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET kind=excluded.kind,body=excluded.body',
                   (identifier, kind, time.time(), json.dumps(body, ensure_ascii=False)))
    return identifier


def records(kind, limit=1000):
    with connection() as db:
        rows = db.execute('SELECT * FROM records WHERE kind=? ORDER BY created DESC LIMIT ?',
                          (kind, limit)).fetchall()
    return [dict(json.loads(r['body']), id=r['id'], _created=r['created']) for r in rows]


def remove(kind, identifier):
    with connection() as db:
        db.execute('DELETE FROM records WHERE id=? AND kind=?', (identifier, kind))


def get(key, default=None):
    with connection() as db:
        row = db.execute('SELECT value FROM kv WHERE key=?', (key,)).fetchone()
    return json.loads(row[0]) if row else default


def put(key, value):
    with connection() as db:
        db.execute('INSERT OR REPLACE INTO kv VALUES (?,?)', (key, json.dumps(value)))


def notify(title, message):
    add('notification', {'title': title, 'message': str(message)[:2000], 'read': False})


def need(module, package=None):
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        raise ToolError(f'This action needs {package or module}. Run: python -m pip install -r requirements.txt') from exc


def required(p, name):
    value = p.get(name)
    if value is None or str(value).strip() == '':
        raise ToolError(f'{name.replace("_", " ").capitalize()} is required.')
    return value


def number(p, name, default, low=None, high=None, integer=False):
    try:
        v = float(p.get(name, default) if p.get(name) not in (None, '') else default)
    except (TypeError, ValueError):
        raise ToolError(f'{name} must be a number.')
    import math
    if not math.isfinite(v) or (low is not None and v < low) or (high is not None and v > high):
        raise ToolError(f'{name} must be between {low} and {high}.')
    return int(v) if integer else v


def path(value, directory=False):
    if not value:
        raise ToolError('Choose a local path or upload a file.')
    p = Path(str(value)).expanduser()
    if p.is_symlink():
        raise ToolError('Use a regular path, not a symbolic link.')
    p = p.resolve()
    if not p.exists() or (directory and not p.is_dir()) or (not directory and not p.is_file()):
        raise ToolError(f'{"Folder" if directory else "File"} does not exist: {p}')
    return p


def walk(root, recursive=True, limit=20000):
    root = path(root, True)
    count = 0
    ignored = {'.git', '.venv', 'venv', 'node_modules', '__pycache__', '.trash'}
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in sorted(dirs) if d not in ignored and not (Path(current) / d).is_symlink()
                   and not (Path(current) / d).resolve().is_relative_to(DATA)]
        for name in sorted(files):
            f = Path(current) / name
            if f.is_symlink() or f.resolve().is_relative_to(DATA):
                continue
            count += 1
            if count > limit:
                raise ToolError(f'Folder exceeds {limit:,} files; select a smaller folder.')
            yield f
        if not recursive:
            break


def read_text(p, max_bytes=12_000_000):
    p = path(p)
    if p.stat().st_size > max_bytes:
        raise ToolError(f'File is larger than {max_bytes // 1_000_000} MB.')
    return p.read_text(encoding='utf-8-sig', errors='replace')


def digest(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def fingerprint(p):
    p = path(p)
    return {'size': p.stat().st_size, 'sha256': digest(p)}


def make_plan(moves, title):
    seen = set()
    for move in moves:
        src, dst = Path(move['source']).resolve(), Path(move['destination']).resolve()
        if src == dst or str(dst).casefold() in seen or dst.exists():
            raise ToolError(f'Conflicting destination: {dst}. Change the pattern or target folder.')
        if src.is_relative_to(DATA) and not src.is_relative_to(DATA / 'trash'):
            raise ToolError('Application data cannot be moved by file tools.')
        seen.add(str(dst).casefold())
        move['source'], move['destination'] = str(src), str(dst)
        move['fingerprint'] = fingerprint(src)
    identifier = add('plan', {'moves': moves, 'title': title, 'applied': False})
    return {'message': f'{len(moves)} file changes ready to review.', 'plan_id': identifier,
            'changes': [{k: v for k, v in m.items() if k != 'fingerprint'} for m in moves]}


def apply_plan(identifier):
    import shutil
    with LOCK:
        plan = next((r for r in records('plan') if r['id'] == identifier), None)
        if not plan or plan['applied'] or time.time() - plan['_created'] > 3600:
            raise ToolError('Preview expired or already applied. Create a fresh preview.')
        for m in plan['moves']:
            src, dst = Path(m['source']), Path(m['destination'])
            if fingerprint(src) != m['fingerprint'] or dst.exists():
                raise ToolError('Files changed since preview. Nothing was moved; preview again.')
        completed = []
        try:
            for m in plan['moves']:
                dst = Path(m['destination'])
                dst.parent.mkdir(parents=True, exist_ok=True)
                # Recheck immediately before each move. Never intentionally overwrite.
                if dst.exists():
                    raise ToolError(f'Destination now exists: {dst}')
                move_without_overwrite(m['source'], m['destination'])
                completed.append(m)
        except Exception as exc:
            failures = []
            for m in reversed(completed):
                try:
                    if Path(m['source']).exists():
                        raise ToolError('Original path now occupied')
                    move_without_overwrite(m['destination'], m['source'])
                except Exception:
                    failures.append(m)
            if failures:
                add('recovery', {'moves': failures, 'error': str(exc)})
            raise ToolError(f'Move failed. Rollback failures: {len(failures)}. {exc}') from exc
        plan['applied'] = True
        add('plan', {k: v for k, v in plan.items() if k not in ('id', '_created')}, identifier)
        journal = add('journal', {'title': plan['title'], 'moves': plan['moves']})
        return {'message': f'Applied {len(completed)} changes.', 'journal_id': journal,
                'note': 'Use File history → Preview undo to reverse these changes.'}


def move_without_overwrite(source, destination):
    """Exclusive destination creation also protects against a late external name collision."""
    import shutil
    destination = Path(destination)
    created = False
    try:
        with open(source, 'rb') as src, open(destination, 'xb') as dst:
            created = True
            shutil.copyfileobj(src, dst, 1024 * 1024)
        if digest(source) != digest(destination):
            raise ToolError('File changed during copy; original retained.')
        shutil.copystat(source, destination)
        Path(source).unlink()
    except Exception:
        if created:
            destination.unlink(missing_ok=True)
        raise


def undo_plan(identifier):
    r = next((r for r in records('journal') if r['id'] == identifier), None)
    if not r:
        raise ToolError('History entry not found.')
    return make_plan([{'source': m['destination'], 'destination': m['source']} for m in r['moves']],
                     'Undo ' + r['title'])


def export(name, content, binary=False):
    name = re.sub(r'[^\w.\-]', '_', name)
    target = DATA / 'exports' / f'{secrets.token_hex(5)}-{name}'
    if binary:
        target.write_bytes(content)
    else:
        target.write_text(str(content), encoding='utf-8')
    return {'name': name, 'url': '/download/' + target.name, 'path': str(target)}


def export_csv(name, rows, columns=None):
    columns = columns or list(dict.fromkeys(k for row in rows for k in row))
    s = io.StringIO(newline='')
    w = csv.DictWriter(s, columns, extrasaction='ignore')
    w.writeheader()
    for row in rows:
        # Prevent spreadsheet formula execution when opening generated CSV exports.
        w.writerow({k: ("'" + v if isinstance(v, str) and v.startswith(('=', '+', '-', '@')) else v)
                    for k, v in row.items()})
    return export(name, s.getvalue())


def http(url, method='GET', body=None, headers=None, timeout=25, max_bytes=15_000_000):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username:
        raise ToolError('Use an http:// or https:// URL without embedded credentials.')
    hdr = {'User-Agent': 'LocalDesk/1.0', **(headers or {})}
    if isinstance(body, (dict, list)):
        body = json.dumps(body).encode()
        hdr.setdefault('Content-Type', 'application/json')
    elif isinstance(body, str):
        body = body.encode()
    request = urllib.request.Request(url, data=body, method=method, headers=hdr)
    start = time.monotonic()
    try:
        response = urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as e:
        response = e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        # Do not echo token-bearing URLs (e.g. Telegram bot URLs) into logs/UI.
        raise ToolError(f'Could not connect to {parsed.hostname}. Check its address, credentials, and network.') from e
    with response:
        data = response.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ToolError('Response exceeds the 15 MB limit.')
        return {'status': response.status, 'headers': dict(response.headers),
                'text': data.decode('utf-8', errors='replace'), 'bytes': data,
                'elapsed_ms': round((time.monotonic() - start) * 1000)}


def fetch_json(url, body=None, method=None, headers=None, timeout=45):
    r = http(url, method or ('POST' if body is not None else 'GET'), body, headers, timeout)
    if r['status'] >= 400:
        raise ToolError(f'{urllib.parse.urlsplit(url).hostname} returned HTTP {r["status"]}. Check configuration.')
    try:
        return json.loads(r['text'])
    except ValueError:
        raise ToolError('Service did not return valid JSON.')


def env(name, default=None):
    v = os.environ.get(name, default)
    if not v:
        raise ToolError(f'Set {name} in .env, then restart LocalDesk. See Settings for setup.')
    return v


def iso_today():
    return datetime.now().date().isoformat()


def load_env():
    global DATA
    f = BASE / '.env'
    if f.exists():
        for line in f.read_text(encoding='utf-8-sig').splitlines():
            if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))
    DATA = Path(os.environ.get('LOCALDESK_DATA') or str(BASE / 'data')).resolve()
