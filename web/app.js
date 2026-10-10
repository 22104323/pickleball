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
let swapConfirmation = null;
let searchTerm = '';
const views = ['queue','attendance','results','activity','live'];
const levelOptions = [['1000','Beginner (~2.0 DUPR)'],['1100','Adv. Beginner (~2.5 DUPR)'],['1200','Intermediate (~3.0 DUPR)'],['1400','Adv. Intermediate (~3.5 DUPR)'],['1600','Advanced (~4.0 DUPR)'],['1800','Expert (~4.5+ DUPR)']];
const modeNames = {balanced:'Balanced',social_mix:'Social Mix',skill_separated:'Skill Separated',winners_losers:'Winners / Losers',skill_courts:'Skill Courts',mixed_doubles:'Mixed Doubles',king_queen:'King/Queen of the Court',club_wars:'Club Wars'};
let importTab = 'paste';
let reviewDraft = [];
let reviewPairs = [];
let reviewPairSelection = null;
let reviewSource = 'manual';
let reviewClubKey = 'manual-roster';
let reviewEventName = '';
let pairSelection = null;
let guideStep = -1;
let firstRender = true;
let revealObserver = null;
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
const SESSION_LINKS_KEY = 'courtside.session-links.v1';

function sessionLinks() {
  try {
    const parsed = JSON.parse(localStorage.getItem(SESSION_LINKS_KEY) || '{}');
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
  } catch { return {}; }
}

function randomLinkToken() {
  if (crypto.randomUUID) return crypto.randomUUID();
  const bytes = new Uint8Array(24);
  crypto.getRandomValues(bytes);
  return [...bytes].map(byte=>byte.toString(16).padStart(2,'0')).join('');
}

function sessionLinkFor(id) {
  const links = sessionLinks();
  const existing = Object.entries(links).find(([,sessionId])=>Number(sessionId)===Number(id));
  if (existing) return existing[0];
  const token = randomLinkToken();
  try {
    localStorage.setItem(SESSION_LINKS_KEY,JSON.stringify({...links,[token]:Number(id)}));
  } catch {
    throw new Error('This browser could not save the session link. Check local storage and try again.');
  }
  return token;
}

function sessionIdForLink(token) {
  const id = Number(sessionLinks()[token]);
  return Number.isSafeInteger(id) && sessions.some(session=>session.id===id) ? id : null;
}

function clearReveals() {
  revealObserver?.disconnect();
  revealObserver = null;
  document.querySelectorAll('.motion-reveal').forEach(node=>node.classList.remove('motion-reveal','motion-visible'));
}

function revealInitialContent() {
  if (!firstRender) return;
  firstRender = false;
  if (reducedMotion.matches || !('IntersectionObserver' in window)) return;
  const groups = [document.querySelectorAll('.page-heading .eyebrow, .page-heading h1, .page-heading p, .page-heading .heading-actions'),
    document.querySelectorAll('.welcome h2, .welcome p, .welcome .btn, .welcome-note')];
  revealObserver = new IntersectionObserver(entries=>{
    entries.forEach(entry=>{
      if (!entry.isIntersecting) return;
      entry.target.classList.add('motion-visible');
      revealObserver?.unobserve(entry.target);
    });
  }, {threshold:0.05});
  groups.forEach(nodes=>nodes.forEach((node,index)=>{
    node.style.setProperty('--entrance-delay',`${Math.min(index*80,400)}ms`);
    node.classList.add('motion-reveal');
    revealObserver.observe(node);
  }));
}
reducedMotion.addEventListener('change',()=>{if(reducedMotion.matches)clearReveals();});

function ratingLevel(rating) {
  if (rating == null) return '';
  return levelOptions.find(([value])=>Number(value)===Number(rating))?.[0] || '';
}

function updateSkillSummary() {
  const levels = new Set(reviewDraft.filter(player=>player.selected).map(player=>player.rating));
  const rating = [...levels][0];
  const label = levels.size > 1 ? 'Mixed levels' : rating == null ? 'No level set' : levelOptions.find(([value])=>Number(value)===Number(rating))?.[1] || `${rating} rating`;
  $('#review-bulk-level option[value="noop"]').textContent = label;
}

function skillStars(rating,index,name) {
  const selected=levelOptions.findIndex(([value])=>value===ratingLevel(rating));
  const label=levelOptions[selected]?.[1]||(rating==null?'Set skill':`${rating} rating`);
  return `<div class="skill-control"><div class="skill-stars" role="radiogroup" aria-label="Skill level for ${e(name)}">${levelOptions.map(([value,option],star)=>`<button type="button" role="radio" class="skill-star ${star<=selected?'is-filled':''}" aria-label="${e(option)}" aria-checked="${star===selected}" tabindex="${star===selected||selected<0&&star===0?'0':'-1'}" data-review-level="${index}" data-rating="${value}">★</button>`).join('')}</div><span class="skill-level-label" aria-live="polite">${e(label)}</span>${rating!=null?`<button type="button" class="skill-clear" data-review-clear="${index}" aria-label="Clear skill for ${e(name)}">Clear</button>`:''}</div>`;
}

