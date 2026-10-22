from __future__ import annotations

import csv
import email
import imaplib
import io
import json
import os
import re
import time
import urllib.parse
import urllib.robotparser
from collections import Counter
from datetime import datetime

from ..core import (ToolError, add, env, export, export_csv, get, http, need, number,
                    path, put, read_text, records, remove, required)


def scrape(p):
    url = str(required(p, 'url'))
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ('https', 'http'):
        raise ToolError('Use an HTTP or HTTPS URL.')
    if p.get('respect_robots', True):
        robots_url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, '/robots.txt', '', ''))
        r = http(robots_url)
        if r['status'] == 200:
            robot = urllib.robotparser.RobotFileParser()
            robot.parse(r['text'].splitlines())
            if not robot.can_fetch('LocalDesk', url):
                raise ToolError('This website disallows this path in robots.txt.')
        elif r['status'] in (401, 403) or r['status'] >= 500:
            raise ToolError('Cannot establish robots.txt access. Try again later.')
    response = http(url)
    if response['status'] >= 400:
        raise ToolError(f'Website returned HTTP {response["status"]}.')
    soup = need('bs4', 'beautifulsoup4').BeautifulSoup(response['text'], 'html.parser')
    try:
        fields = json.loads(p.get('fields') or '{"text": ""}')
    except ValueError:
        raise ToolError('Fields must be a JSON object, such as {"title":"h2","url":"a@href"}.')
    if not isinstance(fields, dict) or not all(isinstance(v, str) for v in fields.values()):
        raise ToolError('Fields must map column names to CSS selectors.')
    rows = []
    for node in soup.select(p.get('selector') or 'body')[:1000]:
        row = {}
        for name, expression in fields.items():
            selector, separator, attribute = expression.rpartition('@')
            selector = selector if separator else expression
            item = node.select_one(selector) if selector else node
            value = (item.get(attribute, '') if separator else item.get_text(' ', strip=True)) if item else ''
            if attribute in ('href', 'src') and value:
                value = urllib.parse.urljoin(url, value)
            row[name] = value
        rows.append(row)
    if not rows:
        raise ToolError('No rows matched. This scraper reads server HTML; JavaScript-only pages need a different source.')
    run_id = add('scrape', {'url': url, 'rows': rows, 'timestamp': datetime.now().isoformat(timespec='seconds')})
    return {'run_id': run_id, 'row_count': len(rows), 'rows': rows,
            'download': export_csv('scraped-data.csv', rows)}


def read_table(file, sheet=None):
    file = path(file)
    if file.suffix.lower() == '.xlsx':
        lib = need('openpyxl')
        wb = lib.load_workbook(file, data_only=True, read_only=True)
        try:
            if sheet and sheet not in wb.sheetnames:
                raise ToolError('Sheet not found. Available: ' + ', '.join(wb.sheetnames))
            ws = wb[sheet] if sheet else wb.active
            rows = []
            for row in ws.iter_rows(values_only=True):
                if len(rows) >= 100001:
                    raise ToolError('Workbook exceeds 100,000 rows; choose a smaller file.')
                rows.append(list(row))
        finally:
            wb.close()
    else:
        text = read_text(file, 30_000_000)
        try:
            dialect = csv.Sniffer().sniff(text[:8000], delimiters=',;\t|')
        except csv.Error:
            dialect = csv.excel
        rows = list(csv.reader(io.StringIO(text), dialect))
    if not rows:
        raise ToolError('The table is empty.')
    if len(rows) > 100001 or max(map(len, rows)) > 1000:
        raise ToolError('Table exceeds 100,000 rows or 1,000 columns.')
    headers = [str(h) if h is not None else f'column_{i+1}' for i, h in enumerate(rows[0])]
    if len(set(headers)) != len(headers):
        raise ToolError('Duplicate column headers. Give each input column a unique name first.')
    width = len(headers)
    malformed = sum(len(r) != width for r in rows[1:])
    if any(len(r) > width and any(v not in (None, '') for v in r[width:]) for r in rows[1:]):
        raise ToolError('Some rows have more values than headers. Fix the delimiter or missing headers first.')
    return headers, [{h: (row[i] if i < len(row) else None) for i, h in enumerate(headers)} for row in rows[1:]], malformed


