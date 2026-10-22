"""The same catalog drives browser forms and validates available server actions."""


def f(name, label=None, kind='text', value='', help='', required=False, options=None):
    return dict(name=name, label=label or name.replace('_', ' ').capitalize(), type=kind,
                value=value, help=help, required=required, options=options or [])


def a(key, label, fields=None, effect='read', schedule=False):
    return dict(key=key, label=label, fields=fields or [], effect=effect, schedule=schedule)


def t(key, name, category, description, icon, actions, note=''):
    return dict(id=key, name=name, category=category, description=description, icon=icon, actions=actions, note=note)


folder = lambda: f('folder', 'Folder path', 'folder', required=True)
file = lambda name='file', label='File': f(name, label, 'file', required=True)
recursive = lambda: f('recursive', 'Include subfolders', 'checkbox', True)
query = lambda: f('query', 'Search or question', 'textarea', required=True)
mode = lambda: f('mode', 'Search mode', 'select', 'keyword', options=['keyword', 'semantic'])
month = lambda: f('month', 'Month', 'month')
identifier = lambda label='Record ID', name='id': f(name, label, required=True)
url = lambda: f('url', 'Website URL', 'url', required=True)
selector = lambda: f('selector', 'CSS selector', help='Optional: watch only part of a page, e.g. .price')
email = lambda: f('email', 'Email me when it changes', 'checkbox', False, 'Uses SMTP settings in .env')
botfields = lambda: [f('provider', 'Service', 'select', 'telegram', options=['telegram', 'discord']),
                     f('message', 'Message or question', 'textarea', required=True)]
cleanfields = lambda: [file(), f('sheet', 'Excel sheet name', help='Blank uses the first sheet'),
    f('trim', 'Trim whitespace', 'checkbox', True), f('normalize_headers', 'Normalize headers', 'checkbox', True),
    f('deduplicate', 'Remove duplicate rows', 'checkbox', True), f('fill', 'Fill empty cells with'),
    f('date_columns', 'Date columns', help='Comma-separated column names'),
    f('date_format', 'Input date format', value='%d/%m/%Y', help='%d/%m/%Y or %Y-%m-%d')]
apifields = lambda: [f('name', 'Request name'), url(),
    f('method', 'Method', 'select', 'GET', options=['GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS']),
    f('headers', 'Headers (JSON)', 'textarea', '{}'), f('body', 'Request body', 'textarea'),
    f('timeout', 'Timeout in seconds', 'number', 25)]
pdffields = lambda: [f('files', 'PDF files, one path per line', 'files', required=True),
    f('pages', 'Pages', help='Blank = all. Example: 1-3,5. Applies to first PDF except Merge.'),
    f('password', 'PDF password if encrypted', 'password')]
scrapefields = lambda: [url(), f('selector', 'Row CSS selector', value='article', required=True),
    f('fields', 'Columns → CSS selectors (JSON)', 'textarea', '{"title":"h2","link":"a@href"}'),
    f('respect_robots', 'Respect robots.txt', 'checkbox', True)]