function renderReview() {
  const list=$('#review-player-list');
  const scrollTop=list.scrollTop;
  const active=document.activeElement;
  const focusAttribute=list.contains(active) && ['data-review-select','data-review-name','data-review-pair','data-review-unpair','data-review-remove'].find(attribute=>active.hasAttribute(attribute));
  const focusValue=focusAttribute && active.getAttribute(focusAttribute);
  const selected=reviewDraft.filter(player=>player.selected).length;
  $('#review-title').textContent='Review players';
  $('#review-count').textContent=`${selected} player${selected===1?'':'s'} selected${reviewEventName?` · ${reviewEventName}`:''}`;
  $('#add-reviewed-players').textContent=`Add ${selected} player${selected===1?'':'s'}`;
  $('#add-reviewed-players').disabled=selected===0;
  $('#review-player-list').innerHTML=reviewDraft.map((player,index)=>{
    const partner=reviewPairs.find(pair=>pair.includes(player.external_id))?.find(id=>id!==player.external_id);
    const partnerName=reviewDraft.find(item=>item.external_id===partner)?.name;
    const selectedForPair=reviewPairSelection===player.external_id;
    return `<article class="review-card ${partner?'paired':''} ${selectedForPair?'selected-for-pair':''}"><div class="review-row"><input class="review-select" type="checkbox" data-review-select="${index}" aria-label="Select ${e(player.name)}" ${player.selected?'checked':''}><input class="review-name" type="text" data-review-name="${index}" aria-label="Player name" maxlength="80" value="${e(player.name)}"><span class="review-badge-wrap">${partner?`<span class="review-pair-badge">Paired: ${e(partnerName||'Player')}</span>`:''}</span>${partner?`<button type="button" class="review-pair-action" data-review-unpair="${e(player.external_id)}">Unpair</button>`:`<button type="button" class="review-pair-action" data-review-pair="${e(player.external_id)}">${selectedForPair?'Choose player':'Pair'}</button>`}<button type="button" class="review-remove" data-review-remove="${index}" aria-label="Remove ${e(player.name)} from this list">×</button></div><div class="review-meta"><small class="review-source">${e(reviewSource==='reclub'?'Reclub sign-up':'New player')}</small>${skillStars(player.rating,index,player.name)}${state?.session.mode==='club_wars'?`<select data-review-group="${index}" aria-label="Club Wars group for ${e(player.name)}"><option value="" ${!player.club_group?'selected':''}>Choose group</option><option value="A" ${player.club_group==='A'?'selected':''}>Group A</option><option value="B" ${player.club_group==='B'?'selected':''}>Group B</option></select>`:''}</div></article>`;
  }).join('');
  list.scrollTop=scrollTop;
  if(focusAttribute) {
    const value=CSS.escape(focusValue);
    const restore=list.querySelector(`[${focusAttribute}="${value}"]`)
      || (focusAttribute.includes('pair') && list.querySelector(`[data-review-pair="${value}"], [data-review-unpair="${value}"]`))
      || $('#add-reviewed-players');
    restore.focus({preventScroll:true});
  }
  updateSkillSummary();
}

function showReview() {
  $('#review-error').textContent='';
  $('#pair-help').textContent='Select a player’s Pair button, then select a second player to set a teammate preference.';
  $('#review-bulk-level').value='noop';
  renderReview();
  $('#import-dialog').close();
  $('#review-dialog').showModal();
}

function guideMarkup() {
  const steps=[
    ['Set up today’s session','Choose the number of courts and play format. Open session settings to adjust the details.'],
    ['Add players','Paste a list or load confirmed sign-ups from a public Reclub event. Review names and partners before adding.'],
    ['Check players in','A Reclub RSVP is not physical attendance. Check players in when they arrive.'],
    ['Start the next game','Build a fair matchup, send it to an open court, and start only when the players are ready.']
  ];
  const [title,description]=steps[guideStep]||steps[0];
  return `<div class="eyebrow">STEP ${guideStep+1} OF ${steps.length}</div><h3>${e(title)}</h3><p>${e(description)}</p><div class="guide-progress" aria-label="Guide step ${guideStep+1} of ${steps.length}">${steps.map((_,index)=>`<span class="${index===guideStep?'active':''}"></span>`).join('')}</div><div class="guide-actions"><button type="button" class="btn btn-small btn-outline" data-guide="skip">Skip</button><button type="button" class="btn btn-small btn-primary" data-guide="next">${guideStep===steps.length-1?'Done':'Next'}</button></div>`;
}

function parsePlayerLines(value) {
  const lines=String(value||'').split(/\r?\n/).map(line=>line.trim()).filter(Boolean);
  if(!lines.length)throw new Error('Paste at least one player name.');
  if(lines.length>200)throw new Error('Review lists can contain at most 200 players.');
  const counts=new Map();
  return lines.map((line,index)=>{
    const fields=line.includes('\t')?line.split('\t').map(value=>value.trim()):line.split(',').map(value=>value.trim());
    const name=fields[0];
    if(!name||name.length>80)throw new Error(`Player ${index+1} needs a name under 80 characters.`);
    let externalId='';
    let rating=null;
    if(fields.length>=3){externalId=fields[1];rating=parsePlayerRating(fields[2]);}
    else if(fields.length===2){
      if(/^(?:dupr\s*)?\d+(?:\.\d+)?(?:\s*dupr)?$/i.test(fields[1]))rating=parsePlayerRating(fields[1]);
      else externalId=fields[1];
    }
    const identity=externalId?`dupr:${externalId.toLowerCase().replace(/[^a-z0-9._-]/g,'')}`:'';
    const slug=name.normalize('NFKD').toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'')||`player-${index+1}`;
    const occurrences=(counts.get(slug)||0)+1;counts.set(slug,occurrences);
    return {external_id:identity||`name:${slug}${occurrences>1?`-${occurrences}`:''}`,name,rating,gender:null,club_group:null,selected:true};
  });
}

function parsePlayerRating(value) {
  const number=Number(String(value).replace(/[^0-9.]/g,''));
  if(!Number.isFinite(number))throw new Error('Rating must be a number or an approximate DUPR level.');
  const duprRatings={2:1000,2.5:1100,3:1200,3.5:1400,4:1600,4.5:1800,5:1950};
  const rating=number>0&&number<=6?(duprRatings[number]??null):number;
  if(rating===null||rating<0||rating>4000)throw new Error('Use an approximate DUPR level from 2.0 to 5.0 or a rating from 0 to 4000.');
  return rating;
}

function errorFor(dialog) {
  return $('#review-error',dialog)||$('#import-error',dialog)||$('.form-error',dialog);
}

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

