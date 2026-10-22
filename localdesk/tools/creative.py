from __future__ import annotations

import json
import math
import random
import re
from collections import Counter, defaultdict

from ..core import (ToolError, add, env, export, fetch_json, get, http, need, number,
                    path, put, read_text, required)
from .data import read_table
from .files import WORDS


FIVE = sorted(set(w for w in WORDS + '''about above abuse actor acute adapt admit adopt adult after again agent
agree ahead alarm album alert alike alive allow alone along alter among angel anger angle angry apart apply
argue arise array aside asset audio audit avoid award aware awful badly baker bases basic basis began begin
begun being below bench birth black blade blame blank blast blind block blood board boost booth bound brain
brand brave bread break breed brief bring broad broke brown build built buyer cable camel canal candy carry
catch cause chain chair chalk charm chart chase cheap check cheer chess chief child chose civil claim class
clean clear clerk click climb clock close coach color could count court cover craft crash crazy cream crime
cross crowd cruel crush curve cycle daily dance dealt death debut delay depth diary dirty doubt dozen draft
drama drawn dress dried drink drive drove dying eager early eight elect elite empty enemy enjoy enter entry
equal error essay event every exact exist extra faint faith false fault fence fetch fever fewer fifty fight
final first fixed flash fleet flesh float floor flour fluid focus force forty forum found frame frank fresh
front fruit funny ghost giant given glass glory going grace grade grand grant graph grasp great green grief
gross group grown guard guess guest guide guilt happy harsh heart heavy hence hobby honor hotel house human
humor ideal image imply index inner input issue joint judge juice known label labor large laser later laugh
layer learn lease least leave legal level light limit links lives local logic loose lower loyal lunch magic
major maker march match maybe mayor meant medal media mercy merit metal meter might minor mixed model money
month moral motor mount mouth movie music naive naked nasty nerve never newly niece noble noise noisy novel
nurse occur offer often order organ other ought outer owned owner paint panel panic paper party pasta patch
pause peace phase phone photo piano piece pilot pitch place plain plane plant plate point polar poker pound
power press pride prime print prior prize proof proud prove pulse punch pupil queen query quest quick quiet
quite quote radar radio raise rally range rapid ratio reach react ready realm refer reign relax relay reply
reset right rigid rival robot rough round route royal rural sadly salad scale scare scene scope score sense
serve seven shade shall shape share shark sharp shelf shift shine shirt shock shoot shore short shown sight
sigma silly since skill sleep slice slide slope small smart smile smoke snake solid solve sorry sound south
space spare speak speed spell spend spent spice split spoke sport staff stage stain stair stake stand start
state steak steal steam steel steep stick still stock stole stood store story strip stuck study stuff style
sugar suite super surge swear sweep swing table taken taste teach teeth thank theft their theme there these
thick thief thing think third those three threw throw tight tired title today token topic total touch tough
trace track trade train treat trend trial tribe trick tried tries truck truly trust truth twice twist uncle
under union unite unity until upper upset urban usage usual valid value video virus visit vital voice voter
wagon waist waste watch weary weigh weird wheel where which while white whole whose width witch woman women
worry worse worst worth would wound write wrong wrote yield young youth'''.split() if len(w) == 5))


def feedback(guess, answer):
    result = ['0'] * 5
    remaining = Counter()
    for i, c in enumerate(answer):
        if guess[i] == c:
            result[i] = '2'
        else:
            remaining[c] += 1
    for i, c in enumerate(guess):
        if result[i] == '0' and remaining[c]:
            result[i], remaining[c] = '1', remaining[c] - 1
    return ''.join(result)


