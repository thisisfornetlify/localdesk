from __future__ import annotations

import difflib
import email.message
import json
import re
import smtplib
import ssl
import time
import urllib.parse
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from ..core import (LOCK, ToolError, add, env, export_csv, fetch_json, get, http, iso_today, need,
                    notify, number, path, put, read_text, records, remove, required)


def valid_date(value):
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError:
        raise ToolError('Use a date in YYYY-MM-DD format.')


def expenses(p):
    action = p.get('action', 'summary')
    if action == 'add':
        try:
            amount = Decimal(str(required(p, 'amount')))
            if not amount.is_finite() or amount <= 0 or amount > 1000000000:
                raise InvalidOperation()
            cents = int((amount * 100).quantize(Decimal('1')))
        except (InvalidOperation, ValueError):
            raise ToolError('Amount must be positive, up to 1,000,000,000.')
        currency = str(p.get('currency') or 'GBP').upper()
        if not re.fullmatch('[A-Z]{3}', currency):
            raise ToolError('Currency must be a three-letter code, such as GBP.')
        add('expense', {'cents': cents, 'amount': cents / 100, 'currency': currency,
                        'date': valid_date(p.get('date') or iso_today()),
                        'category': p.get('category') or 'Other', 'note': p.get('note', '')})
    if action == 'delete':
        remove('expense', required(p, 'id'))
    month = p.get('month') or iso_today()[:7]
    if not re.fullmatch(r'\d{4}-\d{2}', month):
        raise ToolError('Month must be YYYY-MM.')
    rows = [r for r in records('expense', 100000) if r['date'].startswith(month)]
    grouped, total = defaultdict(int), defaultdict(int)
    for r in rows:
        grouped[(r['currency'], r['category'])] += r['cents']
        total[r['currency']] += r['cents']
    result = {'month': month, 'totals': {k: v / 100 for k, v in total.items()}, 'expenses': rows,
              'chart': [{'label': f'{currency} · {category}', 'value': cents / 100}
                        for (currency, category), cents in grouped.items()]}
    if action == 'export':
        result['download'] = export_csv(f'expenses-{month}.csv', rows,
                                        ['date', 'amount', 'currency', 'category', 'note', 'id'])
    return result


def timer(p):
    with LOCK:
        active = get('timer')
        action = p.get('action', 'status')
        if action == 'start':
            if active:
                raise ToolError('Stop the current timer before starting another.')
            active = {'task': str(required(p, 'task')), 'start': time.time(),
                      'minutes': number(p, 'minutes', 25, 1, 1440), 'notified': False}
            put('timer', active)
        if action == 'stop' and active:
            stop = time.time()
            add('time', {'task': active['task'], 'start': active['start'], 'end': stop,
                         'date': datetime.fromtimestamp(active['start']).date().isoformat(),
                         'minutes': round((stop - active['start']) / 60, 2)})
            put('timer', None)
            active = None
    start = valid_date(p.get('week_start') or (date.today() - timedelta(days=date.today().weekday())).isoformat())
    end = (date.fromisoformat(start) + timedelta(days=7)).isoformat()
    rows = [r for r in records('time', 100000) if start <= r['date'] < end]
    totals = defaultdict(float)
    for r in rows:
        totals[r['task']] += r['minutes']
    result = {'active': active, 'server_time': time.time(), 'week_start': start, 'sessions': rows,
              'chart': [{'label': k, 'value': round(v, 2)} for k, v in totals.items()]}
    if action == 'export':
        result['download'] = export_csv('weekly-time.csv', rows, ['date', 'task', 'minutes', 'start', 'end'])
    return result


