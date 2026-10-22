"""Offline integration checks. Run: python -m unittest discover -s tests -v"""
from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import zipfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from localdesk import core, engine
from localdesk.catalog import TOOLS
from localdesk.tools import advanced, creative, data, developer, files, productivity


class ToolboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.old_data = core.DATA
        core.DATA = self.root / 'appdata'
        # File module retains a data constant used by quarantine destinations.
        self.old_files_data = files.DATA
        files.DATA = core.DATA
        core.initialize()

    def tearDown(self):
        core.DATA = self.old_data
        files.DATA = self.old_files_data
        self.temp.cleanup()

    def fixture(self, name, text):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding='utf-8')
        return str(p)

    def test_catalog_all_32_tools_have_handlers(self):
        self.assertEqual(len([t for t in TOOLS if t['category'] != 'System']), 32)
        self.assertEqual({t['id'] for t in TOOLS}, set(engine.HANDLERS))
        with self.assertRaises(core.ToolError):
            engine.execute('home', {'action':'made-up'})

    def test_rename_preview_apply_undo_and_stale_source(self):
        folder = self.root / 'rename'
        self.fixture('rename/a.txt', 'one')
        preview = engine.execute('rename', {'action':'preview','folder':str(folder),'pattern':'{n:03d}{ext}'})
        self.assertTrue((folder / 'a.txt').exists())
        result = core.apply_plan(preview['plan_id'])
        self.assertEqual((folder / '001.txt').read_text(), 'one')
        undo = files.file_history({'action':'undo','journal_id':result['journal_id']})
        core.apply_plan(undo['plan_id'])
        self.assertTrue((folder / 'a.txt').exists())
        fresh = files.rename({'folder':str(folder),'pattern':'new{ext}'})
        (folder / 'a.txt').write_text('changed')
        with self.assertRaises(core.ToolError): core.apply_plan(fresh['plan_id'])
        self.assertFalse((folder / 'new.txt').exists())

    def test_collision_rejects_without_moving(self):
        self.fixture('collision/a.txt','a'); self.fixture('collision/b.txt','b')
        with self.assertRaises(core.ToolError):
            files.rename({'folder':str(self.root/'collision'),'pattern':'same.txt'})
        self.assertTrue((self.root/'collision/a.txt').exists())

    def test_duplicates_quarantine_is_recoverable(self):
        self.fixture('duplicates/a.txt','same');self.fixture('duplicates/b.txt','same')
        preview=files.duplicates({'folder':str(self.root/'duplicates'),'action':'quarantine'})
        self.assertEqual(preview['reclaimable_bytes'],4)
        result=core.apply_plan(preview['plan_id'])
        self.assertTrue((self.root/'duplicates/a.txt').exists())
        self.assertFalse((self.root/'duplicates/b.txt').exists())
        core.apply_plan(core.undo_plan(result['journal_id'])['plan_id'])
        self.assertTrue((self.root/'duplicates/b.txt').exists())

    def test_organizer(self):
        self.fixture('downloads/song.mp3','data')
        result=files.organize({'folder':str(self.root/'downloads')})
        core.apply_plan(result['plan_id'])
        self.assertTrue((self.root/'downloads/Audio/song.mp3').exists())

    def test_password_generation_and_hash_range_privacy(self):
        password=engine.execute('passwords',{'action':'generate','length':24})['password']
        self.assertEqual(len(password),24)
        self.assertTrue(any(c.isdigit() for c in password))
        self.assertEqual(len(files.passwords({'mode':'passphrase','words':8})['password'].split('-')),8)
        import hashlib
        secret='test-password-value';hashed=hashlib.sha1(secret.encode()).hexdigest().upper()
        with patch.object(files,'http',return_value={'status':200,'text':hashed[5:]+':17\r\n'}) as mocked:
            result=engine.execute('passwords',{'action':'check','password':secret})
            self.assertEqual(result['breach_count'],17)
            self.assertNotIn(secret,str(mocked.call_args))
        self.assertFalse(core.records('activity'))

    def test_clipboard_manual_search_and_clear(self):
        files.clipboard({'action':'save','text':'searchable note'})
        self.assertEqual(len(files.clipboard({'query':'NOTE'})['entries']),1)
        self.assertFalse(files.clipboard({})['capture_enabled'])
        self.assertFalse(files.clipboard({'action':'clear'})['entries'])

    def test_expense_money_month_filter_and_csv_formula(self):
        for value in ('0.10','0.20'):
            productivity.expenses({'action':'add','amount':value,'currency':'GBP','date':'2026-01-03','note':'=SUM(A1)'})
        result=productivity.expenses({'month':'2026-01','action':'export'})
        self.assertEqual(result['totals']['GBP'],0.3)
        self.assertIn("'=SUM(A1)",Path(result['download']['path']).read_text())
        self.assertFalse(productivity.expenses({'month':'2026-02'})['expenses'])

    def test_timer_stop_and_report(self):
        productivity.timer({'action':'start','task':'Deep work','minutes':25})
        with self.assertRaises(core.ToolError): productivity.timer({'action':'start','task':'Other'})
        active=core.get('timer');active['start']-=120;core.put('timer',active)
        result=productivity.timer({'action':'stop'})
        self.assertIsNone(result['active'])
        self.assertGreaterEqual(result['sessions'][0]['minutes'],2)
        self.assertIn('download',productivity.timer({'action':'export'}))

    def test_habit_streaks_and_idempotent_checkin(self):
        habit=productivity.habits({'action':'create','name':'Read'})['habits'][0]
        for delta in (0,1,2,2):
            productivity.habits({'action':'check','id':habit['id'],'date':(date.today()-timedelta(days=delta)).isoformat()})
        result=productivity.habits({})['habits'][0]
        self.assertEqual(result['streak'],3);self.assertEqual(result['longest'],3)
        self.assertEqual(len(result['days']),3)

    def test_monitor_snapshots_change_and_notification(self):
        with patch.object(productivity,'page_text',side_effect=['Price 10','Price 10','Price 12']):
            self.assertFalse(productivity.monitor({'url':'https://example.test'})['changed'])
            self.assertFalse(productivity.monitor({'url':'https://example.test'})['changed'])
            self.assertTrue(productivity.monitor({'url':'https://example.test'})['changed'])
        self.assertEqual(len(core.records('notification')),1)

    def test_rss_and_atom(self):
        rss=b'<rss><channel><item><title>One</title><link>https://example.test/one</link></item></channel></rss>'
        atom=b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Two</title><link href="https://example.test/two"/></entry></feed>'
        with patch.object(productivity,'http',side_effect=[{'status':200,'bytes':rss},{'status':200,'bytes':atom}]):
            result=productivity.rss({'urls':'https://one.test\nhttps://two.test'})
        self.assertEqual(len(result['items']),2);self.assertEqual(result['items'][1]['title'],'Two')

    def test_tasks_and_weather(self):
        task=productivity.dashboard({'action':'add_task','title':'Finish report'})['tasks'][0]
        self.assertTrue(productivity.dashboard({'action':'complete','id':task['id']})['tasks'][0]['done'])
        with patch.object(productivity,'fetch_json',side_effect=[{'results':[{'name':'London','country':'UK','latitude':1,'longitude':2}]},{'current':{'temperature_2m':16}}]):
            self.assertEqual(productivity.dashboard({'action':'weather','city':'London'})['weather']['temperature_2m'],16)

    def test_log_analysis(self):
        log=self.fixture('server.log','2026-01-01 10:01:00 ERROR Failed user 123 from 1.2.3.4\n2026-01-01 10:02:00 ERROR Failed user 456 from 1.2.3.4\n')
        result=developer.logs({'file':log})
        self.assertEqual(result['levels']['ERROR'],2);self.assertEqual(result['top_errors'][0]['count'],2)

    def test_api_save_and_send(self):
        p={'action':'save','name':'Example','url':'https://example.test','headers':'{}','method':'GET'}
        developer.api(p);self.assertEqual(len(developer.api({'action':'list'})['requests']),1)
        with patch.object(developer,'http',return_value={'status':201,'elapsed_ms':10,'headers':{},'text':'ok'}):
            self.assertEqual(developer.api({**p,'action':'send'})['status'],201)

    @unittest.skipUnless(shutil.which('git'),'Git not on PATH')
    def test_git_real_repository(self):
        repo=self.root/'repo';repo.mkdir()
        def git(*args):
            subprocess.run(['git','-C',str(repo),*args],check=True,capture_output=True)
        git('init');self.fixture('repo/hello.txt','hello\n');git('add','.')
        git('-c','user.name=Test Author','-c','user.email=test@example.test','commit','-m','Initial')
        result=developer.git({'folder':str(repo),'days':365})
        self.assertEqual(result['commits'],1);self.assertEqual(result['authors']['Test Author'],1)

    def test_config_values_never_exposed(self):
        reference=self.fixture('reference.env','SECRET=supersecret\nNEEDED=yes\n')
        actual=self.fixture('actual.env','SECRET=differentsecret\nEMPTY=\nSECRET=lastsecret\n')
        result=developer.config({'reference':reference,'actual':actual})
        self.assertEqual(result['missing_variables'],['NEEDED'])
        self.assertEqual(result['duplicate_keys_actual'],['SECRET'])
        self.assertNotIn('supersecret',json.dumps(result));self.assertNotIn('lastsecret',json.dumps(result))

    def test_todo_scan_and_scaffold_runnable_python(self):
        self.fixture('project/main.py','# TODO: write meaningful tests\n')
        self.assertEqual(len(developer.todos({'folder':str(self.root/'project')})['items']),1)
        for template in developer.TEMPLATES:
            result=developer.scaffold({'name':'hello','template':template})
            with zipfile.ZipFile(result['download']['path']) as z:
                for name in z.namelist():
                    if name.endswith('.py'):compile(z.read(name),name,'exec')

    def test_csv_cleaning_and_no_original_mutation(self):
        csv=self.fixture('messy.csv',' Name ,Date\n Alice ,22/10/2026\n Alice ,22/10/2026\nBob,invalid\n')
        before=Path(csv).read_text()
        result=data.cleaner({'file':csv,'action':'clean','date_columns':'date'})
        self.assertEqual(result['output_rows'],2);self.assertEqual(result['duplicate_rows'],1)
        self.assertEqual(result['preview'][0]['name'],'Alice')
        self.assertEqual(result['preview'][0]['date'],'2026-10-22')
        self.assertEqual(len(result['invalid_dates']),1);self.assertEqual(Path(csv).read_text(),before)

    @unittest.skipUnless(__import__('importlib').util.find_spec('openpyxl'),'Excel dependency missing')
    def test_excel_cleaning(self):
        csv=self.fixture('table.csv','name,value\nAlice,10\n')
        result=data.cleaner({'file':csv,'action':'clean','format':'xlsx'})
        headers,rows,_=data.read_table(result['download']['path'])
        self.assertEqual(headers,['name','value']);self.assertEqual(rows[0]['name'],'Alice')

    @unittest.skipUnless(__import__('importlib').util.find_spec('bs4'),'HTML dependency missing')
    def test_scraper_css_and_snapshots(self):
        with patch.object(data,'http',return_value={'status':200,'text':'<article><h2>Title</h2><a href="/x">Go</a></article>'}):
            result=data.scrape({'url':'https://example.test','respect_robots':False,'selector':'article','fields':'{"title":"h2","url":"a@href"}'})
        self.assertEqual(result['rows'][0]['url'],'https://example.test/x')
        self.assertEqual(len(core.records('scrape')),1)

    def test_wordle_duplicate_letters(self):
        self.assertEqual(creative.feedback('alley','apple'),'21010')
        words=self.fixture('words.txt','apple\nample\nalley\n')
        result=creative.wordle({'file':words,'history':'alley 21010'})
        self.assertIn('apple',result['candidates'])
        self.assertNotIn('alley',result['candidates'])

    def test_game_persists_turns_and_walls(self):
        creative.game({'command':'new'});creative.game({'command':'east'})
        result=creative.game({'command':'south'})
        self.assertIn('wall',result['message']);self.assertEqual(core.get('game')['x'],1)

    @unittest.skipUnless(__import__('importlib').util.find_spec('PIL'),'Image dependency missing')
    def test_ascii_real_image(self):
        from PIL import Image
        image=self.root/'image.png';Image.new('RGB',(100,100),'white').save(image)
        result=creative.ascii_art({'file':str(image),'width':20})
        self.assertEqual(len(result['ascii'].splitlines()),10)

    def test_spotify_legacy_and_extended_formats(self):
        for record in [{'artistName':'Artist','trackName':'Song','msPlayed':3600000,'endTime':'2026-01-01 10:00'},
                       {'master_metadata_album_artist_name':'Artist','master_metadata_track_name':'Song','ms_played':3600000,'ts':'2026-01-01T10:00:00Z'}]:
            file=self.fixture('history.json',json.dumps([record]))
            self.assertEqual(creative.playlist({'file':file})['listening_hours'],1)

    def test_knowledge_keyword_reindex_and_semantic_chat_contract(self):
        self.fixture('notes/one.md','The lantern workshop opens on Tuesday. Bring the blue notebook.')
        advanced.knowledge({'action':'index','folder':str(self.root/'notes'),'mode':'keyword'})
        self.assertIn('Tuesday',advanced.knowledge({'query':'workshop opens'})['matches'][0]['text'])
        advanced.knowledge({'action':'index','folder':str(self.root/'notes'),'mode':'keyword'})
        self.assertEqual(len(core.records('chunk')),1)
        with patch.object(advanced,'ollama',return_value={'embeddings':[[1,0,0]]}):
            advanced.knowledge({'action':'index','folder':str(self.root/'notes'),'mode':'semantic'})
            self.assertEqual(len(advanced.knowledge({'query':'schedule','mode':'semantic'})['matches']),1)
        with patch.object(advanced,'ollama',return_value={'message':{'content':'Tuesday [1].'}}):
            result=advanced.assistant({'query':'When does the workshop open?'})
            self.assertIn('[1]',result['answer']);self.assertEqual(len(result['sources']),1)

    def test_backtest_delayed_signal_and_no_fee_buy_hold(self):
        file=self.fixture('prices.csv','date,close\n2026-01-01,10\n2026-01-02,11\n2026-01-03,12\n2026-01-04,13\n2026-01-05,14\n')
        result=advanced.backtest({'file':file,'fast':1,'slow':2,'fee_bps':0,'slippage_bps':0,'capital':100})
        self.assertEqual(result['trades'][0]['date'],'2026-01-03')
        hold=advanced.backtest({'file':file,'strategy':'buy_hold','fee_bps':0,'slippage_bps':0,'capital':100})
        self.assertEqual(hold['final_equity'],140)

    def test_home_http_device_and_env_auth(self):
        device=advanced.home({'action':'add','name':'Lamp','endpoint':'http://device.test/api','auth_env':'LAMP_TOKEN'})['device_id']
        with patch.dict(os.environ,{'LAMP_TOKEN':'private'}),patch.object(advanced,'http',return_value={'status':200,'text':'ok'}) as mocked:
            result=advanced.home({'action':'control','device_id':device,'payload':'{"on":true}'})
            self.assertEqual(result['status'],200)
            self.assertIn('Bearer private',str(mocked.call_args))
        self.assertNotIn('private',json.dumps(advanced.home({})))

    def test_telegram_poll_and_allowed_chat_only(self):
        with patch.dict(os.environ,{'TELEGRAM_CHAT_ID':'123'}),patch.object(creative,'telegram',return_value={}) as mocked:
            creative.bots({'action':'quiz','message':'Test?','options':'Yes\nNo','correct':0})
            self.assertEqual(mocked.call_args.args[0],'sendPoll')
            self.assertEqual(mocked.call_args.args[1]['options'][0],{'text':'Yes'})
        updates=[{'update_id':1,'message':{'chat':{'id':999},'text':'/remind 5 bad'}},
                 {'update_id':2,'message':{'chat':{'id':123},'text':'/remind 5 good'}}]
        with patch.dict(os.environ,{'TELEGRAM_CHAT_ID':'123'}),patch.object(creative,'telegram',side_effect=[updates,{}]):
            self.assertIn('1 messages',creative.bots({'action':'listen'})['message'])
        self.assertEqual(core.records('bot_reminder')[0]['message'],'good')

    def test_email_preview_apply_no_expunge_or_replay(self):
        from unittest.mock import MagicMock
        client=MagicMock()
        client.select.return_value=('OK',[b'1'])
        client.response.return_value=('UIDVALIDITY',[b'42'])
        def uid(command,*args):
            if command=='SEARCH':return ('OK',[b'10'])
            if command=='FETCH':return ('OK',[(b'header',b'From: shop@example.test\r\nSubject: Receipt\r\nMessage-ID: <one>\r\n')])
            return ('OK',[b'done'])
        client.uid.side_effect=uid
        with patch.object(data,'imap_client',return_value=client):
            preview=data.email_sort({'rules':'[{"field":"from","contains":"shop","folder":"Receipts"}]'})
            self.assertEqual(len(preview['messages']),1)
            self.assertFalse(any(c.args[0]=='COPY' for c in client.uid.call_args_list))
            result=data.email_sort({'action':'apply','plan_id':preview['email_plan_id']})
            self.assertEqual(len(result['moved']),1)
            self.assertFalse(client.expunge.called)
            with self.assertRaises(core.ToolError):data.email_sort({'action':'apply','plan_id':preview['email_plan_id']})

    @unittest.skipUnless(__import__('importlib').util.find_spec('PIL'),'Image dependency missing')
    def test_receipt_ocr_total_and_date_extraction(self):
        from PIL import Image
        from types import SimpleNamespace
        image=self.root/'receipt.png';Image.new('RGB',(100,100),'white').save(image)
        fake=SimpleNamespace(image_to_string=lambda *a,**k:'SHOP\n22/10/2026\nSubtotal 10.00\nTotal GBP 12.50\n',
                             TesseractNotFoundError=RuntimeError,pytesseract=SimpleNamespace())
        real_need=core.need
        with patch.object(data,'need',side_effect=lambda module,package=None:fake if module=='pytesseract' else real_need(module,package)):
            result=data.ocr({'file':str(image)})
        self.assertEqual(result['total_candidates'][0]['amount'],'12.50')
        self.assertEqual(result['date_candidates'],['22/10/2026'])

    def test_exclusive_move_preserves_existing_destination(self):
        source=self.fixture('source.txt','original')
        destination=self.fixture('destination.txt','keep me')
        with self.assertRaises(FileExistsError):core.move_without_overwrite(source,destination)
        self.assertEqual(Path(destination).read_text(),'keep me')
        self.assertEqual(Path(source).read_text(),'original')

    def test_jobs_persist_claim_once_and_record_failures(self):
        saved=engine.save_job({'tool':'monitor','payload':{'action':'check','url':'https://example.test'},'interval':0,'delay':1})
        with core.connection() as db:db.execute('UPDATE jobs SET next_run=0 WHERE id=?',(saved['job_id'],))
        with patch.object(engine,'execute',return_value={'message':'done'}):
            engine.tick_jobs()
            for _ in range(100):
                if engine.jobs()[0]['status']!='Running':break
                time.sleep(.01)
        self.assertEqual(engine.jobs()[0]['status'],'Succeeded');self.assertFalse(engine.jobs()[0]['enabled'])
        with patch.object(engine,'execute',side_effect=core.ToolError('service offline')):
            engine.run_job(engine.jobs()[0])
        self.assertEqual(engine.jobs()[0]['status'],'Failed')
        self.assertTrue(core.records('notification'))
        with self.assertRaises(core.ToolError):engine.save_job({'tool':'home','payload':{'action':'delete'},'interval':60})

    @unittest.skipUnless(__import__('importlib').util.find_spec('markdown'),'Markdown dependency missing')
    def test_markdown_exports_html_with_restrictive_policy(self):
        result=files.markdown({'text':'# Hello\n\n**world**','format':'html'})
        text=Path(result['download']['path']).read_text()
        self.assertIn('<h1>Hello</h1>',text);self.assertIn('Content-Security-Policy',text)

    @unittest.skipUnless(__import__('importlib').util.find_spec('reportlab') and __import__('importlib').util.find_spec('pypdf'),'PDF dependencies missing')
    def test_pdf_merge_split_extract_and_compress(self):
        first=files.text_pdf('Hello first PDF','one.pdf')['download']['path']
        second=files.text_pdf('Hello second PDF','two.pdf')['download']['path']
        merged=files.pdf({'action':'merge','files':first+'\n'+second})['download']['path']
        self.assertIn('second PDF',files.pdf({'action':'extract','files':merged})['text'])
        split=files.pdf({'action':'split','files':merged})['download']['path']
        with zipfile.ZipFile(split) as z:self.assertEqual(len(z.namelist()),2)
        self.assertGreater(files.pdf({'action':'compress','files':merged})['output_bytes'],0)

    @unittest.skipUnless(__import__('importlib').util.find_spec('icalendar'),'Calendar dependency missing')
    def test_ical_import_idempotent(self):
        file=self.fixture('calendar.ics','BEGIN:VCALENDAR\nVERSION:2.0\nBEGIN:VEVENT\nUID:test-one\nDTSTART:20990101T090000Z\nSUMMARY:Meeting\nEND:VEVENT\nEND:VCALENDAR\n')
        for _ in range(2):productivity.dashboard({'action':'import_calendar','file':file})
        self.assertEqual(len(core.records('calendar')),1)

    def test_http_api_rejects_cross_origin_and_missing_tokens(self):
        server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        base=f'http://127.0.0.1:{server.server_address[1]}'
        try:
            with urllib.request.urlopen(base+'/api/bootstrap') as r:bootstrap=json.load(r)
            self.assertEqual(len(bootstrap['tools']),33)
            req=urllib.request.Request(base+'/api/run/habits',data=b'{"action":"list"}',headers={'Content-Type':'application/json'})
            with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(req)
            self.assertEqual(error.exception.code,403)
            req.add_header('X-LocalDesk-Token',app.TOKEN)
            with urllib.request.urlopen(req) as r:self.assertIn('habits',json.load(r))
            req.add_header('Origin','https://evil.example')
            with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(req)
            self.assertEqual(error.exception.code,403)
            with urllib.request.urlopen(base+'/') as r:self.assertEqual(r.status,200)
        finally:
            server.shutdown();server.server_close()


if __name__=='__main__':unittest.main()