function initials(name) { const parts=name.replace(/\((?:demo|synthetic)\)/g,'').trim().split(/\s+/);return (parts.length===1?parts[0].slice(0,2):parts.slice(0,2).map(n=>n[0]).join('')).toUpperCase(); }
function avatar(name) { return `<span class="avatar" aria-hidden="true">${e(initials(name))}</span>`; }
function button(label, attrs, kind='btn-outline') { return `<button class="btn btn-small ${kind}" ${attrs} ${busy?'disabled':''}>${label}</button>`; }
function playerButton(player, action, label, kind='btn-outline') { return button(label,`data-player="${player.id}" data-player-action="${action}"`,kind); }
function empty(title, description, action='') { return `<div class="empty-state"><h3>${e(title)}</h3><p>${e(description)}</p>${action}</div>`; }
function closed() { return state?.session.status === 'closed'; }

function syncNavigation() {
  const params = new URLSearchParams(location.hash.slice(1));
  view = views.includes(params.get('view')) ? params.get('view') : 'queue';
  const token = params.get('link');
  if (token) return sessionIdForLink(token);
  return null;
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
  const hash = id ? `#link=${encodeURIComponent(sessionLinkFor(id))}&view=${encodeURIComponent(nextView)}` : `#view=${nextView}`;
  if (hash !== location.hash) history[replace?'replaceState':'pushState'](null,'',hash);
  view = nextView;
  swapConfirmation = null;
  searchTerm = '';
  load(true);
}

function render(animate = false) {
  clearReveals();
  document.body.classList.toggle('has-session',Boolean(state));
  $('#landing-page').hidden = Boolean(state);
  const route = new URLSearchParams(location.hash.slice(1));
  const hasRequestedLink = route.has('link') || route.has('session');
  $('#landing-message').hidden = !hasRequestedLink || Boolean(state);
  $('#landing-message').textContent = hasRequestedLink && !state ? 'This session link is not available in this browser. Generate a new link on the original browser.' : '';
  if (swapConfirmation && (swapConfirmation.session !== state?.session.id || swapConfirmation.revision !== state?.session.revision)) swapConfirmation = null;
  const selection = $('#session-select');
  selection.innerHTML = (state ? `<option value="${state.session.id}" selected>${e(state.session.name)}${state.session.status==='closed'?' · closed':''}</option>` : '<option value="">No sessions yet</option>') + '<option value="new">+ New session</option>';
  document.querySelectorAll('[data-view]').forEach(node => {
    node.classList.toggle('active',node.dataset.view===view);
    if(node.dataset.view===view) node.setAttribute('aria-current','page'); else node.removeAttribute('aria-current');
  });
  $('#import-button').hidden = view === 'live';
  $('#import-button').disabled = busy || !state || closed();
  $('#fill-button').disabled = busy || !state || closed() || view !== 'queue';
  $('#fill-button').hidden = view !== 'queue';
  if (!state) {
    $('#summary').hidden = true;
    $('#fill-button').hidden=true;
    $('#view-content').innerHTML = `<div class="welcome"><div><h2>A fair rotation starts with who’s here.</h2><p>Bring your roster, check players in, and build balanced doubles games. Everyone’s wait matters. Strong players don’t get to stack.</p><button class="btn" data-open="create-dialog">Create your first session <span aria-hidden="true">↗</span></button><span class="welcome-note">Local workspace · no sign-in or installation needed</span></div><div class="welcome-court" aria-hidden="true"></div></div><div class="helper-strip"><strong>Just trying it out?</strong><span>Create a session, then load 30 synthetic demo players.</span></div>`;
    return;
  }
  const {session:s,metrics:m} = state;
  $('#session-title').textContent = s.name;
  $('#session-date').textContent = new Date(s.starts_at*1000).toLocaleDateString(undefined,{weekday:'long',month:'long',day:'numeric'}).toUpperCase();
  $('#session-subtitle').textContent = `${s.court_count} court${s.court_count===1?'':'s'} · ${s.max_players} player capacity · ${modeNames[s.mode]||'Balanced'}${closed()?' · Session closed. Ratings finalized.':''}`;
  const reserved=state.players.filter(player=>player.queue_state==='assigned').length;
  $('#nav-count').textContent = m.waiting+reserved;
  $('#summary').hidden = false;
  const activeCourts = state.games.filter(g => g.status==='playing').length;
  const metrics = [ ['Checked in',m.present,`of ${state.players.length} on the roster`],['In the queue',m.waiting+reserved,'Includes reserved Up Next players'],['Courts occupied',activeCourts,`of ${s.court_count} available`],['Games completed',m.completed_games,closed()?'Ratings updated':'Ratings finalize at session close'] ];
  $('#summary').innerHTML = metrics.map(([label,value,note])=>`<div class="metric"><div class="metric-label">${e(label)}</div><div class="metric-value">${value}</div><div class="metric-note">${e(note)}</div></div>`).join('');
  $('#view-content').innerHTML = view === 'queue' ? queueView() : view === 'attendance' ? attendanceView() : view === 'results' ? resultsView() : view === 'live' ? liveView() : activityView();
  $('#view-content').classList.toggle('view-enter',animate);
  $('#updated-label').textContent = `Saved locally · revision ${s.revision}`;
  filterRows();
  revealInitialContent();
}

function stagedGames() { return state.games.filter(game=>game.status==='assigned').sort((a,b)=>a.court-b.court||a.id-b.id); }

function gameTeams(game) {
  return ['a','b'].map(side=>`<div class="team"><span class="team-label">Team ${side==='a'?'1':'2'}</span>${game.players.filter(player=>player.side===side).map(player=>{
    const roster=state.players.find(p=>p.id===player.id_roster);
    return `<div class="court-player"><div><strong>${e(player.name)}</strong><small>${e(roster?.band||'Unrated')}${['winners_losers','king_queen'].includes(state.session.mode)?` · ${e(roster?.last_outcome||'New player')}`:''}</small></div></div>`;
  }).join('')}</div>`).join('');
}