def habits(p):
    action = p.get('action', 'list')
    if action == 'create':
        name = str(required(p, 'name')).strip()
        if any(r['name'].casefold() == name.casefold() for r in records('habit')):
            raise ToolError('A habit with this name already exists.')
        add('habit', {'name': name, 'days': []})
    if action in ('check', 'uncheck', 'delete'):
        habit = next((r for r in records('habit') if r['id'] == p.get('id')), None)
        if not habit:
            raise ToolError('Choose a habit ID from the list.')
        if action == 'delete':
            remove('habit', habit['id'])
        else:
            day = valid_date(p.get('date') or iso_today())
            if day > iso_today():
                raise ToolError('Cannot check off future dates.')
            days = set(habit['days'])
            days.add(day) if action == 'check' else days.discard(day)
            add('habit', {'name': habit['name'], 'days': sorted(days)}, habit['id'])
    result = []
    for r in records('habit'):
        days, streak, longest, run, previous = set(r['days']), 0, 0, 0, None
        cursor = date.today()
        if cursor.isoformat() not in days:
            cursor -= timedelta(days=1)
        while cursor.isoformat() in days:
            streak += 1
            cursor -= timedelta(days=1)
        for d in sorted(days):
            current = date.fromisoformat(d)
            run = run + 1 if previous and (current - previous).days == 1 else 1
            longest, previous = max(longest, run), current
        result.append({**r, 'streak': streak, 'longest': longest, 'today_done': iso_today() in days,
                       'last_30_days': sum(d >= (date.today() - timedelta(days=29)).isoformat() for d in days)})
    return {'habits': result, 'chart': [{'label': r['name'], 'value': r['streak']} for r in result]}


def send_email(subject, text):
    msg = email.message.EmailMessage()
    msg['From'] = env('SMTP_FROM')
    msg['To'] = env('SMTP_TO')
    msg['Subject'] = subject
    msg.set_content(text)
    port = int(env('SMTP_PORT', '587'))
    cls = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP
    with cls(env('SMTP_HOST'), port, timeout=25) as smtp:
        if port != 465:
            smtp.starttls(context=ssl.create_default_context())
        if __import__('os').environ.get('SMTP_USER'):
            smtp.login(env('SMTP_USER'), env('SMTP_PASSWORD'))
        smtp.send_message(msg)


def page_text(url, selector=''):
    r = http(url)
    if r['status'] >= 400:
        raise ToolError(f'Website returned HTTP {r["status"]}.')
    soup = need('bs4', 'beautifulsoup4').BeautifulSoup(r['text'], 'html.parser')
    for tag in soup(['script', 'style', 'noscript']):
        tag.decompose()
    nodes = soup.select(selector) if selector else [soup]
    if not nodes:
        raise ToolError('CSS selector matched no content.')
    return '\n'.join(n.get_text(' ', strip=True) for n in nodes)


def monitor(p):
    url = str(required(p, 'url'))
    selector = p.get('selector', '')
    text = page_text(url, selector)
    key = 'monitor:' + __import__('hashlib').sha256((url + selector).encode()).hexdigest()
    prior = get(key)
    changed = prior is not None and prior['text'] != text
    diff = '\n'.join(difflib.unified_diff(prior['text'].splitlines(), text.splitlines(),
                                         fromfile='Previous', tofile='Current', lineterm='')) if prior else ''
    # Persist the new baseline only after optional email succeeds, so failed alerts are retried.
    if changed:
        if p.get('email'):
            send_email('LocalDesk · website changed', url + '\n\n' + diff[:10000])
        notify('Website changed', url + '\n' + diff[:1500])
    put(key, {'text': text, 'checked': time.time(), 'url': url})
    return {'message': 'Change detected.' if changed else 'Baseline saved.' if prior is None else 'No change.',
            'changed': changed, 'diff': diff, 'text': text[:30000]}


