from __future__ import annotations

import json
import re
import subprocess
from collections import Counter
from pathlib import Path

from ..core import (ToolError, add, export, export_csv, http, make_plan, path,
                    read_text, records, required, walk, number)


def logs(p):
    source = read_text(required(p, 'file'), 50_000_000)
    levels, errors, hours, ips = Counter(), Counter(), Counter(), Counter()
    count = 0
    for line in source.splitlines():
        count += 1
        m = re.search(r'\b(TRACE|DEBUG|INFO|NOTICE|WARN(?:ING)?|ERROR|CRITICAL|FATAL)\b', line, re.I)
        level = m.group(1).upper().replace('WARNING', 'WARN') if m else 'OTHER'
        levels[level] += 1
        hour = re.search(r'(\d{4}-\d\d-\d\d)[T ](\d\d):', line)
        if hour:
            hours[f'{hour[1]} {hour[2]}:00'] += 1
        ip = re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', line)
        if ip:
            ips[ip[0]] += 1
        if level in ('ERROR', 'FATAL', 'CRITICAL'):
            normalized = re.sub(r'\b\d+\b', '#', line)
            errors[normalized[:500]] += 1
    avg = sum(hours.values()) / max(len(hours), 1)
    return {'line_count': count, 'levels': dict(levels), 'top_errors': [{'error': k, 'count': v} for k, v in errors.most_common(30)],
            'top_ips': [{'ip': k, 'count': v} for k, v in ips.most_common(20)],
            'spikes': [{'hour': h, 'count': n} for h, n in sorted(hours.items()) if n >= max(avg * 2, 5)],
            'chart': [{'label': k, 'value': v} for k, v in sorted(hours.items())]}


def api(p):
    action = p.get('action', 'send')
    if action == 'list':
        return {'requests': records('api_request')}
    try:
        headers = json.loads(p.get('headers') or '{}')
        if not isinstance(headers, dict) or any(not isinstance(v, str) for v in headers.values()):
            raise ValueError()
    except ValueError:
        raise ToolError('Headers must be a JSON object of strings.')
    if action == 'save':
        # Authentication headers and bodies can contain secrets; saving requires the explicit Save action.
        identifier = add('api_request', {k: p.get(k, '') for k in ('name', 'url', 'method', 'headers', 'body')})
        return {'message': 'Saved locally, including supplied headers and body.', 'id': identifier}
    url = str(required(p, 'url'))
    method = p.get('method') or 'GET'
    if method not in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'):
        raise ToolError('Unsupported HTTP method.')
    r = http(url, method, p.get('body') or None, headers,
             timeout=number(p, 'timeout', 25, 1, 120))
    return {'status': r['status'], 'elapsed_ms': r['elapsed_ms'], 'headers': r['headers'], 'body': r['text'][:500000]}


