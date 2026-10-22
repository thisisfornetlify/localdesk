from __future__ import annotations

import hashlib
import html
import io
import math
import re
import secrets
import string
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from ..core import (DATA, ToolError, add, apply_plan, digest, export, get, make_plan,
                    need, number, path, put, read_text, records, remove, required, walk, http, undo_plan)


def rename(p):
    pattern = p.get('pattern') or '{name}_{n:03d}{ext}'
    moves = []
    for n, f in enumerate(walk(required(p, 'folder'), p.get('recursive', False)), 1):
        stamp = datetime.fromtimestamp(f.stat().st_mtime)
        if p.get('date_source') == 'exif':
            try:
                Image = need('PIL.Image', 'Pillow')
                with Image.open(f) as im:
                    raw = im.getexif().get(36867) or im.getexif().get(306)
                    if raw:
                        stamp = datetime.strptime(raw, '%Y:%m:%d %H:%M:%S')
            except (OSError, ValueError):
                pass  # Non-images and images without EXIF use modification time.
        try:
            new = pattern.format(name=f.stem, ext=f.suffix, n=n, date=stamp.strftime('%Y-%m-%d'),
                                 year=stamp.year, month=f'{stamp.month:02}', day=f'{stamp.day:02}')
        except (KeyError, ValueError, IndexError, AttributeError) as exc:
            raise ToolError('Use {name}, {ext}, {n:03d}, {date}, {year}, {month}, or {day}.') from exc
        if not new or new in ('.', '..') or re.search(r'[<>:"/\\|?*\x00-\x1f]', new) or new.endswith((' ', '.')):
            raise ToolError(f'Invalid filename generated: {new}')
        if new != f.name:
            moves.append({'source': str(f), 'destination': str(f.with_name(new))})
    return make_plan(moves, 'Bulk rename')


def duplicates(p):
    groups = defaultdict(list)
    for f in walk(required(p, 'folder'), p.get('recursive', True)):
        groups[f.stat().st_size].append(f)
    hashes = defaultdict(list)
    for size, files in groups.items():
        if len(files) > 1:
            for f in files:
                hashes[(size, digest(f))].append(f)
    dupes = [sorted(fs, key=lambda f: str(f).casefold()) for fs in hashes.values() if len(fs) > 1]
    rows = [{'keep': str(fs[0]), 'duplicates': [str(f) for f in fs[1:]],
             'reclaimable_bytes': fs[0].stat().st_size * (len(fs) - 1)} for fs in dupes]
    result = {'groups': rows, 'reclaimable_bytes': sum(r['reclaimable_bytes'] for r in rows),
              'message': f'{len(rows)} duplicate groups. First alphabetical path is kept. Other copies can be moved to recoverable trash.'}
    if p.get('action') == 'quarantine':
        batch = secrets.token_hex(8)
        moves = [{'source': str(f), 'destination': str(DATA / 'trash' / batch / f'{i}-{f.name}')}
                 for i, f in enumerate(f for fs in dupes for f in fs[1:])]
        result.update(make_plan(moves, 'Quarantine duplicates'))
    return result


GROUPS = {'Images': 'jpg jpeg png gif webp bmp svg heic tif tiff',
          'Documents': 'pdf doc docx txt md rtf odt', 'Spreadsheets': 'csv tsv xls xlsx ods',
          'Audio': 'mp3 wav flac ogg m4a aac', 'Video': 'mp4 mov mkv avi webm',
          'Archives': 'zip 7z rar gz tar bz2', 'Code': 'py js ts html css json yaml yml sh ps1'}


def organize(p):
    root = path(required(p, 'folder'), True)
    moves = []
    for f in walk(root, False):
        group = next((k for k, v in GROUPS.items() if f.suffix.lower().lstrip('.') in v.split()), 'Other')
        moves.append({'source': str(f), 'destination': str(root / group / f.name)})
    return make_plan(moves, 'Organize downloads')