function courtCard(court, readOnly = false) {
  const game=state.games.find(game=>game.court===court&&['assigned','playing'].includes(game.status));
  if(game?.status==='playing')return `<article class="court-card is-playing" data-court="${court}"><div class="court-top"><h3>Court ${court}</h3><span class="chip active">On court</span></div><div class="court-teams">${gameTeams(game)}</div>${readOnly?'':`<div class="winner-actions">${button('Team 1 Wins',`data-winner="${game.id}" data-side="a"`,'btn-team-one')}${button('Team 2 Wins',`data-winner="${game.id}" data-side="b"`,'btn-team-two')}</div><div class="court-secondary">${button('Cancel game',`data-cancel="${game.id}"`)}</div>`}</article>`;
  const number=game?stagedGames().findIndex(item=>item.id===game.id)+1:null;
  const teams=game?['a','b'].map(side=>`<div>${game.players.filter(p=>p.side===side).map(p=>`<span>${e(p.name)}</span>`).join('')}</div>`):[];
  return `<article class="court-card court-available" data-court="${court}"><div class="court-top"><h3>Court ${court}</h3><span class="chip">${closed()?'Session closed':'Available'}</span></div><div class="court-preview">${game?`${teams[0]}<span class="versus">vs</span>${teams[1]}`:`<p>${closed()?'Results are saved for this session.':'Build Up Next from checked-in players.'}</p>`}</div>${game&&!readOnly?`<div class="available-actions">${button(`Start Up Next ${number}`,`data-game="${game.id}" data-game-action="start"`,'btn-primary')}</div>`:''}</article>`;
}

function upNextCard(game,index) {
  const outcomes=new Set(game.players.map(player=>state.players.find(p=>p.id===player.id_roster)?.last_outcome));
  const outcome=state.session.mode==='winners_losers'&&outcomes.size===1?[...outcomes][0]:null;
  return `<article class="up-next-card" data-up-next="${game.id}"><div class="up-next-heading"><h3>Up Next ${index+1}</h3><span class="chip">Auto</span>${outcome?`<span class="chip active">${outcome==='winner'?'Winners':'Losers'}</span>`:''}${button('Rebuild',`data-game="${game.id}" data-game-action="rebuild"`)}</div><div class="court-teams">${gameTeams(game)}</div><div class="up-next-actions">${button(`Send to Court ${game.court}`,`data-game="${game.id}" data-game-action="start"`,'btn-primary')}${button('Cancel',`data-cancel="${game.id}"`)}</div><p class="match-reason">${e(state.session.mode==='balanced'?`Balanced · team gap ${Math.round(Math.abs(game.mean_a-game.mean_b))}`:modeNames[state.session.mode])}</p></article>`;
}

function tableToolbar(title, note, search=true) { return `<div class="panel-toolbar"><div><h2>${e(title)}</h2><p class="toolbar-copy">${e(note)}</p></div>${search?`<div class="search-wrap"><label for="player-search" class="sr-only">Search players</label><input id="player-search" placeholder="Search players…" value="${e(searchTerm)}" type="search"></div>`:''}</div>`; }

function queueView() {
  const queued=state.players.filter(player=>['waiting','assigned'].includes(player.queue_state));
  const staged=stagedGames();
  return `<section aria-label="Live Courts"><div class="section-title"><h2>Live Courts <span class="section-count">(${state.session.court_count})</span></h2><span class="live-label">${closed()?'Session archived':'Session active'}</span></div><div class="courts">${Array.from({length:state.session.court_count},(_,i)=>courtCard(i+1)).join('')}</div></section><section aria-label="Upcoming matches"><div class="section-title upcoming-title"><h2>Up Next <span class="section-count">(${staged.length})</span></h2><span class="muted">${e(modeNames[state.session.mode])}</span></div><div class="rotation-layout"><section class="queue-panel" aria-labelledby="queue-title"><div class="queue-heading"><h3 id="queue-title">Queue <span>(${queued.length})</span></h3>${!closed()?button('+ Add player','data-open="import-dialog"'):''}</div><div class="queue-search"><label class="sr-only" for="player-search">Search players</label><input id="player-search" type="search" placeholder="Search players…" value="${e(searchTerm)}"></div>${queued.length?`<ol class="queue-list">${queued.map((player,index)=>`<li class="queue-entry ${player.queue_state==='assigned'?'reserved':''}" data-name="${e(player.name.toLowerCase())}"><span class="queue-position">${index+1}</span><div><strong>${e(player.name)}</strong><small>${e(player.band)} · ${player.games_played} games · Waiting ${Math.floor(player.wait_minutes)}m</small>${player.queue_state==='assigned'?'<span class="reserved-label">Reserved in Up Next</span>':''}</div>${player.queue_state==='waiting'?playerButton(player,'pause','Take a break'):''}</li>`).join('')}</ol>`:empty(closed()?'Session complete':'No players queued',closed()?'Attendance and results remain saved.':'Check in players from Attendance to add them to the queue.',closed()?'':button('Check in players','data-view="attendance"','btn-primary'))}</section><div class="up-next-area"><div class="up-next-grid">${staged.length?staged.map(upNextCard).join(''):empty(closed()?'No upcoming games':'Your next match goes here',closed()?'This session has ended.':'Fill open courts to build a match. Start it when all four players are ready.')}</div><p class="rotation-note">${state.session.mode==='social_mix'?'Social Mix prepares one match at a time. Start it before building the next mix.':'Up Next reserves four players for an available court. They remain here until you start or cancel the match.'}</p></div></div></section>${!state.players.length&&!closed()?`<div class="helper-strip"><strong>Start with your roster</strong><span>Paste a player list, use a Reclub link, or try synthetic demo players.</span>${button('Load demo roster','data-action="demo"')}</div>`:''}<div class="session-tools">${!closed()?button('Close session & finalize ratings','data-confirm="close"'):''}</div>`;
}