def git(p):
    folder = path(required(p, 'folder'), True)
    def run(args):
        try:
            r = subprocess.run(['git', '-C', str(folder), *args], capture_output=True, text=True,
                               encoding='utf-8', errors='replace', timeout=60,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except FileNotFoundError:
            raise ToolError('Install Git and ensure git is on PATH.')
        if r.returncode:
            raise ToolError(r.stderr[:1000] or 'Not a Git repository, or no commits.')
        return r.stdout
    days = number(p, 'days', 365, 1, 36500, True)
    result = run(['log', f'--since={days} days ago', '--format=%aN%x09%ad', '--date=short'])
    authors, weekdays, dates = Counter(), Counter(), Counter()
    from datetime import date
    for line in result.splitlines():
        if '\t' in line:
            author, day = line.rsplit('\t', 1)
            authors[author] += 1
            dates[day] += 1
            weekdays[date.fromisoformat(day).strftime('%A')] += 1
    churn = Counter()
    for line in run(['log', f'--since={days} days ago', '--format=', '--numstat']).splitlines():
        parts = line.split('\t', 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            churn[parts[2]] += int(parts[0]) + int(parts[1])
    return {'commits': sum(authors.values()), 'authors': dict(authors), 'weekdays': dict(weekdays),
            'busiest_dates': dict(dates.most_common(15)),
            'file_churn': [{'file': k, 'lines_added_and_removed': v} for k, v in churn.most_common(40)],
            'chart': [{'label': k, 'value': v} for k, v in authors.most_common()]}


def parse_env(text):
    result, duplicates = {}, []
    for line in text.splitlines():
        m = re.match(r'^\s*(?:export\s+)?([A-Za-z_][\w]*)\s*=\s*(.*)$', line)
        if m:
            if m[1] in result:
                duplicates.append(m[1])
            result[m[1]] = m[2].strip().strip('"').strip("'")
    return result, duplicates


def config(p):
    a, da = parse_env(read_text(required(p, 'reference')))
    b, db = parse_env(read_text(required(p, 'actual')))
    return {'missing_variables': sorted(a.keys() - b.keys()), 'extra_variables': sorted(b.keys() - a.keys()),
            'empty_variables': [k for k, v in b.items() if not v],
            'different_values': sorted(k for k in a.keys() & b.keys() if a[k] != b[k]),
            'duplicate_keys_reference': da, 'duplicate_keys_actual': db,
            'note': 'Values are compared locally and are never included in this report.'}


def todos(p):
    found = []
    extensions = {'.py', '.js', '.ts', '.tsx', '.jsx', '.java', '.c', '.cpp', '.h', '.rs', '.go', '.md', '.html', '.css', '.sh', '.ps1', '.rb', '.php', '.vue', '.svelte', '.sql', '.yml', '.yaml'}
    for f in walk(required(p, 'folder')):
        if f.suffix.lower() not in extensions or f.stat().st_size > 2_000_000:
            continue
        for n, line in enumerate(read_text(f).splitlines(), 1):
            m = re.search(r'\b(TODO|FIXME|HACK|XXX)\b[:\s]*(.*)', line)
            if m:
                found.append({'file': str(f), 'line': n, 'kind': m[1], 'text': m[2].strip()[:1000]})
    return {'items': found, 'download': export_csv('todo-report.csv', found, ['file', 'line', 'kind', 'text'])}


TEMPLATES = {
    'python-cli': {'README.md': '# {name}\n\nRun `python main.py`.\n',
                   'main.py': 'import argparse\n\ndef main():\n    parser = argparse.ArgumentParser(description="{name}")\n    parser.add_argument("--name", default="world")\n    args = parser.parse_args()\n    print(f"Hello, {{args.name}}!")\n\nif __name__ == "__main__":\n    main()\n',
                   '.gitignore': '__pycache__/\n.venv/\n.env\n', 'requirements.txt': '# Add dependencies here\n'},
    'web-app': {'README.md': '# {name}\n\nRun `python server.py` then open http://127.0.0.1:8000.\n',
                'server.py': 'from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer\nfrom pathlib import Path\nimport os\nos.chdir(Path(__file__).parent / "public")\nThreadingHTTPServer(("127.0.0.1", 8000), SimpleHTTPRequestHandler).serve_forever()\n',
                'public/index.html': '<!doctype html><meta charset="utf-8"><title>{name}</title><h1>{name}</h1>\n'},
    'data-project': {'README.md': '# {name}\n\nPut CSVs in data/raw. Run `python analyze.py`.\n',
                     'analyze.py': 'import csv\nfrom pathlib import Path\nfor file in Path("data/raw").glob("*.csv"):\n    with file.open(encoding="utf-8-sig", newline="") as f:\n        rows = list(csv.DictReader(f))\n    print(file.name, len(rows), "rows")\n',
                     'data/raw/.gitkeep': '', 'data/processed/.gitkeep': '', 'reports/.gitkeep': ''}}


def scaffold(p):
    import io
    import zipfile
    name = str(required(p, 'name'))
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', name):
        raise ToolError('Project name must start with a letter and use letters, numbers, underscores or dashes.')
    template = p.get('template', 'python-cli')
    if template not in TEMPLATES:
        raise ToolError('Choose a supported project template.')
    out = io.BytesIO()
    files = []
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for relative, content in TEMPLATES[template].items():
            z.writestr(f'{name}/{relative}', content.replace('{name}', name).replace('{{', '{').replace('}}', '}'))
            files.append(relative)
    return {'files': files, 'download': export(f'{name}.zip', out.getvalue(), True)}


HANDLERS = {'logs': logs, 'api': api, 'git': git, 'config': config, 'todos': todos, 'scaffold': scaffold}