WORDS = '''acorn amber anchor apple apricot arch arrow atlas autumn avocado badge bamboo banana basil
beach beacon bear beaver beetle bell berry birch blossom blue boat breeze brick bridge brook brush bubble
cabin cactus candle canyon carrot castle cedar celery cherry chestnut circle cliff cloud clover coast cobalt
cocoa comet copper coral cotton crane creek cricket crown crystal cube daisy dawn deer delta desert diamond
dolphin dove dragon dream drift drum dune eagle earth echo elm emerald evening falcon feather fern field
finch fire flame flower forest fox frost galaxy garden garlic garnet gate gazelle ginger glacier globe glow
goat gold goose grain grape grass grove gull harbor hare hazel hedgehog heron hill honey horizon horse
ice iris island ivory jade jasmine jay jelly juniper kale kettle kite kiwi koala lake lantern lark lava
leaf lemon leopard lilac lily lime lion lizard lotus lucky lunar lynx mango maple marble meadow melon
meteor mint mist moon moss mountain mouse mushroom nectar nest night north nutmeg oak ocean olive onion
opal orange orchid otter owl panda papaya parsley peach pearl pebble pecan pepper petal pine planet plum
pond poppy potato prairie prism pumpkin quartz rabbit rain rainbow raven reed reef river robin rock rocket
rose ruby sage sail salmon sand satin scarlet sea seed shadow shell silver sky slate snow solar sparrow
spring spruce square star stone storm stream sugar summit sun sunset swan sweet swift teal thistle thyme
tiger timber toast tomato topaz tower trail tree trout tulip turtle valley velvet violet walnut water wave
whale wheat willow wind winter wolf wood wren yellow yonder zebra zenith zinc zinnia'''.split()


def passwords(p):
    if p.get('action') == 'check':
        password = str(required(p, 'password'))
        hashed = hashlib.sha1(password.encode()).hexdigest().upper()
        r = http('https://api.pwnedpasswords.com/range/' + hashed[:5], headers={'Add-Padding': 'true'})
        if r['status'] != 200:
            raise ToolError(f'Pwned Passwords returned HTTP {r["status"]}; retry later.')
        count = next((int(line.split(':')[1]) for line in r['text'].splitlines()
                      if line.split(':')[0] == hashed[5:]), 0)
        return {'breach_count': count, 'message': 'Found in breach data. Replace this password.' if count else
                'No match in this breach dataset. This does not establish password strength.',
                'privacy': 'Only the first five SHA-1 characters were sent; the password is never saved.'}
    if p.get('mode') == 'passphrase':
        length = number(p, 'words', 8, 6, 20, True)
        return {'password': '-'.join(secrets.choice(WORDS) for _ in range(length)),
                'entropy_bits': round(length * math.log2(len(WORDS)), 1)}
    length = number(p, 'length', 24, 12, 128, True)
    classes = [string.ascii_lowercase, string.ascii_uppercase, string.digits, '!@#$%&*+-=?']
    alphabet = ''.join(classes)
    while True:
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
        if all(any(c in group for c in password) for group in classes):
            return {'password': password, 'entropy_bits_approx': round(length * math.log2(len(alphabet)), 1)}


def clipboard(p):
    action = p.get('action', 'search')
    if action == 'start':
        need('pyperclip').paste()  # Fail before enabling when clipboard isn't available.
        put('clipboard_enabled', True)
        return {'message': 'Clipboard capture enabled for this session. Copies, including sensitive text, are stored locally. Stop capture at any time.'}
    if action == 'stop':
        put('clipboard_enabled', False)
    if action == 'save':
        add('clipboard', {'text': str(required(p, 'text'))[:100000]})
        from ..core import connection
        with connection() as db:
            db.execute("DELETE FROM records WHERE kind='clipboard' AND id NOT IN (SELECT id FROM records WHERE kind='clipboard' ORDER BY created DESC LIMIT 1000)")
    if action == 'clear':
        for row in records('clipboard', 10000):
            remove('clipboard', row['id'])
    if action == 'copy':
        need('pyperclip').copy(str(required(p, 'text')))
    q = p.get('query', '').lower()
    return {'capture_enabled': get('clipboard_enabled', False),
            'entries': [r for r in records('clipboard', 1000) if q in r['text'].lower()]}