function attendanceView() {
  const players=state.players;
  const selected=players.find(player=>player.id===pairSelection);
  const pairNotice=selected?`<div class="pair-selection-notice" role="status">Choose another player to pair with ${e(selected.name)}.${button('Cancel pairing','data-pair-cancel')}</div>`:'';
  const pairAction=player=>{
    if(player.paired_roster_id)return `<span class="pair-pill">Paired: ${e(player.partner_name||'Player')}</span>${button('Unpair',`data-unpair-player="${player.id}"`,'btn-outline')}`;
    if(['assigned','playing'].includes(player.queue_state))return 'On court';
    const label=pairSelection&&pairSelection!==player.id?`Pair with ${e(selected?.name||'selected player')}`:pairSelection===player.id?'Cancel pair':'Pair';
    return button(label,`data-pair-player="${player.id}"`);
  };
  return `<section class="panel">${tableToolbar('Session attendance','RSVP is a plan. Check-in is presence. Pair preferences keep chosen partners together.')}${players.length?`<div class="attendance-toolbar">${!closed()?button('Check in all','data-action="checkin-all"','btn-primary'):''}${pairNotice}</div><div class="table-wrap"><table class="attendance-table"><thead><tr><th>Player</th><th>RSVP</th><th>Attendance</th><th>Eligibility</th><th>Rotation</th><th>Pairing</th><th>Action</th></tr></thead><tbody>${players.map(p=>`<tr class="${p.paired_roster_id?'paired-row ':''}${p.id===pairSelection?'pairing-selected':''}" data-name="${e(p.name.toLowerCase())}"><td data-label="Player"><div class="player-cell">${avatar(p.name)}<div><strong>${e(p.name)}</strong><small>${e(p.external_id)} · ${e(p.source)}</small></div></div></td><td data-label="RSVP">${e(p.rsvp)}</td><td data-label="Attendance"><span class="chip ${p.attendance==='present'?'active':p.attendance==='no_show'?'warn':''}">${e(p.attendance.replace('_',' '))}${p.is_late?' · late':''}</span></td><td data-label="Eligibility">${closed()?e(`${p.membership} / ${p.waiver}`):`<div class="inline-eligibility" data-eligibility="${p.id}"><select aria-label="Membership for ${e(p.name)}" data-membership ${['assigned','playing'].includes(p.queue_state)?'disabled':''}>${['active','expired','unknown'].map(x=>`<option ${p.membership===x?'selected':''}>${x}</option>`).join('')}</select><select aria-label="Waiver for ${e(p.name)}" data-waiver ${['assigned','playing'].includes(p.queue_state)?'disabled':''}>${['valid','missing','unknown'].map(x=>`<option ${p.waiver===x?'selected':''}>${x}</option>`).join('')}</select><button class="btn btn-small btn-outline" data-save-eligibility="${p.id}" aria-label="Save eligibility for ${e(p.name)}" ${['assigned','playing'].includes(p.queue_state)?'disabled':''}>Save</button></div>`}</td><td data-label="Rotation">${p.eligible?e(p.queue_state==='off'?'Not queued':p.queue_state):'<span class="chip blocked">Not eligible</span>'}</td><td data-label="Pairing"><div class="pair-control">${closed()?'—':pairAction(p)}</div></td><td data-label="Action"><div class="row-actions">${closed()?'—':p.attendance!=='present'?playerButton(p,'checkin','Check in','btn-primary'):['assigned','playing'].includes(p.queue_state)?'On court':`${p.queue_state==='waiting'?playerButton(p,'pause','Pause'):p.eligible?playerButton(p,'resume','Rejoin','btn-primary'):''}${playerButton(p,'checkout','Check out')}`}</div></td></tr>`).join('')}</tbody></table></div>`:empty('Your roster starts here','Paste a player list or load a public Reclub event. Review names and pair preferences before adding.',`${button('Import player list','data-open="import-dialog"','btn-primary')} ${button('Load demo roster','data-action="demo"')}`)}</section>${!closed()?`<div class="session-tools">${button('Reconcile absent RSVPs','data-confirm="reconcile"')}${button('Close session & finalize ratings','data-confirm="close"')}</div>`:''}<div class="helper-strip"><span>Reclub sign-ups start in Not Yet Here. A player joins the queue only after physical check-in and eligibility confirmation.</span></div>`;
}

function standingsView() {
  return `<section class="panel standings-panel"><div class="panel-toolbar"><div><h2>Live Standings</h2><p>Wins update with corrected results. Games played count completed games.</p></div></div>${state.standings.length?`<div class="table-wrap"><table class="standings-table"><thead><tr><th>Player</th><th>Wins</th><th>Losses</th><th>Games played</th></tr></thead><tbody>${state.standings.map(player=>`<tr data-standing="${player.id}"><td><strong>${e(player.name)}</strong></td><td>${player.wins}</td><td>${player.losses}</td><td>${player.games_played}</td></tr>`).join('')}</tbody></table></div>`:empty('No players yet','Add your roster to see standings here.')}</section>`;
}

function liveView() {
  return `<div class="section-title"><div><h2>Live View</h2><p>Display view on this computer. Organizer controls are in Live queue.</p></div></div><div class="courts">${Array.from({length:state.session.court_count},(_,i)=>courtCard(i+1,true)).join('')}</div>${standingsView()}`;
}

function resultsView() {
  const games = state.games.filter(g=>['completed','cancelled'].includes(g.status));
  return `${standingsView()}<section class="panel">${tableToolbar('Game results',`${state.metrics.completed_games} completed · cancelled games do not affect ratings`,false)}${games.length?`<div class="table-wrap"><table class="result-table"><thead><tr><th>Game</th><th>Team 1</th><th>Team 2</th><th>Result</th><th>Correction</th></tr></thead><tbody>${games.map(g=>`<tr data-result-row="${g.id}"><td><strong>#${g.id}</strong><br><small class="muted">Court ${g.court}</small></td><td>${g.players.filter(p=>p.side==='a').map(p=>e(p.name)).join('<br>')}</td><td>${g.players.filter(p=>p.side==='b').map(p=>e(p.name)).join('<br>')}</td><td><span class="chip ${g.status==='completed'?'active':''}">${g.status==='completed'?`Team ${g.score_a>g.score_b?'1':'2'} won`:'Cancelled'}</span></td><td>${g.status!=='completed'||closed()?'—':swapConfirmation?.id===g.id?`<div class="swap-confirmation" role="group" aria-label="Swap winner for game ${g.id}"><span>Swap winner?</span>${button('Cancel',`data-swap-cancel="${g.id}"`)}${button('Swap',`data-swap-confirm="${g.id}"`,'btn-primary')}</div>`:button('Swap winner',`data-swap-winner="${g.id}"`)}</td></tr>`).join('')}</tbody></table></div>`:empty('The first result is still ahead','Start an assigned game, then choose the winning team when it finishes.')}<div class="rating-note">${closed()?'Ratings were finalized as one session period. Closed sessions cannot be corrected.':'Swap reverses the recorded winner. Up Next teams stay reserved; use Rebuild separately to reconsider them. Ratings update at session close.'} Individual doubles ratings use an experimental Glicko-2 adaptation.</div></section>`;
}