TOOLS = [
 t('rename', 'Bulk renamer', 'Files & security', 'Give a whole folder a consistent name, with a preview first.', 'Aa',
   [a('preview', 'Preview rename', [folder(), f('pattern', 'Filename pattern', value='{name}_{n:03d}{ext}', required=True,
       help='Use {name}, {ext}, {n:03d}, {date}, {year}, {month}, {day}'),
       f('date_source', 'Date source', 'select', 'modified', options=['modified', 'exif']), recursive()])],
   'EXIF uses DateTimeOriginal, then image date, then modification time. Existing destinations are never intentionally overwritten.'),
 t('duplicates', 'Duplicate finder', 'Files & security', 'Find identical files by SHA-256 and recover space safely.', '≋',
   [a('scan','Find duplicates',[folder(),recursive()]), a('quarantine','Preview cleanup',[folder(),recursive()])]),
 t('clipboard', 'Clipboard history', 'Files & security', 'Search saved snippets, or opt into automatic clipboard capture.', '▣',
   [a('search','Search',[f('query','Search text')]), a('save','Save snippet',[f('text','Snippet','textarea',required=True)],'write'),
    a('start','Enable capture',[], 'sensitive'), a('stop','Stop capture',[],'write'),
    a('copy','Copy text',[f('text','Text','textarea',required=True)],'write'), a('clear','Clear history',[],'destructive')],
   'Capture is off at startup. When enabled, all copied text may include secrets. Only the last 1,000 snippets are retained.'),
 t('passwords','Password lab','Files & security','Generate secure passwords or passphrases; check breach exposure.','✳',
   [a('generate','Generate',[f('mode','Type','select','password',options=['password','passphrase']),
      f('length','Password length','number',24),f('words','Passphrase words','number',8)]),
    a('check','Check exposure',[f('password','Password','password',required=True)])],
   'Breach checks use the Pwned Passwords hash-range API. Passwords are never written to history.'),
 t('organize','Downloads organizer','Files & security','Sort a folder into document, image, audio and other folders.','↳',
   [a('preview','Preview organization',[folder()])]),
 t('markdown','Markdown converter','Files & security','Export Markdown as an HTML document or a readable text PDF.','M↓',
   [a('convert','Convert',[f('file','Markdown file (optional)','file'),f('text','Or paste Markdown','textarea'),
      f('format','Export as','select','html',options=['html','pdf'])])]),
 t('expenses','Expense tracker','Daily life','Log spending, compare categories and export monthly reports.','£',
   [a('summary','Monthly summary',[month()]),a('add','Add expense',[
      f('amount','Amount','number',required=True),f('currency','Currency',value='GBP'),f('date','Date','date'),
      f('category','Category',value='Other'),f('note','Note'),month()],'write'),
    a('export','Export month',[month()]),a('delete','Delete expense',[identifier(),month()],'destructive')]),
 t('timer','Focus timer','Daily life','Run a Pomodoro timer and keep a weekly record of time spent.','◷',
   [a('status','This week',[f('week_start','Week starting','date')]),
    a('start','Start focus',[f('task','Task',required=True),f('minutes','Focus minutes','number',25)],'write'),
    a('stop','Stop & save',[],'write'),a('export','Export week',[f('week_start','Week starting','date')])]),
 t('monitor','Website monitor','Daily life','Compare page snapshots and get a local or email notification.','◉',
   [a('check','Check page',[url(),selector(),email()],schedule=True)],
   'Schedule checks in the form below. Monitoring runs while LocalDesk is open. JavaScript-rendered content is not evaluated.'),
 t('habits','Habit tracker','Daily life','Build routines with daily check-ins and current and longest streaks.','✓',
   [a('list','Progress'),a('create','New habit',[f('name','Habit name',required=True)],'write'),
    a('check','Check in',[identifier('Habit ID'),f('date','Date','date')],'write'),
    a('uncheck','Undo check-in',[identifier('Habit ID'),f('date','Date','date')],'write'),
    a('delete','Delete habit',[identifier('Habit ID')],'destructive')]),
 t('rss','News digest','Daily life','Read RSS and Atom feeds in one place, or email yourself a digest.','◔',
   [a('read','Read feeds',[f('urls','Feed URLs, one per line','textarea',required=True),f('limit','Max stories','number',30)]),
    a('email','Email digest',[f('urls','Feed URLs, one per line','textarea',required=True),f('limit','Max stories','number',30)],'external',True),
    a('export','Export digest',[f('urls','Feed URLs, one per line','textarea',required=True)])]),
 t('pdf','PDF toolkit','Daily life','Merge, split, compress, select pages, or extract embedded text.','▤',
   [a(key,label,pdffields()) for key,label in [('extract','Extract text'),('merge','Merge PDFs'),('split','Split pages'),
                                            ('select','Select pages'),('compress','Compress')]]),
 t('logs','Log analyzer','Developer','Find error patterns, traffic spikes and top IP addresses.','⌁',
   [a('analyze','Analyze log',[file()])]),
 t('api','API workbench','Developer','Send HTTP requests and save reusable request definitions.','{ }',
   [a('send','Send request',apifields(),'external'),a('save','Save request',apifields(),'write'),a('list','Saved requests')],
   'Saved requests include their headers and body in local SQLite storage. Avoid saving authentication secrets.'),
 t('git','Git insights','Developer','See contributions, busiest days and file churn in any local repository.','⑂',
   [a('analyze','Analyze repository',[folder(),f('days','Look back days','number',365)])]),
 t('config','Config checker','Developer','Compare .env keys and find missing, empty or different values.','⚙',
   [a('compare','Compare files',[file('reference','Reference .env'),file('actual','Actual .env')])]),
 t('todos','TODO scanner','Developer','Collect TODO, FIXME, HACK and XXX markers across a project.','☷',
   [a('scan','Scan project',[folder()])]),
 t('scaffold','Project starter','Developer','Download a ready-to-run Python CLI, web app or data project.','⊞',
   [a('create','Create project',[f('name','Project name',value='my-project',required=True),
       f('template','Template','select','python-cli',options=['python-cli','web-app','data-project'])])]),
 t('scrape','Scheduled scraper','Data & automation','Extract rows from web pages into CSV and SQLite snapshots.','⌘',
   [a('scrape','Collect data',scrapefields(),schedule=True),a('history','Saved runs')],
   'CSS selectors read server HTML. A selector followed by @href or @src extracts an attribute.'),
 t('cleaner','Table cleaner','Data & automation','Clean CSV or Excel data with a preview and a separate output file.','▦',
   [a('preview','Preview cleanup',cleanfields()),a('clean','Clean & export',cleanfields()+[
       f('format','Export format','select','csv',options=['csv','xlsx'])])]),
 t('dashboard','Personal dashboard','Data & automation','Bring your tasks, calendar, weather and habits together.','◫',
   [a('overview','Overview'),a('add_task','Add task',[f('title','Task',required=True),f('due','Due date','date')],'write'),
    a('complete','Toggle task done',[identifier('Task ID')],'write'),
    a('delete_task','Delete task',[identifier('Task ID')],'destructive'),
    a('weather','Weather',[f('city','City',required=True)]),a('import_calendar','Import calendar',[file('file','Calendar .ics')],'write')]),
 t('email-sort','Email sorter','Data & automation','Preview IMAP rules, then file matching messages into folders.','✉',
   [a('preview','Preview rules',[f('folder','Source folder',value='INBOX'),f('limit','Recent messages','number',100),
       f('rules','Rules (JSON)','textarea','[{"field":"from","contains":"shop","folder":"Receipts"}]',required=True)])],
   'Uses IMAP credentials from .env. Apply copies matches and flags originals Deleted; it never expunges mail.'),
 t('ocr','Receipt reader','Data & automation','Extract text and likely totals and dates from receipt photos.','▧',
   [a('extract','Read receipt',[file(),f('language','Tesseract language',value='eng')])],
   'Requires the Tesseract executable and language data in addition to Python dependencies.'),
 t('bots','Bot studio','Creative','Send Telegram or Discord messages and polls, or run a Telegram reminder bot.','♟',
   [a('send','Send message',botfields(),'external',True),
    a('poll','Send poll',botfields()+[f('options','Options, one per line','textarea',required=True)],'external',True),
    a('quiz','Send quiz',botfields()+[f('options','Options, one per line','textarea',required=True),
       f('correct','Correct option index (first = 0)','number',0)],'external'),
    a('listen','Poll Telegram commands',[],'external',True)],
   'Requires service credentials. Schedule Poll Telegram commands every 15 seconds. Only TELEGRAM_CHAT_ID is allowed to issue commands.'),
 t('game','Lantern Vault','Creative','A small, persistent dungeon adventure. Find gold and escape.','♜',
   [a('play','Play turn',[f('command','Command',value='look',help='new, look, north, south, east, west, attack, drink')],'write')]),
 t('wordle','Wordle companion','Creative','Filter candidates and rank suggestions by feedback information.','W',
   [a('solve','Find suggestions',[f('history','Guesses & feedback','textarea',help='One per line: crane 01200. 0 gray, 1 yellow, 2 green.'),
       f('file','Custom word list (optional)','file')])]),
 t('ascii','ASCII studio','Creative','Turn a picture into text art, ready to copy or download.','▒',
   [a('convert','Make ASCII art',[file(),f('width','Width in characters','number',90),f('ramp','Brightness characters',value='@%#*+=-:. '),
       f('invert','Invert brightness','checkbox',False)])]),
 t('playlist','Playlist insights','Creative','Find artists, listening habits and trends in your Spotify exports.','♫',
   [a('analyze','Analyze listening',[file()])]),
 t('knowledge','Knowledge search','Advanced','Index notes and text PDFs, then search by keyword or local embeddings.','⌕',
   [a('search','Search',[query(),mode()]),a('index','Index folder',[folder(),mode()],'write'),a('stats','Index overview'),
    a('clear','Clear index',[],'destructive')],
   'Semantic indexing requires Ollama and an embedding model. Keyword search works without AI services.'),
 t('assistant','Document assistant','Advanced','Ask a local AI questions with references to your indexed documents.','✧',
   [a('chat','Ask your documents',[query(),mode()])],
   'Requires Ollama and a chat model. Index documents in Knowledge search first.'),
 t('backtest','Strategy lab','Advanced','Compare a moving-average strategy to buy and hold using historical CSV data.','↗',
   [a('run','Run backtest',[file(),f('strategy','Strategy','select','sma',options=['sma','buy_hold']),
      f('capital','Initial capital','number',10000),f('fast','Fast moving average','number',10),
      f('slow','Slow moving average','number',30),f('fee_bps','Fee (basis points)','number',10),
      f('slippage_bps','Slippage (basis points)','number',5)])],
   'Use columns date and close. One basis point = 0.01%. The simulator uses delayed signals and includes transaction costs.'),
 t('home','Home hub','Advanced','Save HTTP or MQTT devices, issue commands and run schedules.','⌂',
   [a('list','Devices'),a('add','Add device',[f('name','Device name',required=True),
      f('protocol','Protocol','select','http',options=['http','mqtt']),f('endpoint','HTTP URL or MQTT topic',required=True),
      f('method','HTTP method','select','POST',options=['GET','POST','PUT','PATCH']),
      f('auth_env','Bearer-token environment variable')],'write'),
    a('control','Control device',[identifier('Device ID','device_id'),f('payload','Command payload','textarea','{}')],'external',True),
    a('delete','Remove device',[identifier('Device ID','device_id')],'destructive')]),
 t('file-history','File history','System','Review applied file changes and create an undo preview.','↶',
   [a('list','History'),a('undo','Preview undo',[identifier('Journal ID','journal_id')])])
]

BY_ID = {tool['id']: tool for tool in TOOLS}
