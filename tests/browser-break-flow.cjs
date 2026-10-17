'use strict';
const assert = require('node:assert/strict');
const {chromium} = require(process.env.PICKLEQUEUE_PLAYWRIGHT_PATH || 'playwright-core');
const base = process.argv[2] || 'http://127.0.0.1:8083';

async function snapshot(page) {
  return page.evaluate(async()=>{
    const api=window.CourtsideBrowser;
    const {sessions}=await api.request('/api/sessions');
    return api.request(`/api/sessions/${sessions[0].id}`);
  });
}
async function mutate(page,action,data={}) {
  return page.evaluate(async({action,data})=>{
    const api=window.CourtsideBrowser;
    const {sessions}=await api.request('/api/sessions');
    const path=`/api/sessions/${sessions[0].id}`;
    const current=await api.request(path);
    return api.request(`${path}/${action}`,{...data,revision:current.session.revision});
  },{action,data});
}
async function create(page,count,start=true) {
  const token=await page.evaluate(async({count,start})=>{
    const api=window.CourtsideBrowser;
    let state=await api.request('/api/sessions',{name:'Break flow (synthetic)',court_count:1,mode:'balanced'});
    const path=`/api/sessions/${state.session.id}`;
    state=await api.request(`${path}/import-reviewed`,{revision:state.session.revision,source:'manual',club_key:'break-regression',players:Array.from({length:count},(_,i)=>({external_id:`qa-${i}`,name:`QA Player ${i+1}`,rating:1200})),pairs:[]});
    state=await api.request(`${path}/checkin-confirmed`,{revision:state.session.revision,id_rosters:state.players.map(p=>p.id)});
    if(start) state=await api.request(`${path}/start-session`,{revision:state.session.revision});
    return api.tokenFor(state.session.id);
  },{count,start});
  await page.goto(`${base}/#link=${token}&view=${start?'queue':'setup'}`);
  await page.locator(start?'.queue-panel':'.setup-roster').waitFor();
  return token;
}