def cleaner(p):
    headers, rows, malformed = read_table(required(p, 'file'), p.get('sheet'))
    output_headers = [re.sub(r'\W+', '_', h.strip().lower()).strip('_') or f'column_{i+1}'
                      for i, h in enumerate(headers)] if p.get('normalize_headers', True) else headers
    if len(set(output_headers)) != len(output_headers):
        raise ToolError('Header normalization creates duplicate names. Turn it off or rename the input columns.')
    date_columns = {s.strip() for s in p.get('date_columns', '').split(',') if s.strip()}
    if date_columns - set(headers) - set(output_headers):
        raise ToolError('Unknown date columns: ' + ', '.join(date_columns - set(headers) - set(output_headers)))
    clean, duplicates, empty, changed, invalid_dates = [], 0, Counter(), 0, []
    seen = set()
    for n, row in enumerate(rows, 2):
        new = {}
        for original, header in zip(headers, output_headers):
            value = row[original]
            if isinstance(value, str) and p.get('trim', True):
                value = value.strip()
            if value in (None, ''):
                empty[header] += 1
                value = p.get('fill', '')
            elif original in date_columns or header in date_columns:
                try:
                    value = (value if isinstance(value, datetime) else datetime.strptime(str(value), p.get('date_format') or '%d/%m/%Y')).date().isoformat()
                except (ValueError, TypeError):
                    invalid_dates.append({'row': n, 'column': header, 'value': str(value)})
            if value != row[original]:
                changed += 1
            new[header] = value
        signature = json.dumps(new, sort_keys=True, default=str)
        if signature in seen:
            duplicates += 1
            if p.get('deduplicate', True):
                continue
        seen.add(signature)
        clean.append(new)
    result = {'input_rows': len(rows), 'output_rows': len(clean), 'duplicate_rows': duplicates,
              'changed_cells': changed, 'missing_cells': dict(empty), 'malformed_row_count': malformed,
              'invalid_dates': invalid_dates[:100], 'preview': clean[:100]}
    if p.get('action') == 'clean':
        if p.get('format') == 'xlsx':
            lib = need('openpyxl')
            wb = lib.Workbook()
            ws = wb.active
            ws.title = 'Cleaned data'
            ws.append(output_headers)
            for row in clean:
                ws.append([("'" + v if isinstance(v, str) and v.startswith(('=', '+', '-', '@')) else v)
                           for v in row.values()])
            ws.freeze_panes = 'A2'
            ws.auto_filter.ref = ws.dimensions
            for cell in ws[1]:
                cell.font = lib.styles.Font(bold=True, color='FFFFFF')
                cell.fill = lib.styles.PatternFill('solid', fgColor='305C49')
            out = io.BytesIO()
            wb.save(out)
            result['download'] = export('cleaned.xlsx', out.getvalue(), True)
        else:
            result['download'] = export_csv('cleaned.csv', clean, output_headers)
    return result


def imap_client():
    client = imaplib.IMAP4_SSL(env('IMAP_HOST'), int(env('IMAP_PORT', '993')), timeout=25)
    try:
        client.login(env('IMAP_USER'), env('IMAP_PASSWORD'))
    except Exception:
        client.logout()
        raise ToolError('IMAP login failed. Check host, username, and app password.')
    return client


def header_text(value):
    from email.header import decode_header, make_header
    try:
        return str(make_header(decode_header(value or '')))
    except (ValueError, LookupError):
        return str(value or '')


