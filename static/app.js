'use strict';

const state = {tools: [], token: '', status: {}, overview: {}, current: '', action: '', forms: {}, renderId: 0,
  favorites: new Set(JSON.parse(localStorage.getItem('localdesk-favorites') || '["rename","expenses","timer","pdf","todos","passwords"]')),
  seenNotifications: new Set()};
const $ = (s, parent = document) => parent.querySelector(s);
const $$ = (s, parent = document) => [...parent.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const label = s => String(s).replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
const categories = [...new Set(['Files & security','Daily life','Developer','Data & automation','Creative','Advanced'])];
const catIcons = ['▱','◷','⌘','▦','✧','⌁'];
const toolById = id => state.tools.find(t => t.id === id);
const main = $('#main');
let clockInterval;

function el(tag, cls, text) { const node = document.createElement(tag); if (cls) node.className = cls; if (text != null) node.textContent = text; return node; }
function toast(text) { const node = el('div', 'toast', text); $('#toasts').append(node); setTimeout(() => node.remove(), 4500); }
function button(text, handler, cls = 'button small') { const b = el('button', cls, text); b.type = 'button'; b.addEventListener('click', handler); return b; }
function dateText(ts) { return ts ? new Date(ts * 1000).toLocaleString([], {dateStyle:'medium', timeStyle:'short'}) : 'Not yet'; }
function ago(ts) { const n = Math.max(0, Math.floor((Date.now()/1000 - ts)/60)); return n < 1 ? 'just now' : n < 60 ? `${n} min ago` : n < 1440 ? `${Math.floor(n/60)} hr ago` : `${Math.floor(n/1440)} days ago`; }

async function request(path, body, options = {}) {
  const config = {headers: {'X-LocalDesk-Token': state.token}, ...options};
  if (body !== undefined) { config.method = 'POST'; config.headers = {...config.headers, 'Content-Type':'application/json'}; config.body = JSON.stringify(body); }
  const res = await fetch(path, config);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

function nav() {
  const raw = location.hash.slice(1) || 'overview';
  const page = raw.split('?')[0];
  const params = new URLSearchParams(raw.split('?')[1] || '');
  $('#main-nav').innerHTML = [['overview','◫','Overview'],['tools','⊞','All tools'],['favorites','☆','Favorites'],['jobs','◷','Schedules']].map(([key,icon,name]) =>
    `<a class="nav-item ${page===key?'active':''}" href="#${key}"><span>${icon}</span>${name}${key==='favorites'?`<span class="nav-count">${state.favorites.size}</span>`:''}</a>`).join('');
  $('#category-nav').innerHTML = categories.map((cat,i) => `<a class="nav-item ${params.get('category')===cat?'active':''}" href="#tools?category=${encodeURIComponent(cat)}"><span>${catIcons[i]}</span>${esc(cat)}<span class="nav-count">${state.tools.filter(t=>t.category===cat).length}</span></a>`).join('');
  $('#sidebar').classList.remove('open');
}

function setBreadcrumb(text, group = 'Workspace') { $('#breadcrumb').innerHTML = `${esc(group)} <span>/</span> <b>${esc(text)}</b>`; document.title = `${text} — LocalDesk`; }
function head(title, description, eyebrow = 'YOUR WORKSPACE') {
  const today = new Date().toLocaleDateString([], {weekday:'short', day:'numeric', month:'short', year:'numeric'});
  return `<div class="page-head"><div><div class="eyebrow">${esc(eyebrow)}</div><h1>${esc(title)}</h1><p>${esc(description)}</p></div><div class="date-pill"><span>▦</span>${esc(today)}</div></div>`;
}

function toolCard(tool) {
  return `<article class="tool-card" data-category="${esc(tool.category)}"><div class="tool-card-top"><span class="tool-icon">${esc(tool.icon)}</span><button class="favorite ${state.favorites.has(tool.id)?'on':''}" data-favorite="${tool.id}" aria-label="${state.favorites.has(tool.id)?'Unfavorite':'Favorite'} ${esc(tool.name)}" aria-pressed="${state.favorites.has(tool.id)}">${state.favorites.has(tool.id)?'★':'☆'}</button></div><h3><a href="#${tool.id}">${esc(tool.name)}</a></h3><p>${esc(tool.description)}</p><div class="tool-card-bottom"><span>${esc(tool.category)}</span><span>↗</span></div></article>`;
}

function bindFavorites(container = main) {
  $$('[data-favorite]', container).forEach(b => b.addEventListener('click', () => {
    const id = b.dataset.favorite;
    state.favorites.has(id) ? state.favorites.delete(id) : state.favorites.add(id);
    localStorage.setItem('localdesk-favorites', JSON.stringify([...state.favorites]));
    b.textContent = state.favorites.has(id) ? '★' : '☆'; b.classList.toggle('on', state.favorites.has(id));
    b.setAttribute('aria-pressed', String(state.favorites.has(id))); nav();
    if (location.hash === '#favorites') render();
  }));
}

function renderOverview() {
  setBreadcrumb('Overview');
  const o = state.overview;
  const tools = state.tools.filter(t => t.category !== 'System');
  let favorites = tools.filter(t => state.favorites.has(t.id)).slice(0,6);
  if (!favorites.length) favorites = tools.slice(0,6);
  const jobs = o.jobs || [];
  const done = (o.tasks || []).filter(t => t.done).length;
  main.innerHTML = head('A good day starts here.', 'One quiet place for the little things that take up your day.') +
    `<section class="hero"><div class="hero-copy"><div class="eyebrow">SMALL TOOLS. A LITTLE MORE HEADSPACE.</div><h2>A little less busywork.</h2><p>Organize your files, find your focus, and make everyday tasks a little easier. Your whole toolbox, right here.</p><a href="#tools" class="button">Explore your tools <span>↗</span></a></div><div class="hero-art" aria-hidden="true"><div class="art-grid"></div><span class="art-star">✧</span><span class="art-dot"></span><div class="art-tile one">✓</div><div class="art-tile two">▱</div><div class="art-tile three">◷</div><div class="art-tile four">⌘</div></div></section>` +
    `<div class="stats-grid"><div class="stat"><span class="stat-icon">⊞</span><div><strong>${tools.length}</strong><small>Tools, all in one place</small></div></div><div class="stat"><span class="stat-icon">◷</span><div><strong>${jobs.filter(j=>j.enabled).length}</strong><small>Active schedules</small></div></div><div class="stat"><span class="stat-icon">✓</span><div><strong>${done}<span class="stat-divider"> / ${o.tasks?.length || 0}</span></strong><small>Tasks checked off</small></div></div><div class="stat"><span class="stat-icon">↗</span><div><strong>${o.habits?.length || 0}</strong><small>Habits in progress</small></div></div></div>` +
    `<div class="section-head"><div><h2>Your everyday essentials</h2><p>A few favorites, always within reach.</p></div><a href="#favorites">All favorites ↗</a></div><div class="tool-grid">${favorites.map(toolCard).join('')}</div>` +
    `<div class="bottom-grid"><section class="panel"><div class="panel-title">Recent activity <span>YOUR LOCAL WORKSPACE</span></div><div id="activity-list"></div></section><section class="panel tip-panel"><div><div class="eyebrow">A LITTLE PEACE OF MIND</div><h3>Your desk. Your data.</h3><p>Files and trackers stay on this computer. Online tools connect to the services you choose. File changes start with a preview you can review.</p></div><a href="#settings">Make yourself at home ↗</a></section></div>`;
  const activity = $('#activity-list');
  if (!(o.activity || []).length) activity.innerHTML = '<div class="empty-state"><strong>A fresh workspace.</strong>Open a tool to get started. Your activity will appear here.</div>';
  else (o.activity || []).slice(0,4).forEach(r => {
    const tool = toolById(r.tool); if (!tool) return;
    const row = el('a','activity-item'); row.href = '#' + r.tool;
    row.append(el('span','activity-icon',tool.icon),el('span','',`${tool.name} · ${label(r.action)}`),el('small','',ago(r.time))); activity.append(row);
  });
  bindFavorites();
}

function renderGallery(favorite, category) {
  const title = favorite ? 'Your favorites.' : category ? `${category}.` : 'A tool for that.';
  setBreadcrumb(favorite ? 'Favorites' : category || 'All tools');
  main.innerHTML = head(title, favorite ? 'The tools you reach for most. Use the star to make this space yours.' : 'From small fixes to bigger ideas. Find a useful place to start.', 'THE TOOLBOX') +
    `<div class="section-head"><div class="tools-filter" id="filters"></div><input class="filter-search" id="filter-search" placeholder="Filter tools…" aria-label="Filter tools"></div><div class="tool-grid" id="gallery"></div>`;
  $('#filters').innerHTML = (favorite ? [] : ['All tools', ...categories]).map(c => `<button class="filter-pill ${(!category&&c==='All tools')||c===category?'active':''}" data-category="${esc(c)}">${esc(c)}</button>`).join('');
  $$('[data-category]', $('#filters')).forEach(b=>b.addEventListener('click',()=> location.hash = b.dataset.category === 'All tools' ? 'tools' : 'tools?category=' + encodeURIComponent(b.dataset.category)));
  const update = () => {
    const q = $('#filter-search').value.toLowerCase();
    const matches = state.tools.filter(t => t.category !== 'System' && (!favorite || state.favorites.has(t.id)) && (!category || category === t.category) && `${t.name} ${t.description} ${t.category}`.toLowerCase().includes(q));
    $('#gallery').innerHTML = matches.map(toolCard).join('') || '<div class="empty-state"><strong>No tools here yet.</strong>Try another search or star a tool.</div>';
    bindFavorites($('#gallery'));
  };
  $('#filter-search').addEventListener('input', update); update();
}

function renderField(field, value) {
  const id = 'field-' + field.name;
  const v = value ?? field.value ?? '';
  const req = field.required ? 'required' : '';
  const optional = !field.required && field.type !== 'checkbox' && !/optional/i.test(field.label) ? '<span class="optional"> (optional)</span>' : '';
  let content;
  if (field.type === 'checkbox') return `<div class="field"><label class="check-label" for="${id}"><input id="${id}" name="${field.name}" type="checkbox" ${v?'checked':''}>${esc(field.label)}</label>${field.help?`<small>${esc(field.help)}</small>`:''}</div>`;
  if (field.type === 'select') content = `<select id="${id}" name="${field.name}">${field.options.map(option=>`<option value="${esc(option)}" ${option===v?'selected':''}>${esc(label(option))}</option>`).join('')}</select>`;
  else if (field.type === 'textarea') content = `<textarea id="${id}" name="${field.name}" ${req} spellcheck="false">${esc(v)}</textarea>`;
  else if (['file','files','folder'].includes(field.type)) {
    const input = field.type==='files' ? `<textarea id="${id}" name="${field.name}" ${req} placeholder="One full path per line">${esc(v)}</textarea>` : `<input id="${id}" name="${field.name}" value="${esc(v)}" ${req} placeholder="${field.type==='folder'?'C:\\Users\\you\\Downloads':'Full file path, or upload'}">`;
    content = field.type==='folder' ? input + '<small>Paste a full path to a folder on this computer.</small>' : `<div class="file-input-row">${input}<button type="button" class="button upload-button" data-field="${field.name}">Upload ↑</button><input hidden class="upload-picker" type="file" data-field="${field.name}" ${field.type==='files'?'multiple':''}></div>`;
  } else content = `<input id="${id}" name="${field.name}" type="${field.type}" value="${esc(v)}" ${req} ${field.type==='number'?'step="any"':''} ${field.type==='password'?'autocomplete="off"':''}>`;
  return `<div class="field"><label for="${id}">${esc(field.label)}${optional}</label>${content}${field.help?`<small>${esc(field.help)}</small>`:''}</div>`;
}

function formPayload(form, spec) {
  const p = {action: spec.key};
  for (const field of spec.fields) {
    const input = form.elements.namedItem(field.name);
    if (field.type==='checkbox') p[field.name] = input.checked;
    else if (input.value !== '') p[field.name] = input.value;
  }
  return p;
}

function rememberForm(tool, spec, form) {
  const p = formPayload(form, spec);
  // Remember convenience fields only in this tab's memory; never persist passwords.
  state.forms[tool.id] = {...state.forms[tool.id], ...Object.fromEntries(Object.entries(p).filter(([k])=>spec.fields.find(f=>f.name===k)?.type!=='password'))};
}

function renderTool(tool, selectedAction) {
  setBreadcrumb(tool.name, tool.category);
  state.current = tool.id;
  const spec = tool.actions.find(a=>a.key===selectedAction) || tool.actions[0];
  state.action = spec.key;
  const cached = state.forms[tool.id] || {};
  main.innerHTML = `<div class="tool-heading"><span class="tool-icon">${esc(tool.icon)}</span>${head(tool.name, tool.description, tool.category)}<button class="favorite ${state.favorites.has(tool.id)?'on':''}" data-favorite="${tool.id}" aria-label="Favorite ${esc(tool.name)}">${state.favorites.has(tool.id)?'★':'☆'}</button></div><div class="tool-workspace"><section class="panel form-panel"><div class="action-tabs">${tool.actions.map(a=>`<button class="action-tab ${a.key===spec.key?'selected':''}" data-action="${a.key}">${esc(a.label)}</button>`).join('')}</div><form id="tool-form">${['external','destructive','sensitive'].includes(spec.effect)?`<div class="action-warning">${spec.effect==='external'?'This action sends a request to the configured external service.':spec.effect==='sensitive'?'Capture saves everything you copy, including any sensitive text, on this computer.':'This action removes the selected saved data.'}</div>`:''}${spec.fields.map(f=>renderField(f,cached[f.name])).join('')}<button class="button primary form-submit" id="run-button" type="submit">${esc(spec.label)} <span>↗</span></button></form>${spec.schedule?`<details class="schedule-details"><summary>◷ Run this on a schedule</summary><p>Uses the fields above. Runs while LocalDesk is open.</p><div class="field"><label for="schedule-name">Schedule name</label><input id="schedule-name" value="${esc(tool.name)}"></div><div class="field"><label for="schedule-interval">Repeat</label><select id="schedule-interval"><option value="15">Every 15 seconds</option><option value="60">Every minute</option><option value="900">Every 15 minutes</option><option value="3600" selected>Every hour</option><option value="86400">Every day</option><option value="0">Once</option></select></div><div class="field"><label for="schedule-delay">First run in seconds</label><input id="schedule-delay" type="number" value="60" min="1"></div><button class="button small" id="save-schedule" type="button">Save schedule</button></details>`:''}${tool.note?`<p class="tool-note">${esc(tool.note)}</p>`:''}</section><section class="panel results-panel" aria-live="polite"><div class="results-title">Your results <span id="result-status">READY WHEN YOU ARE</span></div><div id="results"><div class="result-empty"><div class="result-empty-icon">${esc(tool.icon)}</div><strong>A little less work, right here.</strong>Choose an action and enter the details to get started.</div></div></section></div>`;
  const form = $('#tool-form');
  $$('[data-action]').forEach(b=>b.addEventListener('click',()=>{ rememberForm(tool,spec,form); renderTool(tool,b.dataset.action); }));
  form.addEventListener('submit', async e => {
    e.preventDefault(); rememberForm(tool,spec,form);
    const payload = formPayload(form,spec);
    if (spec.effect==='destructive' && !confirm('Remove this saved data? This action cannot be undone.')) return;
    await runTool(tool,payload);
    $$('input[type=password]',form).forEach(input=>input.value='');
  });
  $$('.upload-button').forEach(b => b.addEventListener('click',()=> $(`.upload-picker[data-field="${b.dataset.field}"]`).click()));
  $$('.upload-picker').forEach(picker => picker.addEventListener('change', async()=> {
    const b = $(`.upload-button[data-field="${picker.dataset.field}"]`); b.disabled=true; b.textContent='Uploading…';
    try {
      const paths=[];
      for (const file of picker.files) {
        if(file.size>60000000) throw new Error('Upload limit is 60 MB per file.');
        const result = await request('/api/upload', undefined, {method:'POST', headers:{'X-LocalDesk-Token':state.token,'X-Filename':encodeURIComponent(file.name)},body:file});
        paths.push(result.path);
      }
      form.elements.namedItem(picker.dataset.field).value=paths.join('\n'); toast(`${paths.length} file${paths.length!==1?'s':''} uploaded locally.`);
    } catch(e) { toast(e.message); } finally {b.disabled=false;b.textContent='Upload ↑';}
  }));
  if(spec.schedule) $('#save-schedule').addEventListener('click',async()=> {
    if (!form.reportValidity()) return;
    const b=$('#save-schedule'); b.disabled=true;
    try { const result=await request('/api/jobs/create',{tool:tool.id,payload:formPayload(form,spec),name:$('#schedule-name').value,interval:$('#schedule-interval').value,delay:$('#schedule-delay').value});toast(result.message);await refreshOverview(); }
    catch(e){toast(e.message);}finally{b.disabled=false;}
  });
  bindFavorites();
  const auto = {clipboard:'search',timer:'status',habits:'list',expenses:'summary',dashboard:'overview',home:'list','file-history':'list'};
  if(auto[tool.id]===spec.key) runTool(tool,formPayload(form,spec));
}

async function runTool(tool, payload) {
  const runButton=$('#run-button'), output=$('#results'), status=$('#result-status');
  const renderId=state.renderId;
  if(runButton) runButton.disabled=true;
  output.replaceChildren(el('div','result-empty','Working on it…'));status.textContent='RUNNING';
  const start=performance.now();
  try {
    const result=await request('/api/run/'+tool.id,payload);
    if (renderId!==state.renderId || !output.isConnected || state.current!==tool.id || state.action!==payload.action) return;
    status.textContent=`COMPLETE · ${((performance.now()-start)/1000).toFixed(1)}s`;
    output.replaceChildren(); renderResult(result,output,tool);
    if(!output.childNodes.length)output.append(el('div','empty-state','Done.'));
    await refreshOverview();
  } catch(e) { if(output.isConnected) {status.textContent='NEEDS ATTENTION';output.replaceChildren(el('div','error-box',e.message));} }
  finally {if(runButton?.isConnected)runButton.disabled=false;}
}

function renderResult(data, target, tool) {
  if(data.message)target.append(el('div','result-message',data.message));
  if(data.password){target.append(el('div','password-value',data.password));target.append(button('Copy password',()=>copyText(data.password)));}
  if(data.active && data.active.start) {
    const timer=el('div','focus-clock');target.append(timer);
    const update=()=> {const left=Math.max(0,Math.ceil(data.active.start+data.active.minutes*60-Date.now()/1000));timer.textContent=`${Math.floor(left/60).toString().padStart(2,'0')}:${(left%60).toString().padStart(2,'0')} · ${data.active.task}`;};
    update();clearInterval(clockInterval);clockInterval=setInterval(update,1000);
  }
  const metrics=Object.entries(data).filter(([k,v])=>typeof v==='number' && !k.startsWith('_') && !['server_time'].includes(k));
  if(metrics.length){const row=el('div','result-metrics');metrics.forEach(([k,v])=>{const chip=el('div','metric-chip');chip.append(el('small','',label(k)),el('strong','',Number.isInteger(v)?v.toLocaleString():v.toLocaleString(undefined,{maximumFractionDigits:3})));row.append(chip);});target.append(row);}
  if(data.chart?.length)renderBars(data.chart,target);
  if(data.series?.length)renderLine(data.series,target);
  for(const [key,value] of Object.entries(data)){
    if(['message','password','chart','series','plan_id','email_plan_id','server_time','note','privacy','active'].includes(key) || typeof value==='number' || key.startsWith('_'))continue;
    renderValue(key,value,target,tool);
  }
  if(data.note)target.append(el('div','result-note',data.note));
  if(data.privacy)target.append(el('div','result-note',data.privacy));
  if(data.plan_id && data.changes?.length) confirmation(target,`${data.changes.length} changes are ready. Review every source and destination above. A journal will let you preview an undo.`, 'Apply file changes', '/api/files/apply',data.plan_id,tool);
  if(data.email_plan_id && data.messages?.length)confirmation(target,'Review the matched messages and destination folders. Applying will copy messages and mark originals Deleted in the source mailbox.','Apply email rules','/api/email/apply',data.email_plan_id,tool);
}

function confirmation(target, text, title, endpoint, id, tool) {
  const box=el('div','plan-confirm');box.append(el('p','',text));
  const b=button(title,async()=>{b.disabled=true;try{const result=await request(endpoint,{plan_id:id});target.replaceChildren();renderResult(result,target,tool);toast('Changes applied.');}catch(e){box.append(el('div','error-box',e.message));b.disabled=false;}},'button primary');
  box.append(b);target.append(box);
}

function renderValue(key,value,target,tool) {
  if(value==null || value==='' || ['_created'].includes(key)) return;
  if(value && typeof value==='object' && value.url && value.name && value.url.startsWith('/download/')) {
    const link=el('a','download-link');link.href=value.url;link.download=value.name;link.append(el('span','',value.name),el('span','','Download ↓'));target.append(link);return;
  }
  const section=el('section','result-section');section.append(el('h3','',label(key)));
  if(Array.isArray(value)) {
    if(!value.length)section.append(el('div','inline-empty','Nothing here yet.'));
    else if(value.every(v=>typeof v==='object'&&v!==null&&!Array.isArray(v)))renderTable(value,section,tool,key);
    else {const text=el('div','result-text',value.map(v=>typeof v==='object'?JSON.stringify(v):v).join('\n'));section.append(text);}
  } else if(typeof value==='object') {
    for(const [k,v]of Object.entries(value))renderValue(k,v,section,tool);
  } else {
    const mono=['text','body','html_source','ascii','map','diff','response','payload','headers'].includes(key);
    const text=el(mono?'pre':'div',mono?'result-text mono':'result-text',typeof value==='boolean'?(value?'Yes':'No'):String(value));
    section.append(text);
    if(mono && String(value).length>20)section.append(button('Copy text',()=>copyText(String(value))));
  }
  target.append(section);
}

function renderTable(rows,target,tool,key) {
  const columns=[...new Set(rows.flatMap(r=>Object.keys(r)))].filter(k=>!k.startsWith('_')&&k!=='vector');
  const wrap=el('div','table-wrap'),table=el('table'),thead=el('thead'),tr=el('tr');
  columns.forEach(c=>tr.append(el('th','',label(c))));thead.append(tr);table.append(thead);
  const tbody=el('tbody');
  rows.slice(0,200).forEach(row=>{
    const tr=el('tr');
    columns.forEach(c=>{
      const td=el('td');let v=row[c];
      if(v==null)v='—';
      if(c==='id' || c==='journal_id' || c==='device_id') {
        const b=button(String(v),()=>{copyText(String(v));const input=$('#tool-form')?.elements.namedItem(tool?.id==='home'?'device_id':tool?.id==='file-history'?'journal_id':'id');if(input)input.value=v;},'copy-id');b.title='Copy ID and fill matching field';td.append(b);
      } else if(typeof v==='object')td.append(el('pre','',JSON.stringify(v,null,2)));
      else td.textContent=typeof v==='boolean'?(v?'Yes':'No'):String(v);
      if(c===columns[0] && tool?.id==='api' && key==='requests')td.append(button('Load',()=>{state.forms.api={...row};renderTool(tool,'send');toast('Request loaded. Review it before sending.');}));
      tr.append(td);
    });tbody.append(tr);
  });table.append(tbody);wrap.append(table);target.append(wrap);
  if(rows.length>200)target.append(el('div','result-note',`Showing the first 200 of ${rows.length} rows. Download the export for all rows.`));
}

function renderBars(rows,target) {
  const chart=el('div','bar-chart');const max=Math.max(...rows.map(r=>Math.abs(Number(r.value)||0)),1);
  rows.slice(0,24).forEach(r=>{const row=el('div','bar-row'),track=el('div','bar-track'),fill=el('div','bar-fill');fill.style.width=`${Math.abs(Number(r.value)||0)/max*100}%`;track.append(fill);row.append(el('span','bar-label',r.label),track,el('span','bar-value',Number(r.value).toLocaleString(undefined,{maximumFractionDigits:2})));chart.append(row);});target.append(chart);
}

function renderLine(rows,target) {
  const ns='http://www.w3.org/2000/svg';const svg=document.createElementNS(ns,'svg');svg.classList.add('line-chart');svg.setAttribute('viewBox','0 0 600 250');svg.setAttribute('role','img');svg.setAttribute('aria-label','Strategy equity compared with buy and hold over time');
  const values=rows.flatMap(r=>[r.equity,r.buy_hold]);const min=Math.min(...values)*.97,max=Math.max(...values)*1.03;
  for(const [key,color]of [['buy_hold','#c9b58e'],['equity','#71985b']]){const poly=document.createElementNS(ns,'polyline');poly.setAttribute('points',rows.map((r,i)=>`${40+i/Math.max(1,rows.length-1)*540},${210-(r[key]-min)/Math.max(max-min,1)*175}`).join(' '));poly.setAttribute('fill','none');poly.setAttribute('stroke',color);poly.setAttribute('stroke-width','2');svg.append(poly);}
  for(const [x,y,text]of [[15,20,`Equity ${min.toFixed(0)}–${max.toFixed(0)}`],[40,235,rows[0].date],[490,235,rows.at(-1).date],[300,20,'Green: strategy · sand: buy & hold']]){const t=document.createElementNS(ns,'text');t.setAttribute('x',x);t.setAttribute('y',y);t.textContent=text;svg.append(t);}target.append(svg);
}

async function copyText(text){try{await navigator.clipboard.writeText(text);toast('Copied to clipboard.');}catch{toast('Clipboard permission was blocked. Select the text to copy it.');}}

function renderJobs(){
  setBreadcrumb('Schedules');main.innerHTML=head('Give busywork a routine.', 'Recurring tasks run while LocalDesk is open. Missed runs are skipped after a restart.', 'AUTOMATION')+'<div id="job-list"></div>';
  const container=$('#job-list'),jobs=state.overview.jobs||[];
  if(!jobs.length){container.innerHTML='<section class="panel empty-state"><strong>Your time, back on the calendar.</strong>Open Website monitor, RSS, Scraper, Bot studio, or Home hub and use “Run this on a schedule”.</section>';return;}
  jobs.forEach(job=>{
    const card=el('section','panel job-card');card.innerHTML=`<div class="job-card-head"><div><h3>${esc(job.name)}</h3><p>${esc(toolById(job.tool)?.name||job.tool)} · ${job.interval?`every ${job.interval} seconds`:'once'}</p><p>Next: ${esc(job.enabled?dateText(job.next_run):'Paused or completed')} · Last: ${esc(dateText(job.last_run))}</p></div><span class="status-badge ${job.status==='Failed'?'fail':''}">${esc(job.status)}</span></div>`;
    if(job.result)renderValue('last_result',job.result,card,toolById(job.tool));
    const row=el('div','button-row');
    [['run','Run soon'],[job.enabled?'pause':'resume',job.enabled?'Pause':'Resume'],['delete','Delete']].forEach(([action,title])=>row.append(button(title,async()=>{if(action==='delete'&&!confirm('Delete this schedule?'))return;try{await request('/api/jobs/action',{id:job.id,action});await refreshOverview();renderJobs();}catch(e){toast(e.message);}})));
    const details=el('details','result-details');details.append(el('summary','','Saved inputs'));renderValue('payload',job.payload,details,toolById(job.tool));card.append(row,details);container.append(card);
  });
}

function renderSettings(){
  setBreadcrumb('Settings & setup');const s=state.status;
  main.innerHTML=head('Make yourself at home.', 'Local by default. Connect only the services you want to use.', 'SETTINGS & SETUP')+
    `<div class="settings-grid"><section class="panel settings-panel"><h2>Your workspace</h2><p>Python <code>${esc(s.python)}</code></p><p>Database, uploads, generated files, and recoverable trash live in:</p><pre>${esc(s.data_folder)}</pre><p>Back up this folder with LocalDesk stopped. It may contain private snippets, requests, and document text. Keep the server bound to loopback; it has no multi-user login.</p><button class="button small" id="browser-notifications">Enable browser notifications</button><p id="notification-permission"></p><h2>How file changes work</h2><p>Create a preview, review destinations, then apply. A SHA-256 check rejects stale plans. Use File history to preview an undo. Duplicate cleanup moves files into recoverable trash.</p><a class="button small" href="#file-history">Open file history ↗</a></section><section class="panel settings-panel"><h2>Python features</h2><p>The server and core tools use the standard library. Install optional libraries from the app folder:</p><pre>python -m pip install -r requirements.txt</pre><div id="dependencies"></div></section><section class="panel settings-panel"><h2>Service connections</h2><p>Copy <code>.env.example</code> to <code>.env</code> in the app folder, fill in the services you need, then restart LocalDesk. Secrets are read on the server and never returned by this page.</p><div id="integrations"></div><p>“Configured” checks variable presence; running a tool tests the actual service connection.</p></section><section class="panel settings-panel"><h2>Local AI & OCR</h2><p>Install Ollama, pull a chat and embedding model, and start the service:</p><pre>ollama pull llama3.2\nollama pull embeddinggemma\nollama serve</pre><p>Ollama endpoint: <code>${esc(s.ollama_url)}</code></p><p>Set <code>OLLAMA_CHAT_MODEL</code> and <code>OLLAMA_EMBED_MODEL</code> to match your installed models. Index notes in Knowledge search before chatting.</p><p>Receipt OCR also needs Tesseract installed with language data. Executable:</p><pre>${esc(s.ocr_executable)}</pre><p>Set <code>TESSERACT_CMD</code> if it is not on PATH. Scanned PDFs need OCR before knowledge indexing.</p></section><section class="panel settings-panel"><h2>Schedules & reminders</h2><p>Schedules run only while the Python app is running. The browser can be closed. Interrupted external jobs are paused on restart so a message or device command is not blindly repeated.</p><p>For a Telegram command bot, schedule “Poll Telegram commands” every 15 seconds. Commands: <code>/remind MINUTES text</code>, <code>/poll</code>, <code>/quiz</code>. Only your configured chat ID is accepted.</p></section><section class="panel settings-panel"><h2>About this toolbox</h2><p>LocalDesk brings 32 tools together in one local website. It does not need a cloud account. Weather, RSS, scraping, breach checking, and configured integrations make network requests when you run them.</p><p>See the included README for setup, feature coverage, formats, and limitations.</p><button class="button small" id="refresh-status">Refresh feature status</button></section></div>`;
  const deps=$('#dependencies');s.packages.forEach(p=>{const row=el('div','dependency-row');row.append(el('span','',p.feature),el('span',p.installed?'ok':'missing',p.installed?'Installed ✓':'Optional · install needed'));deps.append(row);});
  const integrations=$('#integrations');s.integrations.forEach(i=>{const row=el('div','dependency-row');const left=el('div','',i.name);left.append(el('small','',i.variables.join(', ')));row.append(left,el('span',i.configured?'ok':'missing',i.configured?'Configured ✓':'Not configured'));integrations.append(row);});
  $('#notification-permission').textContent='Browser permission: '+('Notification'in window?Notification.permission:'not supported');
  $('#browser-notifications').addEventListener('click',async()=>{if(!('Notification'in window))return toast('Browser notifications are unavailable.');const permission=await Notification.requestPermission();$('#notification-permission').textContent='Browser permission: '+permission;});
  $('#refresh-status').addEventListener('click',async()=>{state.status=await request('/api/status');renderSettings();toast('Feature status refreshed.');});
}

function renderNotifications(){
  setBreadcrumb('Notifications');main.innerHTML=head('A small heads-up.', 'Website changes, completed focus sessions, and schedule errors.', 'NOTIFICATIONS')+'<div class="button-row"><button class="button small" id="mark-read">Mark all read</button></div><div id="notification-list"></div>';
  const container=$('#notification-list');container.className='result-section';const rows=state.overview.notifications||[];
  if(!rows.length)container.innerHTML='<div class="panel empty-state"><strong>All quiet at your desk.</strong>There are no notifications yet.</div>';
  rows.forEach(r=>{const card=el('section','panel notification-card'+(!r.read?' unread':''));card.append(el('h3','',r.title),el('p','',r.message),el('small','',dateText(r._created)));container.append(card);});
  $('#mark-read').addEventListener('click',async()=>{await request('/api/notifications/read',{});await refreshOverview();renderNotifications();});
}

async function refreshOverview(initial=false){
  state.overview=await request('/api/overview');
  const notes=state.overview.notifications||[];const unread=notes.filter(n=>!n.read).length;
  $('#notification-count').textContent=unread;$('#notification-count').hidden=!unread;
  for(const note of notes){if(!initial&&!state.seenNotifications.has(note.id)&&!note.read){toast(note.title);if('Notification'in window&&Notification.permission==='granted')new Notification(note.title,{body:note.message.slice(0,200)});}state.seenNotifications.add(note.id);}
}

async function render(){
  const raw=location.hash.slice(1)||'overview';const [page,search]=raw.split('?');const params=new URLSearchParams(search||'');
  state.renderId++;state.current='';clearInterval(clockInterval);nav();
  if(page==='overview')renderOverview();
  else if(page==='tools'||page==='favorites')renderGallery(page==='favorites',params.get('category'));
  else if(page==='jobs')renderJobs();
  else if(page==='settings')renderSettings();
  else if(page==='notifications')renderNotifications();
  else if(toolById(page))renderTool(toolById(page));
  else {location.hash='overview';}
  window.scrollTo(0,0);
}

function searchTools(){
  const q=$('#global-search').value.toLowerCase();const matches=state.tools.filter(t=>`${t.name} ${t.description} ${t.category}`.toLowerCase().includes(q)).slice(0,12);
  $('#search-results').innerHTML=matches.map(t=>`<a class="search-result" href="#${t.id}"><span class="tool-icon">${esc(t.icon)}</span><div><strong>${esc(t.name)}</strong><small>${esc(t.category)}</small></div><span>↗</span></a>`).join('')||'<div class="empty-state">No tools found.</div>';
  $$('.search-result').forEach(a=>a.addEventListener('click',()=>$('#search-dialog').close()));
}
function openSearch(){$('#search-dialog').showModal();$('#global-search').value='';searchTools();$('#global-search').focus();}
$('#search-launch').addEventListener('click',openSearch);$('#close-search').addEventListener('click',()=>$('#search-dialog').close());$('#global-search').addEventListener('input',searchTools);
document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();if($('#search-dialog').open)$('#search-dialog').close();else openSearch();}});
$('#menu-toggle').addEventListener('click',()=>$('#sidebar').classList.toggle('open'));
window.addEventListener('hashchange',render);

(async()=>{
  try {
    const data=await request('/api/bootstrap');state.tools=data.tools;state.token=data.token;state.status=data.status;
    $('#tool-count').textContent=state.tools.filter(t=>t.category!=='System').length;
    await refreshOverview(true);render();
    setInterval(async()=>{try{await refreshOverview();if(location.hash==='#jobs')renderJobs();}catch{}},10000);
  } catch(e){main.replaceChildren(el('div','error-box','Could not open LocalDesk. '+e.message));}
})();