def rss(p):
    urls = str(required(p, 'urls')).splitlines()
    items, errors = [], []
    for url in urls[:30]:
        if not url.strip():
            continue
        try:
            response = http(url.strip())
            if response['status'] >= 400:
                raise ToolError(f'HTTP {response["status"]}')
            root = ET.fromstring(response['bytes'])
            def text(node, tag):
                child = next((c for c in node if c.tag.split('}')[-1] == tag), None)
                return ''.join(child.itertext()).strip() if child is not None else ''
            for node in root.iter():
                if node.tag.split('}')[-1] not in ('item', 'entry'):
                    continue
                link = text(node, 'link')
                if not link:
                    link = next((c.attrib.get('href', '') for c in node if c.tag.split('}')[-1] == 'link'), '')
                items.append({'title': text(node, 'title'), 'link': link,
                              'date': text(node, 'pubDate') or text(node, 'published') or text(node, 'updated'),
                              'feed': url.strip()})
        except Exception as e:
            errors.append({'feed': url.strip(), 'error': str(e)})
    seen = set()
    items = [i for i in items if not ((i['link'] or i['title']) in seen or seen.add(i['link'] or i['title']))]
    items = items[:number(p, 'limit', 30, 1, 300, True)]
    if p.get('action') == 'email':
        if not items:
            raise ToolError('No feed entries found; email was not sent.')
        send_email('LocalDesk · news digest', '\n\n'.join(f'{i["title"]}\n{i["link"]}' for i in items))
    result = {'items': items, 'errors': errors}
    if p.get('action') == 'export':
        result['download'] = export_csv('news-digest.csv', items)
    return result


def dashboard(p):
    action = p.get('action', 'overview')
    if action == 'add_task':
        add('task', {'title': str(required(p, 'title')), 'due': valid_date(p['due']) if p.get('due') else '', 'done': False})
    if action in ('complete', 'delete_task'):
        identifier = required(p, 'id')
        if action == 'delete_task':
            remove('task', identifier)
        else:
            task = next((r for r in records('task') if r['id'] == identifier), None)
            if not task:
                raise ToolError('Task not found.')
            add('task', {'title': task['title'], 'due': task['due'], 'done': not task['done']}, task['id'])
    if action == 'import_calendar':
        cal = need('icalendar').Calendar.from_ical(read_text(required(p, 'file')))
        count, recurring = 0, 0
        for event in cal.walk('VEVENT'):
            if event.get('RRULE'):
                recurring += 1
            start = event.decoded('DTSTART', None)
            if start:
                uid = str(event.get('UID', '')) or str(event.get('SUMMARY', '')) + start.isoformat()
                add('calendar', {'title': str(event.get('SUMMARY', 'Event')), 'start': start.isoformat(),
                                 'recurring': bool(event.get('RRULE'))},
                    'ical-' + __import__('hashlib').sha256(uid.encode()).hexdigest()[:24])
                count += 1
        return {'message': f'Imported {count} events. {recurring} recurring events show their original start; recurrence expansion is not included.'}
    result = {'tasks': records('task'),
              'calendar': sorted([r for r in records('calendar') if r['start'][:10] >= iso_today()], key=lambda r: r['start'])[:50],
              'habit_streaks': habits({})['habits'], 'timer': get('timer')}
    if action == 'weather':
        city = str(required(p, 'city'))
        geo = fetch_json('https://geocoding-api.open-meteo.com/v1/search?' + urllib.parse.urlencode({'name': city, 'count': 1}))
        if not geo.get('results'):
            raise ToolError('City not found. Try a nearby town.')
        loc = geo['results'][0]
        weather = fetch_json('https://api.open-meteo.com/v1/forecast?' + urllib.parse.urlencode({
            'latitude': loc['latitude'], 'longitude': loc['longitude'], 'current': 'temperature_2m,relative_humidity_2m,wind_speed_10m',
            'timezone': 'auto'}))
        result['weather'] = {'location': f'{loc["name"]}, {loc.get("country", "")}', **weather.get('current', {}),
                             'units': weather.get('current_units', {})}
        put('weather', result['weather'])
    else:
        result['weather'] = get('weather', {'message': 'Choose Weather to fetch a city forecast.'})
    return result


HANDLERS = {'expenses': expenses, 'timer': timer, 'monitor': monitor, 'habits': habits,
            'rss': rss, 'dashboard': dashboard}