def mailbox(value):
    value = str(value)
    if any(c in value for c in '\r\n\x00'):
        raise ToolError('Invalid mailbox name.')
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def email_sort(p):
    action = p.get('action', 'preview')
    if action == 'apply':
        identifier = required(p, 'plan_id')
        plan = next((r for r in records('email_plan') if r['id'] == identifier), None)
        if not plan or plan.get('applied') or time.time() - plan['_created'] > 900:
            raise ToolError('Email preview expired or was applied. Preview again.')
        client = imap_client()
        moved, errors = [], []
        try:
            status, _ = client.select(mailbox(plan['folder']))
            if status != 'OK':
                raise ToolError('Could not select source mailbox.')
            validity = client.response('UIDVALIDITY')[1]
            if str(validity) != plan['validity']:
                raise ToolError('Mailbox identifiers changed. Preview again.')
            # Consume the plan before mutations so retries cannot copy the same messages twice.
            add('email_plan', {**plan, 'applied': True}, identifier)
            for item in plan['messages']:
                try:
                    destination = mailbox(item['destination'])
                    client.create(destination)  # Existing-mailbox NO is harmless; COPY checks final status.
                    status, _ = client.uid('COPY', item['uid'], destination)
                    if status != 'OK':
                        raise ToolError('Copy rejected by server')
                    status, _ = client.uid('STORE', item['uid'], '+FLAGS.SILENT', '(\\Deleted)')
                    if status != 'OK':
                        raise ToolError('Copied, but source could not be flagged deleted; inspect both folders')
                    moved.append(item)
                except Exception as e:
                    errors.append({'uid': item['uid'], 'error': str(e)})
        finally:
            client.logout()  # No EXPUNGE: never permanently delete unrelated messages.
        add('email_history', {'moved': moved, 'errors': errors})
        return {'moved': moved, 'errors': errors,
                'note': 'Messages were copied and originals flagged Deleted. Expunge using your mail client after review.'}
    try:
        rules = json.loads(required(p, 'rules'))
        if not isinstance(rules, list) or any(not isinstance(r, dict) or r.get('field') not in ('from', 'subject') or
                not r.get('contains') or not r.get('folder') for r in rules):
            raise ValueError()
    except ValueError:
        raise ToolError('Rules must be a JSON array: [{"field":"from","contains":"shop","folder":"Receipts"}]')
    folder = p.get('folder') or 'INBOX'
    client, messages = imap_client(), []
    try:
        status, _ = client.select(mailbox(folder), readonly=True)
        if status != 'OK':
            raise ToolError('Could not select source mailbox.')
        validity = str(client.response('UIDVALIDITY')[1])
        status, data = client.uid('SEARCH', None, 'UNDELETED')
        if status != 'OK':
            raise ToolError('Mail search failed.')
        for uid in data[0].split()[-number(p, 'limit', 100, 1, 500, True):]:
            status, content = client.uid('FETCH', uid, '(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT MESSAGE-ID)])')
            chunks = [c[1] for c in content if isinstance(c, tuple)]
            if status != 'OK' or not chunks:
                continue
            msg = email.message_from_bytes(b''.join(chunks))
            info = {'from': header_text(msg['From']), 'subject': header_text(msg['Subject'])}
            rule = next((r for r in rules if str(r['contains']).casefold() in info[r['field']].casefold()), None)
            if rule and str(rule['folder']) != folder:
                mailbox(rule['folder'])
                messages.append({**info, 'uid': uid.decode(), 'destination': rule['folder']})
    finally:
        client.logout()
    identifier = add('email_plan', {'folder': folder, 'validity': validity, 'messages': messages, 'applied': False})
    return {'message': f'{len(messages)} messages matched. Apply only after reviewing destinations.',
            'email_plan_id': identifier, 'messages': messages}


def ocr(p):
    Image = need('PIL.Image', 'Pillow')
    engine = need('pytesseract')
    if os.environ.get('TESSERACT_CMD'):
        engine.pytesseract.tesseract_cmd = env('TESSERACT_CMD')
    try:
        with Image.open(path(required(p, 'file'))) as image:
            if image.width * image.height > 40_000_000:
                raise ToolError('Image is larger than 40 megapixels.')
            text = engine.image_to_string(image, lang=p.get('language') or 'eng', timeout=90)
    except engine.TesseractNotFoundError:
        raise ToolError('Install Tesseract OCR, then set TESSERACT_CMD in .env to its executable path.')
    candidates = []
    for line in text.splitlines():
        if re.search(r'\b(total|amount due|balance due)\b', line, re.I) and not re.search(r'sub\s*total', line, re.I):
            amounts = re.findall(r'(?:[£$€]\s*)?\d[\d,]*[.]\d{2}\b', line)
            if amounts:
                candidates.append({'line': line.strip(), 'amount': amounts[-1]})
    dates = list(dict.fromkeys(re.findall(r'\b(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b', text)))
    result = {'text': text, 'total_candidates': candidates, 'date_candidates': dates,
              'note': 'OCR and total/date extraction are heuristic. Review the original before recording an expense.',
              'download': export('receipt-text.txt', text)}
    add('ocr', {'file': str(p['file']), 'totals': candidates, 'dates': dates})
    return result


HANDLERS = {'scrape': scrape, 'cleaner': cleaner, 'email-sort': email_sort, 'ocr': ocr}
