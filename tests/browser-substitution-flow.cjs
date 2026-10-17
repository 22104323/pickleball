'use strict';
const assert=require('node:assert/strict');
const {chromium}=require(process.env.PICKLEQUEUE_PLAYWRIGHT_PATH||'playwright-core');
const base=process.argv[2]||'http://127.0.0.1:8083';
async function snapshot(page) {
  return page.evaluate(async()=>{const api=window.CourtsideBrowser;const {sessions}=await api.request('/api/sessions');return api.request(`/api/sessions/${sessions[0].id}`);});
}
async function mutate(page,action,data={}) {
  return page.evaluate(async({action,data})=>{const api=window.CourtsideBrowser;const {sessions}=await api.request('/api/sessions');const path=`/api/sessions/${sessions[0].id}`;const state=await api.request(path);return api.request(`${path}/${action}`,{revision:state.session.revision,...data});},{action,data});
}
async function create(page,count,courts=2) {
  const token=await page.evaluate(async({count,courts})=>{
    const api=window.CourtsideBrowser;
    let state=await api.request('/api/sessions',{name:'Substitution QA (synthetic)',court_count:courts,mode:'social_mix'});
    const path=`/api/sessions/${state.session.id}`;
    state=await api.request(`${path}/import-reviewed`,{revision:state.session.revision,source:'manual',club_key:'substitution-qa',players:Array.from({length:count},(_,i)=>({external_id:`qa-${i}`,name:`QA Player ${i+1}`,rating:1200})),pairs:[]});
    state=await api.request(`${path}/checkin-confirmed`,{revision:state.session.revision,id_rosters:state.players.map(p=>p.id)});
    state=await api.request(`${path}/start-session`,{revision:state.session.revision});
    return api.tokenFor(state.session.id);
  },{count,courts});
  await page.goto(`${base}/#link=${token}&view=queue`);
  await page.locator('.queue-panel').waitFor();
}
async function openSubstitution(page,id) {
  await page.locator(`[data-game-options="${id}"]`).click();
  assert.ok(await page.locator('#game-options-dialog').getByRole('button',{name:'Cancel game',exact:true}).isVisible());
  await page.getByRole('button',{name:'Substitute player',exact:true}).click();
  await page.locator('#substitute-dialog').waitFor();
}
async function shareCopy(browser,page) {
  const state=await snapshot(page);
  const url=await page.evaluate(id=>window.CourtsideBrowser.share(id),state.session.id);
  const context=await browser.newContext();const copy=await context.newPage();
  await copy.goto(url);await copy.locator('.queue-panel').waitFor();
  assert.deepEqual((await snapshot(copy)).games,state.games);
  await context.close();
  return url;
}
async function rejectTamperedSnapshots(browser,page) {
  const raw=await page.evaluate(()=>{
    const key=Object.keys(localStorage).find(key=>key.startsWith('courtside.browser-session.v1.'));
    return JSON.parse(localStorage.getItem(key));
  });
  const context=await browser.newContext();const target=await context.newPage();await target.goto(base);
  for(const kind of ['side','outside-roster','old-version','participation']) {
    await assert.rejects(()=>target.evaluate(async({raw,kind})=>{
      const game=raw.games.find(g=>g.substitutions?.length);
      if(kind==='side') game.substitutions[0].side=game.substitutions[0].side==='a'?'b':'a';
      if(kind==='outside-roster') game.substitutions[0].outgoing_id=99999;
      if(kind==='old-version') raw.version=1;
      if(kind==='participation') raw.players[0].games_played++;
      const bytes=new Uint8Array(await new Response(new Blob([JSON.stringify(raw)]).stream().pipeThrough(new CompressionStream('deflate'))).arrayBuffer());
      let binary='';for(const byte of bytes) binary+=String.fromCharCode(byte);
      const encoded=btoa(binary).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
      return window.CourtsideBrowser.open(raw.token,encoded);
    },{raw,kind}));
  }
  await context.close();
}

