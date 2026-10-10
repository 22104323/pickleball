'use strict';

const $ = (selector, parent = document) => parent.querySelector(selector);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const e = escapeHtml;
let state = null;
let sessions = [];
let view = 'queue';
let busy = false;
let loadSequence = 0;
let confirmAction = null;
let resultGame = null;
let searchTerm = '';
const views = ['queue','attendance','results','activity'];

async function api(path, data) {
  const response = await fetch(path, data === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const payload = await response.json();
  if (!response.ok) {
    const error = new Error(payload.error || 'Request failed.');
    error.status = response.status;
    throw error;
  }
  return payload;
}

function message(text, isError = false) {
  const node = $(isError ? '#error' : '#notice');
  node.textContent = text;
  node.hidden = !text;
  if (!isError) $('#error').hidden = true;
}

function initials(name) { const parts=name.replace(/\(demo\)/g,'').trim().split(/\s+/);return (parts.length===1?parts[0].slice(0,2):parts.slice(0,2).map(n=>n[0]).join('')).toUpperCase(); }
function avatar(name) { return `<span class="avatar" aria-hidden="true">${e(initials(name))}</span>`; }
function button(label, attrs, kind='btn-outline') { return `<button class="btn btn-small ${kind}" ${attrs} ${busy?'disabled':''}>${label}</button>`; }
function playerButton(player, action, label, kind='btn-outline') { return button(label,`data-player="${player.id}" data-player-action="${action}"`,kind); }
function empty(title, description, action='') { return `<div class="empty-state"><h3>${e(title)}</h3><p>${e(description)}</p>${action}</div>`; }
function closed() { return state?.session.status === 'closed'; }

function syncNavigation() {
  const params = new URLSearchParams(location.hash.slice(1));
  view = views.includes(params.get('view')) ? params.get('view') : 'queue';
  return Number(params.get('session')) || sessions[0]?.id || null;
}

async function load(animate = false) {
  const sequence = ++loadSequence;
  try {
    const listed = await api('/api/sessions');
    if (sequence !== loadSequence) return;
    sessions = listed.sessions;
    const id = syncNavigation();
    const next = id ? await api(`/api/sessions/${id}`) : null;
    if (sequence !== loadSequence) return;
    state = next;
    render(animate);
  } catch (error) { if(sequence===loadSequence) message(error.message,true); }
}

function navigate(id, nextView = view, replace = false) {
  const hash = id ? `#session=${id}&view=${nextView}` : `#view=${nextView}`;
  if (hash !== location.hash) history[replace?'replaceState':'pushState'](null,'',hash);
  view = nextView;
  searchTerm = '';
  load(true);
}

function render(animate = false) {
  const selection = $('#session-select');
  selection.innerHTML = (sessions.length ? sessions.map(s => `<option value="${s.id}" ${s.id===state?.session.id?'selected':''}>${e(s.name)}${s.status==='closed'?' · closed':''}</option>`).join('') : '<option value="">No sessions yet</option>') + '<option value="new">+ New session</option>';
  document.querySelectorAll('[data-view]').forEach(node => {
    node.classList.toggle('active',node.dataset.view===view);
    if(node.dataset.view===view) node.setAttribute('aria-current','page'); else node.removeAttribute('aria-current');
  });
  $('#import-button').disabled = busy || !state || closed();
  $('#fill-button').disabled = busy || !state || closed() || view !== 'queue';
  $('#fill-button').hidden = view !== 'queue';
  if (!state) {
    $('#summary').hidden = true;
    $('#view-content').innerHTML = `<div class="welcome"><div><h2>A fair rotation starts with who’s here.</h2><p>Bring your roster, check players in, and build balanced doubles games. Everyone’s wait matters. Strong players don’t get to stack.</p><button class="btn" data-open="create-dialog">Create your first session <span aria-hidden="true">↗</span></button><span class="welcome-note">Local workspace · no sign-in or installation needed</span></div><div class="welcome-court" aria-hidden="true"></div></div><div class="helper-strip"><strong>Just trying it out?</strong><span>Create a session, then load 30 synthetic demo players.</span></div>`;
    return;
  }
  const {session:s,metrics:m} = state;
  $('#breadcrumb').textContent = s.name;
  $('#session-title').textContent = s.name;
  $('#session-date').textContent = new Date(s.starts_at*1000).toLocaleDateString(undefined,{weekday:'long',month:'long',day:'numeric'}).toUpperCase();
  $('#session-subtitle').textContent = `${s.court_count} court${s.court_count===1?'':'s'} · ${s.max_players} player capacity · ${closed()?'Session closed. Ratings finalized.':'Balanced rotation. One queue, fair court time.'}`;
  $('#nav-count').textContent = m.waiting;
  $('#summary').hidden = false;
  const activeCourts = state.games.filter(g => ['assigned','playing'].includes(g.status)).length;
  const metrics = [ ['Checked in',m.present,`of ${state.players.length} on the roster`],['In the queue',m.waiting,'Ordered by time waiting'],['Courts occupied',activeCourts,`of ${s.court_count} available`],['Games completed',m.completed_games,closed()?'Ratings updated':'Ratings finalize at session close'] ];
  $('#summary').innerHTML = metrics.map(([label,value,note])=>`<div class="metric"><div class="metric-label">${e(label)}</div><div class="metric-value">${value}</div><div class="metric-note">${e(note)}</div></div>`).join('');
  $('#view-content').innerHTML = view === 'queue' ? queueView() : view === 'attendance' ? attendanceView() : view === 'results' ? resultsView() : activityView();
  $('#view-content').classList.toggle('view-enter',animate);
  $('#updated-label').textContent = `Saved locally · revision ${s.revision}`;
  filterRows();
}

function courtCard(court) {
  const game = state.games.find(g => g.court===court && ['assigned','playing'].includes(g.status));
  if (!game) return `<article class="court-card"><div class="court-top"><h3>Court ${court}</h3><span class="chip">${closed()?'Session closed':'Ready for players'}</span></div><div class="court-empty"><div class="court-lines" aria-hidden="true"></div><strong>${closed()?'See you next session':'The next four are up to you.'}</strong><p>${closed()?'Game results are saved below.':'Fill open courts to find a balanced game from the queue.'}</p></div></article>`;
  const teams = ['a','b'].map(side=>`<div class="team"><span class="team-label">Team ${side.toUpperCase()}</span>${game.players.filter(p=>p.side===side).map(p=>`<div class="court-player">${avatar(p.name)}<div><strong>${e(p.name)}</strong><small>${Math.round(p.rating)} · ${p.rating<1100?'Beginner':p.rating<1450?'Intermediate':p.rating<1750?'Advanced':'Competitive'}</small></div></div>`).join('')}</div>`);
  return `<article class="court-card"><div class="court-top"><h3>Court ${court}</h3><span class="chip active">${game.status==='playing'?'On court':'Assigned'}</span></div><div class="matchup">${teams[0]}<span class="versus">vs</span>${teams[1]}</div><div class="court-balance"><span class="balance-good">Balanced matchup</span><span>Team A estimate ${Math.round(game.expected_a*100)}% · gap ${Math.round(Math.abs(game.mean_a-game.mean_b))}</span></div><div class="court-actions">${game.status==='assigned'?button('Start game',`data-game="${game.id}" data-game-action="start"`,'btn-primary'):button('Record result',`data-result="${game.id}"`,'btn-primary')}${button('Cancel',`data-cancel="${game.id}"`)}</div></article>`;
}

function tableToolbar(title, note, search=true) { return `<div class="panel-toolbar"><div><h2>${e(title)}</h2><p class="toolbar-copy">${e(note)}</p></div>${search?`<div class="search-wrap"><label for="player-search" class="sr-only">Search players</label><input id="player-search" placeholder="Search players…" value="${e(searchTerm)}" type="search"></div>`:''}</div>`; }

function queueView() {
  const queued = state.players.filter(p=>p.queue_state==='waiting');
  return `<div class="section-title"><div><h2>Your courts</h2><p>Close teams. Fresh partners. No automatic game starts.</p></div><span class="live-label">${closed()?'Session archived':'Session active'}</span></div><div class="courts">${Array.from({length:state.session.court_count},(_,i)=>courtCard(i+1)).join('')}</div><section class="panel">${tableToolbar('Up next',`${queued.length} waiting · longest-waiting player is protected`)}${queued.length?`<div class="table-wrap"><table class="queue-table"><thead><tr><th>Queue</th><th>Player</th><th>Skill band</th><th>Games</th><th>Wait</th><th>Action</th></tr></thead><tbody>${queued.map(p=>`<tr data-name="${e(p.name.toLowerCase())}"><td class="position ${p.position<=4?'first':''}">${String(p.position).padStart(2,'0')}</td><td><div class="player-cell">${avatar(p.name)}<div><strong>${e(p.name)}</strong><small>${p.provisional?'Provisional rating':`${Math.round(p.rating)} rating`}${p.is_late?' · arrived late':''}</small></div></div></td><td><span class="chip">${e(p.band)}</span></td><td class="number">${p.games_played}</td><td><span class="waiting-badge">${Math.floor(p.wait_minutes)} min</span></td><td>${playerButton(p,'pause','Take a break')}</td></tr>`).join('')}</tbody></table></div>`:empty(closed()?'Session complete':'No one is waiting yet',closed()?'Your attendance and completed games are stored in this session.':'Go to Attendance to check in players. Only present, eligible players enter the queue.',closed()?'':button('Check in players','data-view="attendance"','btn-primary'))}</section>${!state.players.length&&!closed()?`<div class="helper-strip"><strong>Start with your roster</strong><span>Import a CSV or try the workflow with demo players.</span>${button('Load demo roster','data-action="demo"')}</div>`:''}<div class="session-tools">${!closed()?button('Close session & finalize ratings','data-confirm="close"'):''}</div>`;
}

function attendanceView() {
  const players = state.players;
  return `<section class="panel">${tableToolbar('Session attendance','RSVP is a plan. Check-in is presence. Eligibility gates play.')}${players.length?`<div class="table-wrap"><table class="attendance-table"><thead><tr><th>Player</th><th>RSVP</th><th>Attendance</th><th>Eligibility</th><th>Rotation</th><th>Action</th></tr></thead><tbody>${players.map(p=>`<tr data-name="${e(p.name.toLowerCase())}"><td><div class="player-cell">${avatar(p.name)}<div><strong>${e(p.name)}</strong><small>${e(p.external_id)} · ${e(p.source)}</small></div></div></td><td>${e(p.rsvp)}</td><td><span class="chip ${p.attendance==='present'?'active':p.attendance==='no_show'?'warn':''}">${e(p.attendance.replace('_',' '))}${p.is_late?' · late':''}</span></td><td>${closed()?e(`${p.membership} / ${p.waiver}`):`<div class="inline-eligibility" data-eligibility="${p.id}"><select aria-label="Membership for ${e(p.name)}" data-membership ${['assigned','playing'].includes(p.queue_state)?'disabled':''}>${['active','expired','unknown'].map(x=>`<option ${p.membership===x?'selected':''}>${x}</option>`).join('')}</select><select aria-label="Waiver for ${e(p.name)}" data-waiver ${['assigned','playing'].includes(p.queue_state)?'disabled':''}>${['valid','missing','unknown'].map(x=>`<option ${p.waiver===x?'selected':''}>${x}</option>`).join('')}</select><button class="btn btn-small btn-outline" data-save-eligibility="${p.id}" aria-label="Save eligibility for ${e(p.name)}" ${['assigned','playing'].includes(p.queue_state)?'disabled':''}>Save</button></div>`}</td><td>${p.eligible?e(p.queue_state==='off'?'Not queued':p.queue_state):'<span class="chip blocked">Not eligible</span>'}</td><td><div class="row-actions">${closed()?'—':p.attendance!=='present'?playerButton(p,'checkin','Check in','btn-primary'):['assigned','playing'].includes(p.queue_state)?'On court':`${p.queue_state==='waiting'?playerButton(p,'pause','Pause'):p.eligible?playerButton(p,'resume','Rejoin','btn-primary'):''}${playerButton(p,'checkout','Check out')}`}</div></td></tr>`).join('')}</tbody></table></div>`:empty('Your roster starts here','Import an organizer-prepared CSV, or load synthetic demo players to explore check-in and court rotation.',`${button('Import roster','data-open="import-dialog"','btn-primary')} ${button('Load demo roster','data-action="demo"')}`)}</section>${!closed()?`<div class="session-tools">${button('Reconcile absent RSVPs','data-confirm="reconcile"')}${button('Close session & finalize ratings','data-confirm="close"')}</div>`:''}<div class="helper-strip"><span>Late arrivals join the back. Taking a break or leaving removes you from the queue; assigned games must be resolved first.</span></div>`;
}

function resultsView() {
  const games = state.games.filter(g=>['completed','cancelled'].includes(g.status));
  return `<section class="panel">${tableToolbar('Game results',`${state.metrics.completed_games} completed · cancelled games do not affect ratings`,false)}${games.length?`<div class="table-wrap"><table class="result-table"><thead><tr><th>Game</th><th>Team A</th><th>Score</th><th>Team B</th><th>Result</th></tr></thead><tbody>${games.map(g=>`<tr><td><strong>#${g.id}</strong><br><small class="muted">Court ${g.court}</small></td><td>${g.players.filter(p=>p.side==='a').map(p=>e(p.name)).join('<br>')}</td><td class="number">${g.status==='completed'?`${g.score_a} : ${g.score_b}`:'—'}</td><td>${g.players.filter(p=>p.side==='b').map(p=>e(p.name)).join('<br>')}</td><td><span class="chip ${g.status==='completed'?'active':''}">${g.status==='completed'?`Team ${g.score_a>g.score_b?'A':'B'} won`:'Cancelled'}</span></td></tr>`).join('')}</tbody></table></div>`:empty('The first result is still ahead','Start an assigned game, then record the score when it finishes.') }<div class="rating-note">${closed()?'Ratings were finalized as one session period.':'Ratings stay fixed during this session and update when you close it.'} Individual doubles ratings use an experimental Glicko-2 adaptation. Displayed win estimates are pairing heuristics.</div></section>`;
}

function activityView() {
  const labels = {'session.created':'Session created','roster.imported':'Roster imported','player.checkin':'Player checked in','player.checkout':'Player checked out','player.pause':'Player took a break','player.resume':'Player rejoined the queue','player.eligibility':'Eligibility updated','courts.assigned':'Courts assigned','game.start':'Game started','game.complete':'Game result recorded','game.cancelled':'Game cancelled','attendance.reconciled':'Absentees reconciled','session.closed':'Session closed; ratings finalized'};
  return `<section class="panel">${tableToolbar('Session activity','Changes are recorded locally. Recent 30 actions shown.',false)}<ul class="activity-list">${state.audit.map(a=>`<li><span>${e(labels[a.action]||a.action)}</span><time datetime="${new Date(a.created_at*1000).toISOString()}">${new Date(a.created_at*1000).toLocaleTimeString(undefined,{hour:'2-digit',minute:'2-digit'})}</time></li>`).join('')}</ul></section><div class="helper-strip"><span>This MVP records local organizer actions. Reclub synchronization and external write-back are not connected.</span></div>`;
}

function filterRows() {
  document.querySelectorAll('tr[data-name]').forEach(row=>row.hidden=!row.dataset.name.includes(searchTerm.toLowerCase()));
}

async function mutate(action, data={}, dialog=null) {
  if (busy || !state) return false;
  const id = state.session.id;
  const focused = document.activeElement;
  const focusPlayer = focused?.dataset.player;
  const focusAction = focused?.dataset.playerAction;
  busy = true;
  document.querySelectorAll('button').forEach(b=>{b.dataset.wasDisabled=String(b.disabled);b.disabled=true;});
  if(dialog) $('.form-error',dialog).textContent='';
  try {
    state = await api(`/api/sessions/${id}/${action}`, {revision:state.session.revision,...data});
    ++loadSequence;
    busy = false;
    if(dialog) dialog.close();
    sessions = (await api('/api/sessions')).sessions;
    render();
    document.querySelectorAll('button[data-was-disabled]').forEach(b=>{b.disabled=b.dataset.wasDisabled==='true';delete b.dataset.wasDisabled;});
    $('#import-button').disabled = closed();
    $('#fill-button').disabled = closed();
    if(state.notice) message(state.notice);
    if(focusPlayer) {
      const restore = $(`[data-player="${focusPlayer}"][data-player-action="${focusAction}"]`) || $(`tr:has([data-save-eligibility="${focusPlayer}"]) button[data-player]`);
      (restore || $('#workspace')).focus({preventScroll:true});
    }
    return true;
  } catch (error) {
    if(dialog) $('.form-error',dialog).textContent=error.message; else message(error.message,true);
    if(error.status===409) { busy=false; await load(); }
    return false;
  } finally {
    busy=false;
    document.querySelectorAll('button[data-was-disabled]').forEach(b=>{b.disabled=b.dataset.wasDisabled==='true';delete b.dataset.wasDisabled;});
  }
}

function openDialog(id) {
  const dialog = $(`#${id}`);
  $('.form-error',dialog).textContent='';
  if(id==='create-dialog') {
    const now = new Date();
    now.setMinutes(now.getMinutes()-now.getTimezoneOffset());
    $('#session-start').value=now.toISOString().slice(0,16);
  }
  dialog.showModal();
}

document.addEventListener('click', event=>{
  const target = event.target.closest('button');
  if(!target || busy || target.disabled) return;
  if(target.classList.contains('close-dialog')) return target.closest('dialog').close();
  if(target.dataset.view) return navigate(state?.session.id,target.dataset.view);
  if(target.dataset.open) return openDialog(target.dataset.open);
  if(target.dataset.action) return mutate(target.dataset.action);
  if(target.dataset.player) return mutate('player',{id_roster:Number(target.dataset.player),action:target.dataset.playerAction});
  if(target.dataset.saveEligibility) {
    const fields=target.closest('[data-eligibility]');
    return mutate('player',{id_roster:Number(target.dataset.saveEligibility),action:'eligibility',membership:$('[data-membership]',fields).value,waiver:$('[data-waiver]',fields).value});
  }
  if(target.dataset.game) return mutate('game',{id_game:Number(target.dataset.game),action:target.dataset.gameAction});
  if(target.dataset.result) {
    resultGame=Number(target.dataset.result);
    const game=state.games.find(g=>g.id===resultGame);
    $('#result-form').reset();
    $('#result-teams').innerHTML=`<div class="result-team-summary"><strong>Team A</strong>: ${game.players.filter(p=>p.side==='a').map(p=>e(p.name)).join(' + ')}<br><strong>Team B</strong>: ${game.players.filter(p=>p.side==='b').map(p=>e(p.name)).join(' + ')}</div>`;
    return openDialog('result-dialog');
  }
  if(target.dataset.cancel || target.dataset.confirm) {
    const isCancel=Boolean(target.dataset.cancel);
    confirmAction=isCancel?{action:'game',data:{id_game:Number(target.dataset.cancel),action:'cancel'}}:{action:target.dataset.confirm,data:{}};
    $('#cancel-reason-field').hidden=!isCancel;
    $('#cancel-reason').required=isCancel;
    $('#cancel-reason').value='';
    $('#confirm-title').textContent=isCancel?'Cancel this game?':confirmAction.action==='close'?'Close this session?':'Mark absent RSVPs as no-shows?';
    $('#confirm-description').textContent=isCancel?'This result will not be rated. All four players return to the queue with their original waiting priority.':confirmAction.action==='close'?'Finish or cancel active courts first. Closing ends the queue and applies ratings once from completed games. This session cannot be reopened in the MVP.':'Available 30 minutes after the start. Only RSVP-yes players who never checked in are marked. No penalty or notification is sent.';
    $('#confirm-submit').textContent=isCancel?'Cancel game':confirmAction.action==='close'?'Close & finalize':'Reconcile attendance';
    return openDialog('confirm-dialog');
  }
});

$('#session-select').addEventListener('change',event=>{
  if(event.target.value==='new'){event.target.value=state?.session.id||'';openDialog('create-dialog');}
  else navigate(Number(event.target.value));
});
document.addEventListener('input',event=>{if(event.target.id==='player-search'){searchTerm=event.target.value;filterRows();}});
$('#csv-file').addEventListener('change',async event=>{
  const file=event.target.files[0];
  if(!file)return;
  if(file.size>200000){$('.form-error',$('#import-dialog')).textContent='CSV must be under 200 KB.';return;}
  try{$('#csv-content').value=await file.text();}catch{$('.form-error',$('#import-dialog')).textContent='File could not be read.';}
});
$('#create-form').addEventListener('submit',async event=>{
  event.preventDefault();
  if(busy)return;
  const form=new FormData(event.target);
  const dialog=$('#create-dialog');
  const submit=$('[type=submit]',event.target);
  submit.disabled=true;busy=true;
  try{
    const payload=await api('/api/sessions',{name:form.get('name'),starts_at:new Date(form.get('starts_at')).getTime()/1000,court_count:Number(form.get('court_count')),max_players:Number(form.get('max_players'))});
    dialog.close();event.target.reset();navigate(payload.session.id,'queue');message('Session created. Import your roster or load demo players.');
  }catch(error){$('.form-error',dialog).textContent=error.message;}finally{busy=false;submit.disabled=false;}
});
$('#import-form').addEventListener('submit',event=>{event.preventDefault();const form=new FormData(event.target);mutate('import',{source:form.get('source'),club_key:form.get('club_key'),csv:form.get('csv')},$('#import-dialog'));});
$('#result-form').addEventListener('submit',event=>{event.preventDefault();const form=new FormData(event.target);mutate('game',{id_game:resultGame,action:'complete',score_a:Number(form.get('score_a')),score_b:Number(form.get('score_b'))},$('#result-dialog'));});
$('#confirm-form').addEventListener('submit',event=>{event.preventDefault();if(confirmAction)mutate(confirmAction.action,{...confirmAction.data,...(confirmAction.action==='game'?{reason:$('#cancel-reason').value}:{})},$('#confirm-dialog'));});
window.addEventListener('popstate',()=>{searchTerm='';load(true);});
window.addEventListener('hashchange',()=>{searchTerm='';load(true);});
window.addEventListener('pageshow',event=>{if(event.persisted)load();});
let refreshTimer = setInterval(()=>{
  if(document.hidden||busy||$('dialog[open]')||['INPUT','SELECT','TEXTAREA'].includes(document.activeElement?.tagName))return;
  load();
},30000);
window.addEventListener('pagehide',()=>{clearInterval(refreshTimer);refreshTimer=null;});
window.addEventListener('pageshow',()=>{if(!refreshTimer)refreshTimer=setInterval(()=>{if(!document.hidden&&!busy&&!$('dialog[open]')&&!['INPUT','SELECT','TEXTAREA'].includes(document.activeElement?.tagName))load();},30000);});
load();