(async()=>{
  const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH || '/usr/bin/chromium',headless:true,args:['--no-sandbox']});
  try {
    const page=await browser.newPage({viewport:{width:1440,height:900}});
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(base);
    await create(page,12);
    let state=await snapshot(page);
    const player=state.players.find(p=>p.queue_state==='waiting');
    const ticket=player.ticket;
    const nextTicket=state.session.next_ticket;
    assert.ok(state.up_next.some(g=>g.players.some(p=>p.id_roster===player.id)));
    await page.locator(`.queue-entry [data-player="${player.id}"][data-player-action="pause"]`).click();
    const returnButton=page.locator(`.queue-entry.on-break [data-player="${player.id}"][data-player-action="resume"]`);
    await returnButton.waitFor();
    assert.equal(await page.locator('.break-panel').count(),0);
    await page.locator(`[data-queue-player="${player.id}"] [data-edit-name]`).click();
    await page.locator('#player-name').fill('  QA <Renamed> & Player  ');
    await page.getByRole('button',{name:'Save name',exact:true}).click();
    await page.locator('#rename-dialog').waitFor({state:'hidden'});
    const renamed=(await snapshot(page)).players.find(p=>p.id===player.id);
    assert.equal(renamed.name,'QA <Renamed> & Player');
    assert.equal(renamed.ticket,ticket);
    assert.equal(renamed.queue_state,'off');
    assert.equal((await snapshot(page)).session.next_ticket,nextTicket);
    assert.equal(await page.locator(`[data-queue-player="${player.id}"] strong`).textContent(),renamed.name);
    assert.equal(await page.locator('.queue-entry:not(.on-break) .queue-position').first().textContent(),'1');
    for (const [name,viewport] of [['desktop',{width:1440,height:900}],['mobile',{width:390,height:844}]]) {
      await page.setViewportSize(viewport);
      await returnButton.scrollIntoViewIfNeeded();
      assert.ok(await returnButton.isVisible());
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
      if(process.env.PICKLEQUEUE_SCREENSHOTS) await page.screenshot({path:`${process.env.PICKLEQUEUE_SCREENSHOTS}/break-${name}.png`});
    }
    await page.setViewportSize({width:1440,height:900});
    state=await snapshot(page);
    assert.equal(state.players.find(p=>p.id===player.id).ticket,ticket);
    assert.ok(state.up_next.every(g=>g.players.every(p=>p.id_roster!==player.id)));
    await mutate(page,'player',{id_roster:player.id,action:'eligibility',membership:'active',waiver:'valid'});
    assert.equal((await snapshot(page)).players.find(p=>p.id===player.id).queue_state,'off');
    const game=(await snapshot(page)).games.find(g=>g.status==='playing');
    await mutate(page,'game',{id_game:game.id,action:'complete',winner:'a'});
    state=await snapshot(page);
    assert.ok(state.games.filter(g=>g.status==='playing').every(g=>g.players.every(p=>p.id_roster!==player.id)));
    await page.reload();
    await returnButton.waitFor();
    const counter=state.session.next_ticket;
    await returnButton.click();
    await page.locator(`.queue-entry [data-player="${player.id}"][data-player-action="pause"]`).waitFor();
    state=await snapshot(page);
    const returned=state.players.find(p=>p.id===player.id);
    assert.equal(returned.ticket,ticket);
    assert.equal(returned.position,1);
    assert.ok(returned.wait_minutes<1);
    assert.equal(state.session.next_ticket,counter);
    assert.ok(counter>nextTicket);
    await page.getByRole('button',{name:'Players & check-in',exact:true}).click();
    const card=page.locator(`[data-player-card="${player.id}"]`);
    await card.getByRole('button',{name:'Take a break',exact:true}).click();
    await card.getByText('On break · place held',{exact:true}).waitFor();
    const shared=await page.evaluate(id=>window.CourtsideBrowser.share(id),state.session.id);
    const isolated=await browser.newContext();
    const copy=await isolated.newPage();
    await copy.goto(shared);
    await copy.locator(`.queue-entry.on-break [data-player="${player.id}"]`).waitFor();
    assert.equal((await snapshot(copy)).players.find(p=>p.id===player.id).ticket,ticket);
    await isolated.close();
    await card.getByRole('button',{name:'Return to queue',exact:true}).click();
    await card.getByRole('button',{name:'Take a break',exact:true}).waitFor();
    await card.getByRole('button',{name:'Take a break',exact:true}).click();
    await card.getByRole('button',{name:'Check out',exact:true}).click();
    await card.getByRole('button',{name:'Check in',exact:true}).click();
    await card.getByRole('button',{name:'Take a break',exact:true}).waitFor();
    assert.ok((await snapshot(page)).players.find(p=>p.id===player.id).ticket>counter);
    console.log('PASS: real queue/setup return controls, held priority, paused exclusion, reload, snapshot sharing, checkout');

    const renameContext=await browser.newContext();
    const renamePage=await renameContext.newPage();
    await renamePage.goto(base);
    await create(renamePage,4);
    let renameState=await snapshot(renamePage);
    const renamedActive=renameState.players.find(p=>p.queue_state==='playing');
    const beforeGames=renameState.games;
    await mutate(renamePage,'player',{id_roster:renamedActive.id,action:'rename',name:'QA Active renamed'});
    renameState=await snapshot(renamePage);
    assert.equal(renameState.games.length,beforeGames.length);
    assert.equal(renameState.games[0].players.find(p=>p.id_roster===renamedActive.id).name,'QA Active renamed');
    for(const name of [' ', 'x'.repeat(81)]) {
      await assert.rejects(()=>mutate(renamePage,'player',{id_roster:renamedActive.id,action:'rename',name}));
    }
    assert.equal((await snapshot(renamePage)).session.revision,renameState.session.revision);
    await mutate(renamePage,'game',{id_game:renameState.games[0].id,action:'cancel',reason:'Synthetic rename check'});
    const freeCourt=await snapshot(renamePage);
    assert.equal(freeCourt.players.filter(p=>p.queue_state==='waiting').length,4);
    await mutate(renamePage,'player',{id_roster:renamedActive.id,action:'rename',name:'QA Free court renamed'});
    const displayOnly=await snapshot(renamePage);
    assert.deepEqual(displayOnly.games.map(g=>[g.id,g.status]),freeCourt.games.map(g=>[g.id,g.status]));
    assert.equal(displayOnly.session.next_ticket,freeCourt.session.next_ticket);
    await renameContext.close();
    console.log('PASS: unified queue, pencil editing, escaped names, held priority, on-court names and invalid-name rollback');

    await create(page,5);
    state=await snapshot(page);
    const resting=state.players.find(p=>p.queue_state==='waiting');
    await mutate(page,'player',{id_roster:resting.id,action:'pause'});
    const active=state.games.find(g=>g.status==='playing');
    await mutate(page,'game',{id_game:active.id,action:'cancel'});
    assert.equal((await snapshot(page)).games.filter(g=>g.status==='playing').length,0);
    state=await mutate(page,'player',{id_roster:resting.id,action:'resume'});
    const playing=state.games.filter(g=>g.status==='playing');
    assert.equal(playing.length,1);
    assert.ok(playing[0].players.some(p=>p.id_roster===resting.id));
    assert.equal(new Set(playing.flatMap(g=>g.players.map(p=>p.id_roster))).size,4);
    await assert.rejects(()=>mutate(page,'player',{id_roster:resting.id,action:'pause'}),/Resolve the active court assignment first/);
    console.log('PASS: return automatically starts a valid match when a court is free; active game cannot be paused');

    const legacyToken=await create(page,4,false);
    state=await snapshot(page);
    const legacy=state.players[0];
    await mutate(page,'player',{id_roster:legacy.id,action:'pause'});
    await page.evaluate(({token,id})=>{
      const key=`courtside.browser-session.v1.${token}`;
      const record=JSON.parse(localStorage.getItem(key));
      record.players.find(p=>p.id===id).ticket=null;
      localStorage.setItem(key,JSON.stringify(record));
    },{token:legacyToken,id:legacy.id});
    state=await mutate(page,'player',{id_roster:legacy.id,action:'eligibility',membership:'active',waiver:'valid'});
    assert.equal(state.players.find(p=>p.id===legacy.id).queue_state,'off');
    state=await mutate(page,'player',{id_roster:legacy.id,action:'resume'});
    assert.equal(state.players.find(p=>p.id===legacy.id).ticket,5);
    await mutate(page,'player',{id_roster:legacy.id,action:'pause'});
    state=await mutate(page,'player',{id_roster:legacy.id,action:'eligibility',membership:'expired',waiver:'valid'});
    assert.equal(state.players.find(p=>p.id===legacy.id).ticket,null);
    state=await mutate(page,'player',{id_roster:legacy.id,action:'eligibility',membership:'active',waiver:'valid'});
    assert.equal(state.players.find(p=>p.id===legacy.id).ticket,6);
    console.log('PASS: legacy breaks without a ticket and lost eligibility return at the back');
    await page.reload();
    await page.locator('[data-player-card]').first().waitFor();
    for(const p of state.players) await mutate(page,'player',{id_roster:p.id,action:'pause'});
    await page.reload();
    await mutate(page,'close');
    await page.reload();
    assert.equal(await page.locator('.queue-entry.on-break').count(),0);
    assert.equal(await page.getByText('On break',{exact:true}).count(),0);
    console.log('PASS: closed sessions do not label players as taking a break');
    assert.deepEqual(errors,[]);
    console.log('Browser break-flow regression passed. Synthetic browser storage only.');
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