def wordle(p):
    words = [w.strip().lower() for w in read_text(p['file']).splitlines()] if p.get('file') else FIVE
    words = sorted(set(w for w in words if re.fullmatch('[a-z]{5}', w)))
    if len(words) > 20000:
        raise ToolError('Use a word list of at most 20,000 entries.')
    candidates = words[:]
    for line in str(p.get('history', '')).splitlines():
        if not line.strip():
            continue
        parts = line.lower().split()
        if len(parts) != 2 or not re.fullmatch('[a-z]{5}', parts[0]) or not re.fullmatch('[012]{5}', parts[1]):
            raise ToolError('Each line must be a guess and feedback, such as crane 01200. 0=gray, 1=yellow, 2=green.')
        candidates = [w for w in candidates if feedback(parts[0], w) == parts[1]]
    if not candidates:
        return {'message': 'No matches. Check feedback or upload a larger word list.', 'remaining': 0}
    # Rank a bounded set of probes by exact feedback entropy, including duplicate-letter accounting.
    frequencies = Counter(c for w in candidates for c in set(w))
    probes = sorted(words, key=lambda w: sum(frequencies[c] for c in set(w)), reverse=True)[:120]
    sample = candidates if len(candidates) <= 2000 else random.Random(0).sample(candidates, 2000)
    scores = []
    for guess in set(probes + candidates[:100]):
        groups = Counter(feedback(guess, w) for w in sample)
        entropy = -sum((n / len(sample)) * math.log2(n / len(sample)) for n in groups.values())
        scores.append({'word': guess, 'entropy_bits': round(entropy, 3), 'possible_answer': guess in candidates})
    scores.sort(key=lambda r: (-r['entropy_bits'], not r['possible_answer'], r['word']))
    return {'remaining': len(candidates), 'candidates': candidates[:200], 'suggestions': scores[:15],
            'note': 'Ranks a bounded probe set by information gain. The bundled starter dictionary is small; upload your own five-letter list for broader coverage.'}