def markdown(p):
    source = read_text(p['file']) if p.get('file') else str(required(p, 'text'))
    md = need('markdown', 'Markdown')
    rendered = md.markdown(source, extensions=['tables', 'fenced_code'])
    if p.get('format') == 'pdf':
        return text_pdf(source, 'document.pdf')
    # Exported HTML disables scripts and network subresource requests by document policy.
    document = ('<!doctype html><html><head><meta charset="utf-8">'
                '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">'
                '<title>Converted document</title><style>body{max-width:800px;margin:48px auto;font:17px/1.7 system-ui;padding:24px}'
                'pre{white-space:pre-wrap;background:#f4f4f4;padding:16px}table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:8px}</style>'
                '</head><body>' + rendered + '</body></html>')
    return {'download': export('document.html', document), 'html_source': document}


def text_pdf(text, name):
    need('reportlab')
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    out = io.BytesIO()
    styles = getSampleStyleSheet()
    story = []
    for line in text.splitlines():
        level = len(line) - len(line.lstrip('#'))
        style = styles['Heading1' if level == 1 else 'Heading2' if level in (2, 3) else 'BodyText']
        # PDF mode intentionally uses readable text and headings; HTML retains richer Markdown.
        story.append(Paragraph(html.escape(line.lstrip('# ').strip()), style) if line.strip() else Spacer(1, 8))
    SimpleDocTemplate(out).build(story or [Paragraph(' ', styles['BodyText'])])
    return {'download': export(name, out.getvalue(), True), 'note': 'PDF renders headings and text; use HTML for rich Markdown tables and code formatting.'}


def pages(value, total):
    selected = set()
    if not value:
        return list(range(total))
    try:
        for token in str(value).split(','):
            bounds = [int(n.strip()) for n in token.split('-')]
            if len(bounds) == 1:
                bounds *= 2
            if len(bounds) != 2 or not (1 <= bounds[0] <= bounds[1] <= total):
                raise ValueError()
            selected.update(range(bounds[0] - 1, bounds[1]))
    except ValueError:
        raise ToolError(f'Use page numbers 1–{total}, such as 1-3,5.')
    return sorted(selected)


def pdf(p):
    lib = need('pypdf')
    action = p.get('action', 'extract')
    files = [path(s.strip()) for s in str(required(p, 'files')).splitlines() if s.strip()]
    readers = [lib.PdfReader(f) for f in files]
    for reader in readers:
        if reader.is_encrypted and not reader.decrypt(p.get('password', '')):
            raise ToolError('Encrypted PDF. Provide its password.')
    if action == 'extract':
        text = '\n\n'.join(f'--- Page {i+1} ---\n{readers[0].pages[i].extract_text() or ""}'
                           for i in pages(p.get('pages'), len(readers[0].pages)))
        return {'text': text, 'download': export('extracted.txt', text),
                'note': 'Scanned PDFs need OCR; text extraction reads embedded text.'}
    if action == 'split':
        out = io.BytesIO()
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
            for i in pages(p.get('pages'), len(readers[0].pages)):
                w, single = lib.PdfWriter(), io.BytesIO()
                w.add_page(readers[0].pages[i])
                w.write(single)
                z.writestr(f'page-{i+1}.pdf', single.getvalue())
        return {'download': export('split-pages.zip', out.getvalue(), True)}
    w, out = lib.PdfWriter(), io.BytesIO()
    if action == 'merge':
        for reader in readers:
            for page in reader.pages:
                w.add_page(page)
    elif action in ('compress', 'select'):
        for i in pages(p.get('pages'), len(readers[0].pages)):
            w.add_page(readers[0].pages[i])
        if action == 'compress':
            for page in w.pages:
                page.compress_content_streams()
            w.add_metadata({})
    else:
        raise ToolError('Unknown PDF action.')
    w.write(out)
    return {'download': export(f'{action}.pdf', out.getvalue(), True), 'output_bytes': len(out.getvalue()),
            'input_bytes': sum(f.stat().st_size for f in files),
            'note': 'Lossless stream compression may not shrink already compressed PDFs.' if action == 'compress' else ''}


def file_history(p):
    if p.get('action') == 'undo':
        return undo_plan(required(p, 'journal_id'))
    return {'history': records('journal'), 'recovery': records('recovery')}


HANDLERS = {'rename': rename, 'duplicates': duplicates, 'organize': organize,
            'passwords': passwords, 'clipboard': clipboard, 'markdown': markdown, 'pdf': pdf,
            'file-history': file_history}
