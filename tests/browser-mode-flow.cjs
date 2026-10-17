'use strict';
const assert=require('node:assert/strict');
const {chromium}=require(process.env.PICKLEQUEUE_PLAYWRIGHT_PATH||'playwright-core');
const base=process.argv[2]||'http://127.0.0.1:8083';

async function snapshot(page) {
  return page.evaluate(async()=>{
    const api=window.CourtsideBrowser;
    const {sessions}=await api.request('/api/sessions');
    return api.request(`/api/sessions/${sessions[0].id}`);
  });
}

async function createSession(page) {
  const token=await page.evaluate(async()=>{
    const api=window.CourtsideBrowser;
    let state=await api.request('/api/sessions',{name:'Mode flow QA (synthetic)',court_count:4,mode:'balanced'});
    const path=`/api/sessions/${state.session.id}`;
    state=await api.request(`${path}/import-reviewed`,{
      revision:state.session.revision,source:'manual',club_key:'mode-flow-qa',
      players:Array.from({length:20},(_,i)=>({external_id:`qa-${i}`,name:`QA Player ${i+1}`,rating:1200})),pairs:[]
    });
    state=await api.request(`${path}/checkin-confirmed`,{revision:state.session.revision,id_rosters:state.players.map(player=>player.id)});
    state=await api.request(`${path}/start-session`,{revision:state.session.revision});
    return api.tokenFor(state.session.id);
  });
  await page.goto(`${base}/#link=${token}&view=queue`);
  await page.locator('.queue-panel').waitFor();
}

(async()=>{
  const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
  try {
    const page=await browser.newPage({viewport:{width:1440,height:900}});
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    await page.goto(base);await createSession(page);
    let before=await snapshot(page);
    assert.equal(before.games.filter(game=>game.status==='playing').length,4);
    assert.equal(before.up_next.length,1);
    assert.equal(await page.locator('[data-court]').count(),4);
    const layout=await page.evaluate(()=>{
      const content=document.querySelector('#view-content');
      const grid=document.querySelector('.courts');
      const cards=[...grid.querySelectorAll('.court-card')].map(card=>({top:card.getBoundingClientRect().top,bottom:card.getBoundingClientRect().bottom}));
      return {scrollable:content.scrollHeight>content.clientHeight,gridTop:grid.getBoundingClientRect().top,gridBottom:grid.getBoundingClientRect().bottom,cards};
    });
    assert.ok(layout.scrollable,'Four-court queue should scroll as one page section when needed.');
    assert.ok(layout.cards[2].top>layout.cards[0].top,'Courts 3 and 4 should render as a complete second row.');
    assert.ok(layout.cards.every(card=>card.bottom<=layout.gridBottom+1),'Court cards should not be clipped by an inner panel.');
    if(process.env.PICKLEQUEUE_SCREENSHOTS) await page.screenshot({path:`${process.env.PICKLEQUEUE_SCREENSHOTS}/four-courts-desktop.png`,fullPage:true});

    await page.getByRole('button',{name:/Change Mode/}).click();
    await page.locator('#mode-dialog').waitFor();
    await page.waitForTimeout(300);
    if(process.env.PICKLEQUEUE_SCREENSHOTS) await page.screenshot({path:`${process.env.PICKLEQUEUE_SCREENSHOTS}/mode-dialog-desktop.png`});
    assert.equal(await page.locator('#mode-picker .mode-option').count(),8);
    await page.locator('#mode-picker input[value="social_mix"]').check();
    assert.ok(await page.locator('#mode-picker input[value="social_mix"]').evaluate(input=>input.closest('.mode-option').classList.contains('selected')));
    await page.getByRole('button',{name:'Apply mode',exact:true}).click();
    await page.locator('#mode-dialog').waitFor({state:'hidden'});
    const after=await snapshot(page);
    assert.equal(after.session.mode,'social_mix');
    assert.deepEqual(after.games,before.games,'Changing mode must not change current or completed court games.');
    assert.deepEqual(after.players.map(player=>[player.id,player.ticket]),before.players.map(player=>[player.id,player.ticket]),'Queue tickets must be preserved.');
    assert.equal(after.session.next_ticket,before.session.next_ticket);
    assert.equal(after.games.filter(game=>game.status==='playing').length,4,'Changing mode must not auto-start or alter current matches.');
    assert.ok(after.up_next.every(game=>game.preview),'Future matches should be recalculated as previews.');
    assert.match(await page.getByRole('button',{name:/Change Mode/}).textContent(),/Social Mix/);

    await page.setViewportSize({width:390,height:844});
    await page.getByRole('button',{name:/Change Mode/}).click();
    const dialog=page.locator('#mode-dialog');
    await dialog.waitFor();
    await page.waitForTimeout(300);
    const bounds=await dialog.boundingBox();
    assert.ok(bounds.width<=366&&bounds.x>=0&&bounds.x+bounds.width<=390);
    assert.equal(await page.locator('#mode-picker .mode-option').count(),8);
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await page.mouse.move(0,0);
    if(process.env.PICKLEQUEUE_SCREENSHOTS) await page.screenshot({path:`${process.env.PICKLEQUEUE_SCREENSHOTS}/mode-dialog-mobile.png`});
    await dialog.getByRole('button',{name:'Cancel',exact:true}).click();
    await page.setViewportSize({width:320,height:740});
    await page.evaluate(()=>window.scrollTo(0,0));
    if(process.env.PICKLEQUEUE_SCREENSHOTS) await page.screenshot({path:`${process.env.PICKLEQUEUE_SCREENSHOTS}/narrow-phone-nav.png`});
    const nav=await page.evaluate(()=>{
      const button=document.querySelector('.side-navigation .nav-link');
      const badge=button.querySelector('.count');
      const buttonBox=button.getBoundingClientRect(),badgeBox=badge.getBoundingClientRect();
      return {columns:getComputedStyle(button.parentElement).gridTemplateColumns.split(' ').length,
        whiteSpace:getComputedStyle(button).whiteSpace,height:buttonBox.height,
        badgeCentered:Math.abs((buttonBox.top+buttonBox.bottom)/2-(badgeBox.top+badgeBox.bottom)/2)<2,
        pageWidth:document.documentElement.scrollWidth};
    });
    assert.equal(nav.columns,2);
    assert.equal(nav.whiteSpace,'nowrap');
    assert.ok(nav.height<=48&&nav.badgeCentered);
    assert.ok(nav.pageWidth<=320);
    assert.deepEqual(errors,[]);
    console.log('PASS: four-court layout, mode picker, narrow-phone navigation, queue-preserving replan, current games unchanged.');
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
