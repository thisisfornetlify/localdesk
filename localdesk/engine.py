from __future__ import annotations

import json
import threading
import time
import secrets

from . import core
from .catalog import BY_ID
from .tools import advanced, creative, data, developer, files, productivity

HANDLERS = {**files.HANDLERS, **productivity.HANDLERS, **developer.HANDLERS,
            **data.HANDLERS, **creative.HANDLERS, **advanced.HANDLERS}
STOP = threading.Event()
JOB_SLOTS = threading.BoundedSemaphore(4)


def execute(tool, payload):
    if tool not in BY_ID:
        raise core.ToolError('Unknown tool.')
    action = payload.get('action') or BY_ID[tool]['actions'][0]['key']
    if action not in {a['key'] for a in BY_ID[tool]['actions']}:
        raise core.ToolError('Unknown action.')
    payload = {**payload, 'action': action}
    if tool == 'scrape' and action == 'history':
        return {'runs': core.records('scrape', 50)}
    result = HANDLERS[tool](payload)
    if tool != 'passwords':
        # Do not persist request inputs or outputs in the activity log.
        core.add('activity', {'tool': tool, 'action': action, 'time': time.time()})
        with core.connection() as db:
            db.execute("DELETE FROM records WHERE kind='activity' AND id NOT IN (SELECT id FROM records WHERE kind='activity' ORDER BY created DESC LIMIT 500)")
    return result


def jobs():
    with core.connection() as db:
        rows = db.execute('SELECT * FROM jobs ORDER BY next_run').fetchall()
    return [{**dict(row), 'payload': json.loads(row['payload']),
             'result': json.loads(row['result']) if row['result'] else None} for row in rows]


def save_job(p):
    tool = core.required(p, 'tool')
    payload = p.get('payload', {})
    if not isinstance(payload, dict):
        raise core.ToolError('Job payload must be a JSON object.')
    action = payload.get('action')
    spec = next((a for a in BY_ID.get(tool, {}).get('actions', []) if a['key'] == action and a.get('schedule')), None)
    if not spec:
        raise core.ToolError('This action cannot run in the background.')
    interval = core.number(p, 'interval', 3600, 0, 31536000)
    if interval != 0 and interval < 15:
        raise core.ToolError('Use at least 15 seconds between recurring runs; 0 means once.')
    delay = core.number(p, 'delay', interval or 60, 1, 31536000)
    identifier = secrets.token_hex(12)
    with core.connection() as db:
        db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?)',
                   (identifier, p.get('name') or BY_ID[tool]['name'], tool, json.dumps(payload), interval,
                    time.time()+delay, 1, None, 'Scheduled', None))
    return {'message': 'Schedule saved. Keep LocalDesk running for it to execute.', 'job_id': identifier}


def job_action(p):
    identifier, action = core.required(p, 'id'), core.required(p, 'action')
    with core.connection() as db:
        if action == 'delete':
            db.execute('DELETE FROM jobs WHERE id=?', (identifier,))
        elif action in ('pause', 'resume', 'run'):
            if action == 'pause':
                db.execute('UPDATE jobs SET enabled=0 WHERE id=?', (identifier,))
            else:
                db.execute('UPDATE jobs SET enabled=1,next_run=? WHERE id=?',
                           (time.time() + (1 if action == 'run' else 15), identifier))
        else:
            raise core.ToolError('Unknown schedule action.')
    return {'message': 'Schedule updated.'}


def run_job(job):
    try:
        result = execute(job['tool'], job['payload'])
        status = 'Succeeded'
        # Full snapshots are kept by their tool, not repeatedly duplicated in jobs.
        summary = {k: v for k, v in result.items() if k in ('message','changed','row_count','run_id','note')}
        if not summary:
            summary = {'message': 'Completed successfully.'}
    except Exception as exc:
        status = 'Failed'
        summary = {'error': str(exc) if isinstance(exc, core.ToolError) else type(exc).__name__ + ': check service configuration and inputs.'}
        core.notify('Schedule failed · ' + job['name'], summary['error'])
    with core.connection() as db:
        db.execute('UPDATE jobs SET status=?,result=?,last_run=? WHERE id=?',
                   (status, json.dumps(summary), time.time(), job['id']))


def job_thread(job):
    try:
        run_job(job)
    finally:
        JOB_SLOTS.release()


def tick_jobs():
    now = time.time()
    for job in jobs():
        if not job['enabled'] or job['next_run'] > now or job['status'] == 'Running':
            continue
        if not JOB_SLOTS.acquire(blocking=False):
            break
        # Claim before dispatch, skip missed intervals rather than replaying external side effects.
        with core.connection() as db:
            changed = db.execute('UPDATE jobs SET status=?,next_run=?,enabled=? WHERE id=? AND status<>?',
                ('Running', now+max(15, job['interval']), int(job['interval'] > 0), job['id'], 'Running')).rowcount
        if changed:
            threading.Thread(target=job_thread, args=(job,), daemon=True).start()
        else:
            JOB_SLOTS.release()


def tick_local():
    timer = core.get('timer')
    if timer and not timer.get('notified') and time.time() >= timer['start'] + timer['minutes'] * 60:
        core.notify('Focus session complete', timer['task'] + ' · take a break. Stop the timer to save your time.')
        with core.LOCK:
            current = core.get('timer')
            if current and current['start'] == timer['start']:
                current['notified'] = True
                core.put('timer', current)
    for r in core.records('bot_reminder', 1000):
        if not r['sent'] and r['at'] <= time.time():
            # Fail closed against duplicate sends after ambiguous network failures; user can inspect notification.
            core.add('bot_reminder', {**r, 'sent': True}, r['id'])
            try:
                creative.telegram('sendMessage', {'chat_id': core.env('TELEGRAM_CHAT_ID'), 'text': r['message']})
            except Exception:
                core.notify('Bot reminder delivery failed', r['message'])


def clipboard_worker():
    previous = None
    while not STOP.wait(1):
        if not core.get('clipboard_enabled', False):
            previous = None
            continue
        try:
            text = core.need('pyperclip').paste()
            if text and text != previous:
                core.add('clipboard', {'text': str(text)[:100000]})
                previous = text
                with core.connection() as db:
                    db.execute("DELETE FROM records WHERE kind='clipboard' AND id NOT IN (SELECT id FROM records WHERE kind='clipboard' ORDER BY created DESC LIMIT 1000)")
        except Exception:
            core.put('clipboard_enabled', False)
            core.notify('Clipboard capture stopped', 'Clipboard access failed. Check the system clipboard and pyperclip dependency.')


def worker():
    while not STOP.wait(2):
        try:
            tick_local()
            tick_jobs()
        except Exception:
            # Keep scheduler alive through transient DB/service faults.
            pass


def start_workers():
    STOP.clear()
    core.put('clipboard_enabled', False)
    with core.connection() as db:
        # An interrupted external request is not blindly replayed after restart.
        db.execute("UPDATE jobs SET status='Interrupted — review before resuming',enabled=0 WHERE status='Running'")
    threading.Thread(target=worker, daemon=True).start()
    threading.Thread(target=clipboard_worker, daemon=True).start()