(async()=>{
  const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
  try {
    const page=await browser.newPage({viewport:{width:1440,height:1000}});
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    await page.goto(base);await create(page,17);
    let state=await snapshot(page);
    const game=state.games.find(g=>g.status==='playing');
    const outgoing=game.players[0];
    const waiting=state.players.filter(p=>p.queue_state==='waiting');
    const incoming=waiting[4];
    assert.ok(state.up_next[1].players.some(p=>p.id_roster===incoming.id));
    const nextTicket=state.session.next_ticket;
    const other=state.games.find(g=>g.id!==game.id&&g.status==='playing');
    await openSubstitution(page,game.id);
    assert.equal(await page.locator('#substitute-incoming').inputValue(),String(waiting[0].id));
    assert.match(await page.locator('#substitute-incoming option').first().textContent(),/Suggested.*Up Next 1/);
    await page.locator('#substitute-outgoing').selectOption(String(outgoing.id_roster));
    await page.locator('#substitute-incoming').selectOption(String(incoming.id));
    assert.match(await page.locator('#substitute-priority').textContent(),/skips 4 earlier/);
    if(process.env.PICKLEQUEUE_SCREENSHOTS) await page.screenshot({path:`${process.env.PICKLEQUEUE_SCREENSHOTS}/substitute-dialog-desktop.png`});
    await page.setViewportSize({width:390,height:844});
    assert.ok(await page.getByRole('button',{name:'Confirm substitution',exact:true}).isVisible());
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await page.waitForTimeout(300);
    if(process.env.PICKLEQUEUE_SCREENSHOTS) await page.screenshot({path:`${process.env.PICKLEQUEUE_SCREENSHOTS}/substitute-dialog-mobile.png`});
    const formBox=await page.locator('#substitute-dialog').boundingBox();
    assert.ok(formBox.width<=366&&formBox.x>=0&&formBox.x+formBox.width<=390);
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await page.getByRole('button',{name:'Confirm substitution',exact:true}).click();
    await page.locator('#substitute-dialog').waitFor({state:'hidden'});
    state=await snapshot(page);
    const changed=state.games.find(g=>g.id===game.id);
    const departed=state.players.find(p=>p.id===outgoing.id_roster);
    assert.equal(await page.locator('.court-card .substitution-history').count(),0);
    await page.locator(`[data-game-options="${game.id}"]`).click();
    await page.locator('#game-options-history').getByText('No individual wins, losses, or rating changes.',{exact:true}).waitFor();
    await page.locator('#game-options-dialog .close-dialog').click();
    await page.setViewportSize({width:390,height:844});
    await page.locator(`[data-game-options="${game.id}"]`).click();
    await page.waitForTimeout(300);
    const optionsBox=await page.locator('#game-options-dialog').boundingBox();
    assert.ok(optionsBox.width<=366&&optionsBox.x>=0&&optionsBox.x+optionsBox.width<=390);
    for(const label of ['Substitute player','Cancel game']) {
      const optionButton=page.locator('#game-options-dialog').getByRole('button',{name:label,exact:true});
      const box=await optionButton.boundingBox();assert.ok(box.height>=48&&box.width>=200);
    }
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    if(process.env.PICKLEQUEUE_SCREENSHOTS) await page.screenshot({path:`${process.env.PICKLEQUEUE_SCREENSHOTS}/game-options-mobile.png`});
    await page.locator('#game-options-dialog .close-dialog').click();
    await page.setViewportSize({width:1440,height:1000});
    assert.equal(changed.court,game.court);assert.equal(changed.started_at,game.started_at);
    assert.equal(changed.players.find(p=>p.id_roster===incoming.id).side,outgoing.side);
    assert.equal(changed.rating_eligible,false);
    assert.equal(departed.queue_state,'off');assert.equal(departed.attendance,'present');assert.equal(departed.ticket,nextTicket+1);
    assert.notEqual(departed.ticket,incoming.ticket);
    assert.deepEqual(state.games.find(g=>g.id===other.id),other);
    assert.ok(state.up_next.every(g=>g.players.every(p=>![incoming.id,outgoing.id_roster].includes(p.id_roster))));
    assert.ok(await page.locator(`[data-queue-player="${departed.id}"] .break-badge`).isVisible());
    await page.setViewportSize({width:1275,height:741});
    const cardBox=await page.locator(`[data-court="${game.court}"]`).boundingBox();
    const otherBox=await page.locator(`[data-court="${other.court}"]`).boundingBox();
    assert.equal(cardBox.height,otherBox.height);
    const winBox=await page.locator(`[data-court="${game.court}"] [data-winner]`).first().boundingBox();
    assert.ok(winBox.y+winBox.height<=cardBox.y+cardBox.height);
    if(process.env.PICKLEQUEUE_SCREENSHOTS) await page.screenshot({path:`${process.env.PICKLEQUEUE_SCREENSHOTS}/substitute-courts-desktop.png`});
    await page.reload();await page.locator(`[data-game-options="${game.id}"]`).waitFor();
    await shareCopy(browser,page);
    // Returning an original participant and substituting them back must count them once.
    await mutate(page,'player',{id_roster:departed.id,action:'resume'});
    await page.reload();await page.locator(`[data-game-options="${game.id}"]`).waitFor();
    await openSubstitution(page,game.id);
    await page.locator('#substitute-outgoing').selectOption(String(incoming.id));
    await page.locator('#substitute-incoming').selectOption(String(departed.id));
    assert.equal(await page.locator('#substitute-dialog select').count(),2);
    assert.equal(await page.locator('#substitute-dialog select').filter({has:page.locator('option[value="checkout"]')}).count(),0);
    await page.getByRole('button',{name:'Confirm substitution',exact:true}).click();
    await page.locator('#substitute-dialog').waitFor({state:'hidden'});
    const breakTicket=(await snapshot(page)).players.find(p=>p.id===incoming.id).ticket;
    await page.locator(`[data-court="${game.court}"] [data-winner][data-side="a"]`).click();
    await page.locator(`[data-game-options="${game.id}"]`).waitFor({state:'hidden'});
    state=await snapshot(page);
    const completed=state.games.find(g=>g.id===game.id);
    assert.equal(completed.status,'completed');assert.equal(completed.substitutions.length,2);
    const participants=new Set([...game.players.map(p=>p.id_roster),incoming.id]);
    for(const p of state.players) {
      assert.equal(p.games_played,Number(participants.has(p.id)));
      assert.equal(p.wins,0);assert.equal(p.losses,0);assert.equal(p.last_outcome,null);
    }
    const returnedToBreak=state.players.find(p=>p.id===incoming.id);
    assert.equal(returnedToBreak.attendance,'present');
    assert.equal(returnedToBreak.queue_state,'off');
    assert.equal(returnedToBreak.ticket,breakTicket);
    await page.setViewportSize({width:1275,height:741});
    await shareCopy(browser,page);
    await rejectTamperedSnapshots(browser,page);
    await page.getByRole('button',{name:'Game results',exact:true}).click();
    await page.locator(`[data-result-row="${game.id}"]`).getByText('No individual wins, losses, or rating changes.',{exact:true}).waitFor();
    for(const active of (await snapshot(page)).games.filter(g=>g.status==='playing')) await mutate(page,'game',{id_game:active.id,action:'cancel',reason:'Synthetic finalization'});
    // Checkout the remaining queue to prevent auto-start while cancelling the last court.
    while((await snapshot(page)).games.some(g=>g.status==='playing')) {
      for(const p of (await snapshot(page)).players.filter(p=>p.queue_state==='waiting')) await mutate(page,'player',{id_roster:p.id,action:'checkout'});
      for(const g of (await snapshot(page)).games.filter(g=>g.status==='playing')) await mutate(page,'game',{id_game:g.id,action:'cancel',reason:'Synthetic finalization'});
    }
    await mutate(page,'close');
    assert.ok((await snapshot(page)).players.every(p=>p.rating===1200&&p.rated_games===0));
    console.log('PASS: 17-player UI, Up Next override, break-only departure, court and side retention, reload/share, repeated substitution, participation-only results and ratings');

    await create(page,5,1);state=await snapshot(page);
    const active=state.games.find(g=>g.status==='playing');
    const substitute=state.players.find(p=>p.queue_state==='waiting');
    await openSubstitution(page,active.id);
    await page.locator('#substitute-outgoing').selectOption(String(active.players[0].id_roster));
    await mutate(page,'player',{id_roster:substitute.id,action:'pause'});
    const beforeStale=await snapshot(page);
    await page.getByRole('button',{name:'Confirm substitution',exact:true}).click();
    await page.locator('#substitute-dialog .form-error').getByText(/session changed/i).waitFor();
    assert.deepEqual((await snapshot(page)).games,beforeStale.games);
    await page.getByRole('button',{name:'Keep game unchanged',exact:true}).click();
    await openSubstitution(page,active.id);
    assert.ok(await page.locator('#substitute-submit').isDisabled());
    assert.match(await page.locator('#substitute-priority').textContent(),/No eligible replacement/);
    await page.getByRole('button',{name:'Keep game unchanged',exact:true}).click();
    const revision=(await snapshot(page)).session.revision;
    for(const invalid of [{disposition:'checkout'},{incoming_id:substitute.id},{incoming_id:active.players[1].id_roster},{incoming_id:active.players[0].id_roster},{incoming_id:9999},{incoming_id:true},{outgoing_id:substitute.id},{disposition:'swap'}]) {
      await assert.rejects(()=>mutate(page,'game',{id_game:active.id,action:'substitute',outgoing_id:active.players[0].id_roster,incoming_id:substitute.id,disposition:'break',...invalid}));
      assert.equal((await snapshot(page)).session.revision,revision);
    }
    await page.locator(`[data-game-options="${active.id}"]`).click();
    await page.locator('#game-options-dialog').getByRole('button',{name:'Cancel game',exact:true}).click();
    await page.locator('#confirm-dialog').getByRole('button',{name:'Cancel game',exact:true}).click();
    await page.locator('#confirm-dialog').waitFor({state:'hidden'});
    assert.equal((await snapshot(page)).games.find(g=>g.id===active.id).status,'cancelled');
    assert.deepEqual(errors,[]);
    console.log('PASS: stale-dialog rejection, unavailable replacements, no-candidate controls and Cancel game via Game options');
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