function activityView() {
  const labels = {'session.created':'Session created','roster.imported':'Roster imported','roster.reviewed_imported':'Reviewed players added','player.checkin':'Player checked in','players.checked_in_all':'Players checked in','players.paired':'Players paired','players.unpaired':'Pair preference removed','player.checkout':'Player checked out','player.pause':'Player took a break','player.resume':'Player rejoined the queue','player.eligibility':'Eligibility updated','courts.assigned':'Courts assigned','game.start':'Game started','game.complete':'Game result recorded','game.winner_swapped':'Recorded winner corrected','game.rebuilt':'Up Next rebuilt','game.cancelled':'Game cancelled','attendance.reconciled':'Absentees reconciled','session.closed':'Session closed; ratings finalized'};
  return `<section class="panel">${tableToolbar('Session activity','Changes are recorded locally. Recent 30 actions shown.',false)}<ul class="activity-list">${state.audit.map(a=>`<li><span>${e(labels[a.action]||a.action)}</span><time datetime="${new Date(a.created_at*1000).toISOString()}">${new Date(a.created_at*1000).toLocaleTimeString(undefined,{hour:'2-digit',minute:'2-digit'})}</time></li>`).join('')}</ul></section><div class="helper-strip"><span>Reclub preview is read-only. Check-ins and game results stay in this local workspace.</span></div>`;
}

function filterRows() {
  document.querySelectorAll('[data-name]').forEach(row=>row.hidden=!row.dataset.name.includes(searchTerm.toLowerCase()));
}

async function mutate(action, data={}, dialog=null) {
  if (busy || !state) return false;
  const id = state.session.id;
  const focused = document.activeElement;
  const focusGame = focused?.dataset.swapConfirm || focused?.dataset.game || focused?.dataset.winner;
  const focusPlayer = focused?.dataset.player;
  const focusAction = focused?.dataset.playerAction;
  busy = true;
  document.querySelectorAll('button').forEach(b=>{b.dataset.wasDisabled=String(b.disabled);b.disabled=true;});
  if(dialog&&errorFor(dialog)) errorFor(dialog).textContent='';
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
    message(state.notice || (action==='game' && data.action==='complete' && data.winner
      ? `Team ${data.winner==='a'?'1':'2'} won. Result recorded.` : ''));
    if(focusGame) ($(`[data-swap-winner="${focusGame}"]`) || $(`[data-game="${focusGame}"]`) || $('#workspace')).focus({preventScroll:true});
    if(focusPlayer) {
      const restore = $(`[data-player="${focusPlayer}"][data-player-action="${focusAction}"]`) || $(`tr:has([data-save-eligibility="${focusPlayer}"]) button[data-player]`);
      (restore || $('#workspace')).focus({preventScroll:true});
    }
    return true;
  } catch (error) {
    if(dialog&&errorFor(dialog)) errorFor(dialog).textContent=error.message; else message(error.message,true);
    if(error.status===409) { busy=false; await load(); }
    return false;
  } finally {
    busy=false;
    document.querySelectorAll('button[data-was-disabled]').forEach(b=>{b.disabled=b.dataset.wasDisabled==='true';delete b.dataset.wasDisabled;});
  }
}

function openDialog(id) {
  const dialog = $(`#${id}`);
  const error=errorFor(dialog);if(error)error.textContent='';
  if(id==='create-dialog') {
    const now = new Date();
    now.setMinutes(now.getMinutes()-now.getTimezoneOffset());
    $('#session-start').value=now.toISOString().slice(0,16);
    guideStep=-1;$('#guide-panel').hidden=true;
  }
  dialog.showModal();
}

