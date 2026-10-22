"""Run: python app.py --port 8765. Everything binds to loopback only."""
from __future__ import annotations

import argparse
import importlib.util
import json
import mimetypes
import os
import secrets
import sys
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / '.packages'))

from localdesk import core
core.load_env()
from localdesk import engine
from localdesk.catalog import TOOLS

TOKEN = secrets.token_urlsafe(32)
STATIC = Path(__file__).resolve().parent / 'static'
BUSY = threading.BoundedSemaphore(8)


def system_status():
    modules = [('Pillow', 'PIL'), ('PDF toolkit', 'pypdf'), ('Markdown', 'markdown'),
               ('Web parsing', 'bs4'), ('Excel', 'openpyxl'), ('PDF generation', 'reportlab'),
               ('Clipboard', 'pyperclip'), ('OCR wrapper', 'pytesseract'),
               ('Calendar', 'icalendar'), ('MQTT', 'paho')]
    integrations = {'Email sorting': ['IMAP_HOST','IMAP_USER','IMAP_PASSWORD'],
                    'Email notifications': ['SMTP_HOST','SMTP_FROM','SMTP_TO'],
                    'Telegram bot': ['TELEGRAM_BOT_TOKEN','TELEGRAM_CHAT_ID'],
                    'Discord webhook': ['DISCORD_WEBHOOK_URL'], 'MQTT broker': ['MQTT_HOST']}
    return {'python': sys.version.split()[0], 'data_folder': str(core.DATA),
            'packages': [{'feature': label, 'installed': importlib.util.find_spec(module) is not None} for label, module in modules],
            'integrations': [{'name': label, 'configured': all(os.environ.get(k) for k in keys), 'variables': keys}
                             for label, keys in integrations.items()],
            'ollama_url': os.environ.get('OLLAMA_URL', 'http://127.0.0.1:11434'),
            'ocr_executable': os.environ.get('TESSERACT_CMD', 'tesseract (system PATH)'),
            'note': 'Configured means variables are present; use a tool action to test the connection.'}


class Handler(BaseHTTPRequestHandler):
    server_version = 'LocalDesk/1.0'

    def log_message(self, format, *args):
        # Avoid logging request contents and token-bearing URLs.
        pass

    def trusted(self, mutate=False):
        port = self.server.server_address[1]
        hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
        if self.headers.get('Host', '').lower() not in hosts:
            return False
        origin = self.headers.get('Origin')
        if origin and origin not in {'http://' + h for h in hosts}:
            return False
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            return False
        return not mutate or secrets.compare_digest(self.headers.get('X-LocalDesk-Token', ''), TOKEN)

    def send(self, status, content, content_type='application/json; charset=utf-8', filename=None):
        if isinstance(content, (dict, list)):
            content = json.dumps(content, ensure_ascii=False, default=str).encode('utf-8')
        elif isinstance(content, str):
            content = content.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        if filename:
            self.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + urllib.parse.quote(filename))
        self.end_headers()
        try:
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        if not self.trusted():
            return self.send(403, {'error': 'Only same-origin loopback requests are accepted.'})
        route = urllib.parse.urlsplit(self.path).path
        if route == '/api/bootstrap':
            return self.send(200, {'tools': TOOLS, 'token': TOKEN, 'status': system_status()})
        if route == '/api/overview':
            return self.send(200, {'activity': core.records('activity', 10), 'notifications': core.records('notification', 30),
                                   'jobs': engine.jobs(), 'timer': core.get('timer'),
                                   'tasks': core.records('task'), 'habits': core.records('habit')})
        if route == '/api/jobs':
            return self.send(200, {'jobs': engine.jobs()})
        if route == '/api/status':
            return self.send(200, system_status())
        if route.startswith('/download/'):
            name = urllib.parse.unquote(route[len('/download/'):])
            if not name or '/' in name or '\\' in name or name.startswith('.'):
                return self.send(404, {'error': 'File not found.'})
            target = core.DATA / 'exports' / name
            if not target.is_file():
                return self.send(404, {'error': 'File not found.'})
            return self.send(200, target.read_bytes(), 'application/octet-stream', name)
        asset = 'index.html' if route == '/' else route.lstrip('/')
        target = (STATIC / asset).resolve()
        if not target.is_relative_to(STATIC) or not target.is_file():
            return self.send(404, {'error': 'Page not found.'})
        return self.send(200, target.read_bytes(), mimetypes.guess_type(target.name)[0] or 'application/octet-stream')

    def do_POST(self):
        if not self.trusted(True):
            return self.send(403, {'error': 'Session token or origin rejected. Refresh LocalDesk.'})
        if not BUSY.acquire(blocking=False):
            return self.send(429, {'error': 'Several tools are already running. Try again shortly.'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 <= length <= 60_000_000:
                return self.send(413, {'error': 'Upload limit is 60 MB.'})
            raw = self.rfile.read(length)
            route = urllib.parse.urlsplit(self.path).path
            if route == '/api/upload':
                name = urllib.parse.unquote(self.headers.get('X-Filename', 'upload.bin'))
                name = __import__('re').sub(r'[^\w.\-]', '_', Path(name).name)[:150]
                target = core.DATA / 'uploads' / (secrets.token_hex(8) + '-' + (name or 'upload.bin'))
                target.write_bytes(raw)
                return self.send(200, {'path': str(target), 'name': name})
            p = json.loads(raw or b'{}')
            if not isinstance(p, dict):
                raise core.ToolError('Request must be a JSON object.')
            if route.startswith('/api/run/'):
                result = engine.execute(route.rsplit('/', 1)[-1], p)
            elif route == '/api/files/apply':
                result = core.apply_plan(core.required(p, 'plan_id'))
            elif route == '/api/email/apply':
                result = engine.data.email_sort({'action': 'apply', 'plan_id': core.required(p, 'plan_id')})
            elif route == '/api/jobs/create':
                result = engine.save_job(p)
            elif route == '/api/jobs/action':
                result = engine.job_action(p)
            elif route == '/api/notifications/read':
                for r in core.records('notification', 1000):
                    core.add('notification', {**r, 'read': True}, r['id'])
                result = {'message': 'Notifications marked read.'}
            else:
                return self.send(404, {'error': 'Endpoint not found.'})
            self.send(200, result)
        except (core.ToolError, json.JSONDecodeError) as exc:
            self.send(400, {'error': str(exc)})
        except Exception as exc:
            print(f'Tool failure: {type(exc).__name__}', file=sys.stderr)
            self.send(400, {'error': f'Action failed ({type(exc).__name__}). Check the input file, permissions, or service settings.'})
        finally:
            BUSY.release()


def main():
    parser = argparse.ArgumentParser(description='LocalDesk — a local Python toolbox')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    core.initialize()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    engine.start_workers()
    address = f'http://127.0.0.1:{server.server_address[1]}'
    print(f'LocalDesk is ready at {address}', flush=True)
    print(f'Local data: {core.DATA}', flush=True)
    if not args.no_browser:
        threading.Timer(.5, lambda: webbrowser.open(address)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        engine.STOP.set()
        server.server_close()


if __name__ == '__main__':
    main()