def ascii_art(p):
    Image = need('PIL.Image', 'Pillow')
    width = number(p, 'width', 90, 20, 200, True)
    ramp = p.get('ramp') or '@%#*+=-:. '
    if len(ramp) < 2:
        raise ToolError('Use at least two characters in the brightness ramp.')
    if p.get('invert'):
        ramp = ramp[::-1]
    with Image.open(path(required(p, 'file'))) as im:
        if im.width * im.height > 40_000_000:
            raise ToolError('Image is larger than 40 megapixels.')
        height = min(300, max(1, round(im.height / im.width * width * .48)))
        # Composite transparent pixels onto white before conversion.
        rgba = im.convert('RGBA')
        base = Image.new('RGBA', im.size, 'white')
        base.alpha_composite(rgba)
        gray = base.convert('L').resize((width, height))
        pixels = list(gray.tobytes())
    text = '\n'.join(''.join(ramp[pixel * (len(ramp) - 1) // 255] for pixel in pixels[y*width:(y+1)*width])
                     for y in range(height))
    return {'ascii': text, 'download': export('ascii-art.txt', text)}


def game(p):
    from ..core import LOCK
    with LOCK:
        state = get('game')
        command = str(p.get('command') or 'look').strip().lower()
        if not state or command == 'new':
            state = {'x': 0, 'y': 0, 'hp': 30, 'gold': 0, 'potions': 2, 'enemy': 0,
                     'visited': ['0,0'], 'treasure': ['2,1', '4,0', '1,3'], 'defeated': [],
                     'won': False, 'message': 'Welcome to the Lantern Vault. Find three treasures, then reach (4,4).'}
        elif state['hp'] <= 0 or state['won']:
            state['message'] = 'Adventure finished. Type new to play again.'
        elif command in ('n', 's', 'e', 'w', 'north', 'south', 'east', 'west'):
            if state['enemy'] > 0:
                state['message'] = 'A sentinel blocks your path. Type attack or drink.'
            else:
                dx, dy = {'n': (0,-1), 's': (0,1), 'e': (1,0), 'w': (-1,0)}[command[0]]
                x, y = state['x'] + dx, state['y'] + dy
                if not (0 <= x < 5 and 0 <= y < 5) or (x, y) in ((1,1), (3,2), (2,3)):
                    state['message'] = 'A stone wall blocks the way.'
                else:
                    state['x'], state['y'] = x, y
                    cell = f'{x},{y}'
                    state['message'] = f'You enter chamber ({x},{y}).'
                    if cell not in state['visited']:
                        state['visited'].append(cell)
                    if cell in ('2,0', '0,2', '3,3') and cell not in state['defeated']:
                        state['enemy'] = 8
                        state['message'] += ' A sentinel appears!'
                    if cell in state['treasure']:
                        state['treasure'].remove(cell)
                        state['gold'] += 10
                        state['message'] += ' You found ten gold!'
                    if cell == '4,4':
                        state['won'] = state['gold'] >= 30
                        state['message'] = 'You escape with all three treasures. Victory!' if state['won'] else 'The exit needs all three treasures.'
        elif command == 'attack':
            if state['enemy'] > 0:
                damage = random.randint(3, 7)
                state['enemy'] = max(0, state['enemy'] - damage)
                state['message'] = f'You deal {damage} damage.'
                if state['enemy'] == 0:
                    state['defeated'].append(f'{state["x"]},{state["y"]}')
                    state['message'] += ' Sentinel defeated.'
                else:
                    state['hp'] = max(0, state['hp'] - random.randint(2, 5))
            else:
                state['message'] = 'No enemy here.'
        elif command == 'drink':
            if state['potions']:
                state['potions'] -= 1
                state['hp'] = min(30, state['hp'] + 12)
                state['message'] = 'You drink a healing potion.'
            else:
                state['message'] = 'No potions left.'
        elif command not in ('look', 'help'):
            raise ToolError('Commands: new, look, north, south, east, west, attack, drink.')
        put('game', state)
    grid = []
    for y in range(5):
        grid.append(' '.join('@' if (x,y) == (state['x'],state['y']) else '#' if (x,y) in ((1,1),(3,2),(2,3)) else
                             'E' if (x,y) == (4,4) else '$' if f'{x},{y}' in state['treasure'] else
                             '.' if f'{x},{y}' in state['visited'] else '?' for x in range(5)))
    return {'message': state['message'], 'map': '\n'.join(grid), 'health': state['hp'], 'gold': state['gold'],
            'potions': state['potions'], 'enemy_health': state['enemy'], 'won': state['won'],
            'commands': 'north / south / east / west / attack / drink / new. @ you, # wall, $ treasure, E exit.'}


def playlist(p):
    file = path(required(p, 'file'))
    if file.suffix.lower() == '.json':
        data = json.loads(read_text(file, 50_000_000))
        if isinstance(data, dict):
            data = data.get('items', data.get('tracks', []))
        rows = data
    else:
        _, rows, _ = read_table(file)
    if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
        raise ToolError('Use a Spotify listening-history JSON array or a CSV export.')
    artists, tracks, hours, months = Counter(), Counter(), Counter(), Counter()
    total_ms, skipped, metrics = 0, 0, defaultdict(list)
    for row in rows:
        track = row.get('track', row)
        if not isinstance(track, dict):
            track = row
        artist = row.get('master_metadata_album_artist_name') or row.get('artistName') or row.get('artist') or track.get('artist')
        if not artist and track.get('artists'):
            artist = ', '.join(a.get('name', '') for a in track['artists'])
        name = row.get('master_metadata_track_name') or row.get('trackName') or row.get('name') or track.get('name')
        if not name:
            continue
        artists[str(artist or 'Unknown')] += 1
        tracks[str(name)] += 1
        try:
            ms = int(float(row.get('ms_played', row.get('msPlayed', row.get('duration_ms', track.get('duration_ms', 0)))) or 0))
        except (ValueError, TypeError):
            ms = 0
        total_ms += max(ms, 0)
        skipped += bool(row.get('skipped') in (True, 'true', 'True'))
        timestamp = str(row.get('ts', row.get('endTime', row.get('played_at', ''))))
        if len(timestamp) >= 13:
            hours[timestamp[11:13]] += 1
            months[timestamp[:7]] += 1
        for key in ('energy', 'danceability', 'valence', 'tempo', 'popularity'):
            try:
                metrics[key].append(float(row[key]))
            except (KeyError, TypeError, ValueError):
                pass
    return {'entries': sum(tracks.values()), 'unique_tracks': len(tracks), 'unique_artists': len(artists),
            'listening_hours': round(total_ms / 3_600_000, 2), 'skipped_entries': skipped,
            'top_artists': [{'artist': k, 'plays': v} for k, v in artists.most_common(20)],
            'top_tracks': [{'track': k, 'plays': v} for k, v in tracks.most_common(20)],
            'by_hour': dict(sorted(hours.items())), 'by_month': dict(sorted(months.items())),
            'average_audio_features': {k: round(sum(v) / len(v), 3) for k, v in metrics.items() if v},
            'chart': [{'label': k, 'value': v} for k, v in artists.most_common(12)],
            'note': 'Uses exported data. Audio features are summarized only when included in your file.'}


def telegram(method, body=None):
    response = fetch_json('https://api.telegram.org/bot' + env('TELEGRAM_BOT_TOKEN') + '/' + method, body or {})
    if not response.get('ok'):
        raise ToolError('Telegram rejected the request. Check your token and chat ID.')
    return response.get('result')


def bots(p):
    provider = p.get('provider') or 'telegram'
    action = p.get('action', 'send')
    message = str(p.get('message') or 'Hello from LocalDesk')
    if provider == 'discord':
        body = {'content': message[:2000]}
        if action == 'poll':
            options = [s.strip() for s in str(required(p, 'options')).splitlines() if s.strip()]
            if not 2 <= len(options) <= 10:
                raise ToolError('Use 2–10 poll options, one per line.')
            body['poll'] = {'question': {'text': message[:300]}, 'answers': [{'poll_media': {'text': s[:55]}} for s in options],
                            'duration': 24, 'allow_multiselect': False}
        if action == 'quiz':
            raise ToolError('Use Telegram for automatic quiz scoring. Discord supports messages and polls here.')
        result = http(env('DISCORD_WEBHOOK_URL'), 'POST', body)
        if result['status'] >= 400:
            raise ToolError(f'Discord returned HTTP {result["status"]}.')
        return {'message': 'Posted to Discord.'}
    if provider != 'telegram':
        raise ToolError('Choose Telegram or Discord.')
    chat_id = str(env('TELEGRAM_CHAT_ID'))
    if action == 'listen':
        # This is a bounded poll. Schedule every 15 seconds for a continuous local bot.
        updates = telegram('getUpdates', {'offset': get('telegram_offset', 0), 'timeout': 0, 'allowed_updates': ['message']})
        handled = 0
        for update in updates:
            msg = update.get('message', {})
            if str(msg.get('chat', {}).get('id')) == chat_id:
                text = msg.get('text', '')
                if text.startswith('/remind '):
                    parts = text.split(' ', 2)
                    if len(parts) == 3 and parts[1].isdigit() and 1 <= int(parts[1]) <= 525600:
                        add('bot_reminder', {'at': __import__('time').time() + int(parts[1]) * 60, 'message': parts[2], 'sent': False})
                        reply = 'Reminder saved. LocalDesk must remain running.'
                    else:
                        reply = 'Use /remind MINUTES message (1–525600 minutes).'
                elif text.startswith('/quiz'):
                    telegram('sendPoll', {'chat_id': chat_id, 'question': 'Which Python type is immutable?',
                                          'options': [{'text': 'list'}, {'text': 'tuple'}, {'text': 'dict'}],
                                          'type': 'quiz', 'correct_option_id': 1, 'is_anonymous': True})
                    reply = None
                elif text.startswith('/poll'):
                    telegram('sendPoll', {'chat_id': chat_id, 'question': 'Time for a break?',
                                          'options': [{'text': 'Yes'}, {'text': 'Later'}]})
                    reply = None
                else:
                    reply = 'LocalDesk bot: /remind MINUTES message, /quiz, /poll, /help'
                if reply:
                    telegram('sendMessage', {'chat_id': chat_id, 'text': reply})
                handled += 1
            put('telegram_offset', update['update_id'] + 1)
        return {'message': f'Handled {handled} messages in the allowed chat.'}
    if action in ('poll', 'quiz'):
        options = [s.strip() for s in str(required(p, 'options')).splitlines() if s.strip()]
        if not 2 <= len(options) <= 10:
            raise ToolError('Use 2–10 options, one per line.')
        body = {'chat_id': chat_id, 'question': message, 'options': [{'text': s} for s in options], 'is_anonymous': True}
        if action == 'quiz':
            body.update(type='quiz', correct_option_id=number(p, 'correct', 0, 0, len(options)-1, True))
        telegram('sendPoll', body)
    else:
        telegram('sendMessage', {'chat_id': chat_id, 'text': message})
    return {'message': 'Sent to Telegram.'}


HANDLERS = {'bots': bots, 'game': game, 'wordle': wordle, 'ascii': ascii_art, 'playlist': playlist}