document.addEventListener('click', event=>{
  const target = event.target.closest('button');
  if(!target || busy || target.disabled) return;
  if(target.classList.contains('close-dialog')) return target.closest('dialog').close();
  if(target.dataset.guide) {
    if(target.dataset.guide==='start')guideStep=0;
    else if(target.dataset.guide==='skip'){guideStep=-1;$('#guide-panel').hidden=true;return;}
    else if(target.dataset.guide==='next'){if(guideStep>=3){guideStep=-1;$('#guide-panel').hidden=true;return;}guideStep+=1;}
    $('#guide-panel').innerHTML=guideMarkup();$('#guide-panel').hidden=false;return;
  }
  if(target.dataset.importTab) {
    importTab=target.dataset.importTab;
    document.querySelectorAll('[data-import-tab]').forEach(tab=>{const active=tab.dataset.importTab===importTab;tab.classList.toggle('active',active);tab.setAttribute('aria-selected',String(active));});
    document.querySelectorAll('[data-import-pane]').forEach(pane=>pane.hidden=pane.dataset.importPane!==importTab);
    $('#review-players-button').textContent=importTab==='reclub'?'Load players':'Review players';
    $('#import-error').textContent='';return;
  }
  if(target.dataset.reviewLevel!==undefined) {
    const index=Number(target.dataset.reviewLevel),rating=Number(target.dataset.rating);
    const player=reviewDraft[index];
    if(player&&levelOptions.some(([value])=>Number(value)===rating)) {
      player.rating=rating;
      target.closest('.skill-control').outerHTML=skillStars(rating,index,player.name);
      updateSkillSummary();
      $(`[data-review-level="${index}"][aria-checked="true"]`)?.focus({preventScroll:true});
    }
    return;
  }
  if(target.dataset.reviewClear!==undefined) {
    const index=Number(target.dataset.reviewClear),player=reviewDraft[index];
    if(player) {
      player.rating=null;
      target.closest('.skill-control').outerHTML=skillStars(null,index,player.name);
      updateSkillSummary();
      $(`[data-review-level="${index}"][tabindex="0"]`)?.focus({preventScroll:true});
    }
    return;
  }
  if(target.dataset.reviewPair) {
    const id=target.dataset.reviewPair;
    const player=reviewDraft.find(item=>item.external_id===id);
    if(!player?.selected){$('#review-error').textContent='Select both players before pairing them.';return;}
    if(!reviewPairSelection){reviewPairSelection=id;$('#pair-help').textContent=`Choose a second selected player to pair with ${player.name}.`;}
    else if(reviewPairSelection===id){reviewPairSelection=null;$('#pair-help').textContent='Select a player’s Pair button, then select a second player to set a teammate preference.';}
    else{
      const other=reviewDraft.find(item=>item.external_id===reviewPairSelection);
      if(!other?.selected){reviewPairSelection=id;return;}
      if(reviewPairs.some(pair=>pair.includes(id)||pair.includes(reviewPairSelection))){$('#review-error').textContent='Unpair a player before choosing a new partner.';return;}
      reviewPairs.push([reviewPairSelection,id]);reviewPairSelection=null;$('#pair-help').textContent='Paired players stay together when a court is assigned. You can unpair them any time.';
    }
    $('#review-error').textContent='';renderReview();return;
  }
  if(target.dataset.reviewUnpair) {
    reviewPairs=reviewPairs.filter(pair=>!pair.includes(target.dataset.reviewUnpair));reviewPairSelection=null;renderReview();return;
  }
  if(target.dataset.reviewRemove!==undefined) {
    const player=reviewDraft[Number(target.dataset.reviewRemove)];
    if(player)reviewPairs=reviewPairs.filter(pair=>!pair.includes(player.external_id));
    reviewDraft.splice(Number(target.dataset.reviewRemove),1);reviewPairSelection=null;renderReview();return;
  }
  if(target.id==='edit-player-list'){ $('#review-dialog').close();$('#import-dialog').showModal();return; }
  if(target.id==='add-reviewed-players') {
    const selected=reviewDraft.filter(player=>player.selected);
    const ids=new Set(selected.map(player=>player.external_id));
    const players=selected.map(({external_id,name,rating,club_group})=>({external_id,name,rating,club_group}));
    const pairs=reviewPairs.filter(pair=>pair.every(id=>ids.has(id)));
    return mutate('import-reviewed',{players,pairs,source:reviewSource,club_key:reviewClubKey},$('#review-dialog'));
  }
  if(target.dataset.pairPlayer) {
    const id=Number(target.dataset.pairPlayer);
    if(pairSelection===null){pairSelection=id;render();return;}
    if(pairSelection===id){pairSelection=null;render();return;}
    const first=pairSelection;pairSelection=null;return mutate('pair',{action:'pair',id_a:first,id_b:id});
  }
  if(target.dataset.unpairPlayer)return mutate('pair',{action:'unpair',id_roster:Number(target.dataset.unpairPlayer)});
  if(target.dataset.pairCancel!==undefined){pairSelection=null;render();return;}
  if(target.dataset.swapWinner) {
    swapConfirmation={id:Number(target.dataset.swapWinner),session:state.session.id,revision:state.session.revision};
    render();$(`[data-swap-cancel="${swapConfirmation.id}"]`)?.focus({preventScroll:true});return;
  }
  if(target.dataset.swapCancel) {
    const id=target.dataset.swapCancel;swapConfirmation=null;render();
    $(`[data-swap-winner="${id}"]`)?.focus({preventScroll:true});return;
  }
  if(target.dataset.swapConfirm) return mutate('game',{id_game:Number(target.dataset.swapConfirm),action:'swap_winner'});
  if(target.dataset.view) {navigate(state?.session.id,target.dataset.view);$('#workspace').focus({preventScroll:true});return;}
  if(target.dataset.open) return openDialog(target.dataset.open);
  if(target.dataset.action) return mutate(target.dataset.action);
  if(target.dataset.player) return mutate('player',{id_roster:Number(target.dataset.player),action:target.dataset.playerAction});
  if(target.dataset.saveEligibility) {
    const fields=target.closest('[data-eligibility]');
    return mutate('player',{id_roster:Number(target.dataset.saveEligibility),action:'eligibility',membership:$('[data-membership]',fields).value,waiver:$('[data-waiver]',fields).value});
  }
  if(target.dataset.game) return mutate('game',{id_game:Number(target.dataset.game),action:target.dataset.gameAction});
  if(target.dataset.winner) return mutate('game',{id_game:Number(target.dataset.winner),action:'complete',winner:target.dataset.side});
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

document.addEventListener('keydown',event=>{
  if(event.key==='Escape' && swapConfirmation && !busy) {
    const id=swapConfirmation.id;swapConfirmation=null;render();
    $(`[data-swap-winner="${id}"]`)?.focus({preventScroll:true});
  }
});

$('#session-select').addEventListener('change',event=>{
  if(event.target.value==='new'){event.target.value=state?.session.id||'';openDialog('create-dialog');}
  else navigate(Number(event.target.value));
});
$('#generate-link').addEventListener('click',async()=>{
  if(busy)return;
  const button=$('#generate-link');
  $('#landing-message').hidden=true;
  button.disabled=true;busy=true;
  try{
    const payload=await api('/api/sessions',{name:'Open Play',starts_at:Date.now()/1000,court_count:1,max_players:30,mode:'balanced'});
    const token=sessionLinkFor(payload.session.id);
    navigate(payload.session.id,'queue',true);
    try{await navigator.clipboard?.writeText(`${location.origin}${location.pathname}${location.search}#link=${encodeURIComponent(token)}&view=queue`);}catch{}
  }catch(error){$('#landing-message').textContent=error.message;$('#landing-message').hidden=false;}
  finally{busy=false;button.disabled=false;}
});
document.querySelectorAll('.mode-picker input[name="mode"]').forEach(input=>input.addEventListener('change',()=>{
  document.querySelectorAll('.mode-option').forEach(option=>option.classList.toggle('selected',option.querySelector('input')?.checked));
  const notes={balanced:'Ratings and recent history guide each balanced doubles matchup.',social_mix:'Social Mix minimizes repeat partners and spreads opponents. Ratings are not used.',skill_separated:'Players are grouped by their current rating band; a court may wait for four.',winners_losers:'Recent winners and losers rotate within their groups. New players can join either group.',skill_courts:'Open courts draw from separate skill bands, starting with the largest ready group.',mixed_doubles:'Set each player’s category during roster review. Names are never used to infer it.',king_queen:'Winners target a higher court and losing players target a lower court.',club_wars:'Assign every player to Group A or Group B during roster review.'};
  $('#mode-help').textContent=notes[input.value]||notes.balanced;
}));
document.querySelector('.mode-picker input[name="mode"]:checked')?.dispatchEvent(new Event('change'));
document.addEventListener('input',event=>{if(event.target.id==='player-search'){searchTerm=event.target.value;filterRows();}});
$('#create-form').addEventListener('submit',async event=>{
  event.preventDefault();
  if(busy)return;
  const form=new FormData(event.target);
  const dialog=$('#create-dialog');
  const submit=$('[type=submit]',event.target);
  submit.disabled=true;busy=true;
  try{
    const payload=await api('/api/sessions',{name:form.get('name'),starts_at:new Date(form.get('starts_at')).getTime()/1000,court_count:Number(form.get('court_count')),max_players:Number(form.get('max_players')),mode:form.get('mode')});
    dialog.close();event.target.reset();navigate(payload.session.id,'queue');message('Session created. Import your roster or load demo players.');
  }catch(error){$('.form-error',dialog).textContent=error.message;}finally{busy=false;submit.disabled=false;}
});
$('#import-form').addEventListener('submit',async event=>{
  event.preventDefault();if(busy)return;
  const error=$('#import-error');error.textContent='';
  const submit=$('#review-players-button');
  if(importTab==='paste'){
    try{reviewDraft=parsePlayerLines($('#player-names').value);reviewSource='manual';reviewClubKey='manual-roster';reviewEventName='';reviewPairs=[];reviewPairSelection=null;showReview();}
    catch(problem){error.textContent=problem.message;}
    return;
  }
  submit.disabled=true;submit.textContent='Loading players…';busy=true;
  try{
    const roster=await api('/api/reclub/preview',{url:$('#reclub-link').value});
    if(!roster.players.length)throw new Error('No confirmed participants were available for review.');
    reviewDraft=roster.players.map(player=>({...player,selected:true}));reviewSource='reclub';reviewClubKey=roster.club_key;reviewEventName=roster.event_name;reviewPairs=[];reviewPairSelection=null;showReview();
  }catch(problem){error.textContent=problem.message;}
  finally{busy=false;submit.disabled=false;submit.textContent='Load players';}
});
$('#review-player-list').addEventListener('change',event=>{
  const target=event.target;
  if(target.dataset.reviewSelect!==undefined){
    const player=reviewDraft[Number(target.dataset.reviewSelect)];if(player){player.selected=target.checked;if(!target.checked)reviewPairs=reviewPairs.filter(pair=>!pair.includes(player.external_id));}
    renderReview();return;
  }
  if(target.dataset.reviewGroup!==undefined)reviewDraft[Number(target.dataset.reviewGroup)].club_group=target.value||null;
});
$('#review-player-list').addEventListener('keydown',event=>{
  const target=event.target;
  if(target.dataset.reviewLevel===undefined||!['ArrowRight','ArrowDown','ArrowLeft','ArrowUp','Home','End'].includes(event.key))return;
  const radios=[...target.closest('[role="radiogroup"]').querySelectorAll('[data-review-level]')];
  const index=radios.indexOf(target);
  const next=event.key==='Home'?0:event.key==='End'?radios.length-1:(index+(event.key==='ArrowRight'||event.key==='ArrowDown'?1:-1)+radios.length)%radios.length;
  event.preventDefault();radios[next].click();
});
$('#review-player-list').addEventListener('input',event=>{
  if(event.target.dataset.reviewName!==undefined){const player=reviewDraft[Number(event.target.dataset.reviewName)];if(player)player.name=event.target.value;}
});
$('#review-bulk-level').addEventListener('change',event=>{
  const value=event.target.value;
  if(value==='clear'||levelOptions.some(([level])=>level===value)){
    reviewDraft.filter(player=>player.selected).forEach(player=>{player.rating=value==='clear'?null:Number(value);});
    renderReview();
  }
  event.target.value='noop';
});
$('#confirm-form').addEventListener('submit',event=>{event.preventDefault();if(confirmAction)mutate(confirmAction.action,{...confirmAction.data,...(confirmAction.action==='game'?{reason:$('#cancel-reason').value}:{})},$('#confirm-dialog'));});
window.addEventListener('popstate',()=>{searchTerm='';load(true);});
window.addEventListener('hashchange',()=>{searchTerm='';load(true);});
window.addEventListener('pageshow',event=>{if(event.persisted)load();});
let refreshTimer = setInterval(()=>{
  if(document.hidden||busy||swapConfirmation||$('dialog[open]')||['INPUT','SELECT','TEXTAREA'].includes(document.activeElement?.tagName))return;
  load();
},30000);
window.addEventListener('pagehide',()=>{clearReveals();clearInterval(refreshTimer);refreshTimer=null;});
window.addEventListener('pageshow',()=>{if(!refreshTimer)refreshTimer=setInterval(()=>{if(!document.hidden&&!busy&&!swapConfirmation&&!$('dialog[open]')&&!['INPUT','SELECT','TEXTAREA'].includes(document.activeElement?.tagName))load();},30000);});
load();
