'use strict';

// Hosted sessions run on the user's device; the Python engine still serves local use.
(() => {
  const PREFIX = 'courtside.browser-session.v1.';
  const LIFETIME = 48 * 60 * 60;
  const MODES = ['balanced','social_mix','skill_separated','winners_losers','skill_courts','mixed_doubles','king_queen','club_wars'];
  const ACTIVE = ['assigned','playing'];
  const now = () => Date.now() / 1000;
  const eligible = player => player.membership === 'active' && player.waiver === 'valid';
  const band = rating => rating < 1100 ? 'Beginner' : rating < 1450 ? 'Intermediate' : rating < 1750 ? 'Advanced' : 'Competitive';
  const pairKey = (a,b) => [a,b].sort((x,y)=>x-y).join(':');
  let currentToken = null;

  function fail(message,status=400) {
    const error = new Error(message);
    error.status = status;
    throw error;
  }

  function integer(value,label,min,max) {
    if (!Number.isSafeInteger(value) || value < min || value > max) fail(`${label} must be an integer from ${min} to ${max}.`);
    return value;
  }

  function text(value,label,limit=120) {
    if (typeof value !== 'string' || !value.trim() || value.length > limit || /[\x00-\x1f]/.test(value)) fail(`${label} is required and must be at most ${limit} printable characters.`);
    return value.trim();
  }

  function audit(record,action,detail={}) {
    record.audit.unshift({id:record.next_audit++,action,detail:JSON.stringify(detail),created_at:now()});
    record.audit = record.audit.slice(0,30);
  }

  function read(token) {
    if (!/^[a-f0-9-]{36}$/.test(token || '')) return null;
    const raw = localStorage.getItem(PREFIX + token);
    if (!raw) return null;
    let record;
    try { record = JSON.parse(raw); } catch { fail('This browser session could not be read. Generate a new link.'); }
    if (![1,2].includes(record.version) || record.token !== token || !Number.isFinite(record.expires_at)) fail('This session uses an unsupported format.');
    if (record.expires_at <= now()) {
      localStorage.removeItem(PREFIX + token);
      fail('This session link has expired after 48 hours. Generate a new link.',410);
    }
    return record;
  }

  function save(record) {
    try { localStorage.setItem(PREFIX + record.token,JSON.stringify(record)); }
    catch { fail('This browser could not save the session. Free some browser storage and try again.'); }
  }

  function purgeExpired() {
    const keys=Object.keys(localStorage).filter(key=>key.startsWith(PREFIX));
    for (const key of keys) {
      let record;
      try { record=JSON.parse(localStorage.getItem(key)); } catch { continue; }
      if (Number.isFinite(record?.expires_at)&&record.expires_at<=now()) localStorage.removeItem(key);
    }
  }

  function create(data) {
    purgeExpired();
    const name = text(data.name,'Session name');
    const court_count = integer(data.court_count ?? 2,'Courts',1,8);
    const max_players = integer(data.max_players ?? 30,'Capacity',4,200);
    const mode = data.mode ?? 'balanced';
    if (!MODES.includes(mode)) fail('Choose a supported play mode.');
    const starts_at = data.starts_at ?? now();
    if (!Number.isFinite(starts_at) || starts_at <= 0 || starts_at >= 4102444800) fail('Choose a valid start time before 2100.');
    const created_at = now();
    const token = crypto.randomUUID();
    const record = {version:1,token,expires_at:created_at+LIFETIME,
      session:{id:Date.now(),name,starts_at,court_count,max_players,mode,status:'active',revision:0,next_ticket:0,created_at},
      players:[],games:[],audit:[],next_player:1,next_game:1,next_audit:1};
    audit(record,'session.created',{court_count,max_players});
    save(record);
    currentToken = token;
    return snapshot(record);
  }

  function upcoming(record) {
    const waiting=record.players.filter(p=>p.queue_state==='waiting'&&eligible(p));
    const matches=[];
    if(record.session.status==='active'&&record.games.length&&waiting.length>=4) {
      const preview=structuredClone(record);
      const playing=record.games.filter(g=>g.status==='playing').sort((a,b)=>a.started_at-b.started_at||a.court-b.court);
      const courts=[...playing.map(g=>g.court),...Array.from({length:record.session.court_count},(_,i)=>i+1).filter(court=>!playing.some(g=>g.court===court))];
      let progress=true;
      while(progress&&matches.length<Math.floor(waiting.length/4)) {
        progress=false;
        for(const court of courts) {
          preview.games=preview.games.filter(g=>g.court!==court||!ACTIVE.includes(g.status));
          fill(preview,[court]);
          const game=preview.games.find(g=>g.status==='assigned'&&g.court===court);
          if(game) {
            matches.push({...structuredClone(game),preview:true,turn:matches.length+1});
            game.status='playing';
            progress=true;
          }
        }
      }
    }
    const planned=new Set(matches.flatMap(g=>g.players.map(p=>p.id_roster)));
    return {matches,waiting:waiting.filter(p=>!planned.has(p.id)).map(p=>p.id)};
  }

  function ratedGame(game) { return !(game.substitutions||[]).some(change=>change.during_play); }
  function participants(game) {
    return [...new Set([...game.players.map(p=>p.id_roster),...(game.substitutions||[]).filter(change=>change.during_play).map(change=>change.outgoing_id)])];
  }

  function snapshot(record) {
    const output = structuredClone(record);
    const planned=upcoming(record);
    output.up_next=planned.matches;
    const wins = new Map(), losses = new Map(), latest = new Map();
    const completed = output.games.filter(game=>game.status==='completed').sort((a,b)=>b.id-a.id);
    for (const game of completed.filter(ratedGame)) for (const player of game.players) {
      const won = (game.score_a > game.score_b) === (player.side === 'a');
      wins.set(player.id_roster,(wins.get(player.id_roster)||0)+Number(won));
      losses.set(player.id_roster,(losses.get(player.id_roster)||0)+Number(!won));
      if (!latest.has(player.id_roster)) latest.set(player.id_roster,won?'winner':'loser');
    }
    output.players.sort((a,b)=>(a.ticket ?? Infinity)-(b.ticket ?? Infinity)||a.id-b.id);
    let position = 0;
    for (const player of output.players) {
      player.position = player.queue_state==='waiting' ? ++position : null;
      player.wait_minutes = player.queued_at ? Math.max(0,(now()-player.queued_at)/60) : 0;
      player.eligible = eligible(player);
      player.provisional = player.rated_games < 10;
      player.band = band(player.rating);
      player.wins = wins.get(player.id)||0;
      player.losses = losses.get(player.id)||0;
      player.last_outcome = latest.get(player.id)||null;
      const partner = output.players.find(other=>other.id===player.paired_roster_id);
      player.partner_name = partner?.name || null;
    }
    output.games.sort((a,b)=>b.id-a.id);
    for (const game of output.games) {
      game.rating_eligible=ratedGame(game);
      game.substitutions=(game.substitutions||[]).map(change=>({...change,
        outgoing_name:output.players.find(p=>p.id===change.outgoing_id)?.name||'Player',
        incoming_name:output.players.find(p=>p.id===change.incoming_id)?.name||'Player'}));
      for (const gp of game.players) gp.name=output.players.find(player=>player.id===gp.id_roster)?.name||'Player';
    }
    const standings = output.players.map(({id,name,wins,losses,games_played})=>({id,name,wins,losses,games_played}));
    standings.sort((a,b)=>b.wins-a.wins||Number(a.games_played===0)-Number(b.games_played===0)||a.losses-b.losses||a.name.toLowerCase().localeCompare(b.name.toLowerCase())||a.id-b.id);
    const metrics = {present:output.players.filter(p=>p.attendance==='present').length,waiting:position,
      on_court:output.players.filter(p=>ACTIVE.includes(p.queue_state)).length,completed_games:completed.length,
      no_shows:output.players.filter(p=>p.attendance==='no_show').length,late:output.players.reduce((n,p)=>n+p.is_late,0),
      stomp_rate:completed.length?completed.filter(g=>g.expected_a<.35||g.expected_a>.65).length/completed.length:null};
    return {session:output.session,players:output.players,games:output.games,up_next:output.up_next,up_next_waiting:planned.waiting,audit:output.audit,standings,metrics,expires_at:record.expires_at};
  }

  function enqueue(record,player) {
    player.ticket = ++record.session.next_ticket;
    player.queued_at = now();
    player.queue_state = 'waiting';
  }

  function off(player) {
    player.queue_state = 'off';
    player.ticket = null;
    player.queued_at = null;
  }

  function rejoin(record,player) {
    if (player.ticket===null) enqueue(record,player);
    else {
      player.queue_state='waiting';
      player.queued_at=now();
    }
  }

  function pause(player) {
    if (player.queue_state!=='waiting') fail('Player is not waiting in the queue.',409);
    player.queue_state='off';
    player.queued_at=null;
  }

  function getPlayer(record,id) {
    const player = record.players.find(p=>p.id===id);
    if (!player) fail('Player not found.',404);
    return player;
  }

  function available(player) {
    if (ACTIVE.includes(player.queue_state)) fail('Resolve the active court assignment first.',409);
  }

  function checkin(record,player) {
    available(player);
    if (player.attendance==='present') fail('Player is already checked in.',409);
    if (record.players.filter(p=>p.attendance==='present').length>=record.session.max_players) fail('Session capacity is full.',409);
    player.attendance = 'present';
    player.checked_in_at = now();
    player.checked_out_at = null;
    player.is_late = Number(now()>record.session.starts_at+15*60);
    if (eligible(player)) enqueue(record,player);
  }

  function playerAction(record,data) {
    const player = getPlayer(record,data.id_roster);
    if (data.action==='checkin') checkin(record,player);
    else if (data.action==='rename') player.name=text(data.name,'Player name',80);
    else {
      available(player);
      if (data.action==='eligibility') {
        if (!['active','expired','unknown'].includes(data.membership)||!['valid','missing','unknown'].includes(data.waiver)) fail('Choose valid membership and waiver states.');
        const wasEligible=eligible(player);
        player.membership = data.membership;
        player.waiver = data.waiver;
        if (!eligible(player)) off(player);
        else if (player.attendance==='present'&&player.queue_state==='off'&&!wasEligible) enqueue(record,player);
      } else if (data.action==='rating') {
        if (record.games.length) fail('Set initial skills before preparing the first game.',409);
        const rating=Number(data.rating);
        if (!Number.isFinite(rating)||rating<0||rating>4000) fail('Ratings must be from 0 to 4000.');
        player.rating=rating;player.base_rating=rating;
      } else if (data.action==='remove') {
        if (record.games.length) fail('Remove players before preparing the first game; use check-out during play.',409);
        if (player.paired_roster_id) getPlayer(record,player.paired_roster_id).paired_roster_id=null;
        record.players=record.players.filter(p=>p.id!==player.id);
      } else if (data.action==='resume') {
        if (player.attendance!=='present'||!eligible(player)) fail('Player must be present and eligible.');
        if (player.queue_state==='waiting') fail('Player is already queued.',409);
        rejoin(record,player);
      } else if (['pause','checkout'].includes(data.action)) {
        if (data.action==='checkout') {
          if (player.attendance!=='present') fail('Player is not checked in.',409);
          player.attendance='left'; player.checked_out_at=now();
          off(player);
        } else {
          pause(player);
        }
      } else fail('Unknown player action.');
    }
    audit(record,`player.${data.action}`,{id_roster:player.id});
  }

  function pairPlayers(record,idA,idB,unchanged=false) {
    if (!Number.isSafeInteger(idA)||!Number.isSafeInteger(idB)||idA===idB) fail('Choose two different players to pair.');
    const a=getPlayer(record,idA), b=getPlayer(record,idB);
    if (unchanged&&a.paired_roster_id===b.id&&b.paired_roster_id===a.id) return;
    available(a); available(b);
    if (a.paired_roster_id||b.paired_roster_id) fail('Unpair the selected players before choosing another partner.',409);
    a.paired_roster_id=b.id; b.paired_roster_id=a.id;
  }

  function importPlayers(record,data,demo=false) {
    if (!Array.isArray(data.players)||data.players.length<1||data.players.length>200) fail('Review between 1 and 200 players.');
    if (!demo&&!['manual','reclub'].includes(data.source)) fail('Choose manual or Reclub players.');
    if (demo&&record.players.length) fail('Load demo players into an empty session only.',409);
    if (!demo&&record.players.some(p=>p.source==='demo')) fail('Create a new session for your own roster; demo players cannot be mixed with it.',409);
    const clubKey=text(data.club_key,'Club identifier');
    const selected=new Map();
    for (const value of data.players) {
      if (!value||typeof value!=='object'||Array.isArray(value)) fail('Each player must be an object.');
      const external=text(value.external_id,'Player ID');
      if (selected.has(external)) fail('Every reviewed player needs a unique ID.');
      const name=text(value.name,'Player name',80);
      const rating=value.rating ?? 1200;
      if (!Number.isFinite(rating)||rating<0||rating>4000) fail('Ratings must be from 0 to 4000.');
      const gender=value.gender||null;
      if (gender!==null&&!['M','F'].includes(gender)) fail('Choose M, F, or no category.');
      const group=value.club_group ? text(value.club_group,'Club group',40) : null;
      let player=record.players.find(p=>p.external_id===external&&p.source===data.source&&p.club_key===clubKey);
      if (player) {
        if (ACTIVE.includes(player.queue_state)&&((gender&&gender!==player.gender)||(group&&group!==player.club_group))) fail('Resolve the active game before changing player categories or groups.',409);
        player.name=name; player.rsvp='yes';
        if (gender) player.gender=gender;
        if (group) player.club_group=group;
      } else {
        if (record.players.length>=200) fail('A browser session supports at most 200 roster entries.');
        const id=record.next_player++;
        player={id,id_member:id,id_session:record.session.id,name,external_id:external,source:data.source,club_key:clubKey,gender,club_group:group,
          rating,deviation:350,volatility:.06,rated_games:0,base_rating:rating,base_deviation:350,base_volatility:.06,
          rsvp:'yes',attendance:'absent',membership:demo?'active':'unknown',waiver:demo?'valid':'unknown',queue_state:'off',
          checked_in_at:null,checked_out_at:null,is_late:0,ticket:null,queued_at:null,games_played:0,paired_roster_id:null};
        record.players.push(player);
      }
      selected.set(external,player.id);
    }
    const pairs=data.pairs ?? [];
    if (!Array.isArray(pairs)||pairs.length>100) fail('Invalid player pair list.');
    const paired=new Set();
    for (const pair of pairs) {
      if (!Array.isArray(pair)||pair.length!==2||pair[0]===pair[1]||!selected.has(pair[0])||!selected.has(pair[1])) fail('Every pair needs two different selected players.');
      if (pair.some(id=>paired.has(id))) fail('A player can have only one partner.');
      pair.forEach(id=>paired.add(id));
      pairPlayers(record,selected.get(pair[0]),selected.get(pair[1]),true);
    }
    audit(record,demo?'roster.imported':'roster.reviewed_imported',{source:data.source,rows:data.players.length,pairs:pairs.length});
    return `Added ${data.players.length} players to Not Yet Here. Check them in when they arrive.`;
  }

  function history(record) {
    const partners=new Map(),opponents=new Map();
    for (const game of record.games.filter(g=>g.status==='completed'&&ratedGame(g)).slice(-10)) {
      for (let i=0;i<game.players.length;i++) for (let j=i+1;j<game.players.length;j++) {
        const a=game.players[i],b=game.players[j],counts=a.side===b.side?partners:opponents;
        const key=pairKey(a.id_roster,b.id_roster);
        counts.set(key,(counts.get(key)||0)+1);
      }
    }
    return {partners,opponents};
  }

  function compareKeys(a,b) {
    for (let i=0;i<a.length;i++) if (a[i]!==b[i]) return a[i]-b[i];
    return 0;
  }

  function teamsKey(teams) {
    return teams.map(team=>team.map(p=>p.id).sort((a,b)=>a-b).join(':')).sort().join('|');
  }

  function choose(players,counts,mode,excluded=null,preferred=null) {
    if (players.length<4) return null;
    const ordered=[...players].sort((a,b)=>a.ticket-b.ticket||a.id-b.id), anchor=ordered[0];
    const positions=new Map(ordered.map((p,i)=>[p.id,i]));
    for (const size of [...new Set([Math.min(12,ordered.length),Math.min(16,ordered.length)])]) {
      const ids=new Set(ordered.slice(0,size).map(p=>p.id));
      for (const p of ordered.slice(0,size)) if (p.paired_roster_id) ids.add(p.paired_roster_id);
      const pool=ordered.filter(p=>ids.has(p.id));
      let best=null;
      for (let i=1;i<pool.length-2;i++) for (let j=i+1;j<pool.length-1;j++) for (let k=j+1;k<pool.length;k++) {
        const quartet=[anchor,pool[i],pool[j],pool[k]];
        if(Array.isArray(excluded)&&quartet.every(p=>excluded.includes(p.id))) continue;
        if (quartet.some(p=>p.paired_roster_id&&!quartet.some(q=>q.id===p.paired_roster_id))) continue;
        for (let partner=1;partner<4;partner++) {
          const a=[anchor,quartet[partner]],b=quartet.filter((_,i)=>i!==0&&i!==partner),teams=[a,b];
          if (teams.some(team=>team.some(p=>p.paired_roster_id&&!team.some(q=>q.id===p.paired_roster_id)))) continue;
          if (mode==='mixed_doubles'&&teams.some(team=>team.map(p=>p.gender).sort().join('')!=='FM')) continue;
          if (mode==='club_wars'&&(!a[0].club_group||!b[0].club_group||a[0].club_group!==a[1].club_group||b[0].club_group!==b[1].club_group||a[0].club_group===b[0].club_group)) continue;
          if (excluded===teamsKey(teams)) continue;
          const mean_a=(a[0].rating+a[1].rating)/2,mean_b=(b[0].rating+b[1].rating)/2;
          const delta=Math.abs(mean_a-mean_b),expected=1/(1+10**((mean_b-mean_a)/400));
          if (mode!=='social_mix'&&(delta>150||expected<.4||expected>.6)) continue;
          const partnerRepeats=teams.reduce((n,t)=>n+(counts.partners.get(pairKey(t[0].id,t[1].id))||0),0);
          const opponentRepeats=a.reduce((n,x)=>n+b.reduce((m,y)=>m+(counts.opponents.get(pairKey(x.id,y.id))||0),0),0);
          const gap=(Math.abs(a[0].rating-a[1].rating)+Math.abs(b[0].rating-b[1].rating))/2;
          const base=mode==='social_mix'?8*partnerRepeats+2*opponentRepeats:8*delta/75+4*gap/350+3*partnerRepeats+2*opponentRepeats;
          const cost=base+quartet.reduce((n,p)=>n+positions.get(p.id),0)-6-quartet.filter(p=>p.games_played===0&&(mode==='social_mix'||p.rated_games<10)).length/2;
          const key=[cost,...(mode==='social_mix'?[partnerRepeats,opponentRepeats]:[delta]),...a.map(p=>p.id),...b.map(p=>p.id)];
          if(preferred===teamsKey(teams)) return {teams,key,cost,mean_a,mean_b,expected_a:mode==='social_mix'?.5:expected};
          if (!best||compareKeys(key,best.key)<0) best={teams,key,cost,mean_a,mean_b,expected_a:mode==='social_mix'?.5:expected};
        }
      }
      if (best) return best;
    }
    return null;
  }

  function fill(record,courts=null,rebuild=null,excluded=null,preferred=null) {
    const s=record.session, mode=s.mode, counts=history(record),messages=[],assigned=[];
    const active=record.games.filter(g=>ACTIVE.includes(g.status));
    if (!rebuild&&mode==='social_mix'&&active.some(g=>g.status==='assigned')) return 'Social Mix: start the planned match before building the next mix.';
    const outcomes=new Map(),lastCourts=new Map();
    for (const game of record.games.filter(g=>g.status==='completed'&&ratedGame(g)).sort((a,b)=>b.id-a.id)) for (const gp of game.players) {
      if (!outcomes.has(gp.id_roster)) {
        outcomes.set(gp.id_roster,(game.score_a>game.score_b)===(gp.side==='a')?'winner':'loser');
        lastCourts.set(gp.id_roster,game.court);
      }
    }
    const usedBands=new Set(active.filter(g=>g.id!==rebuild?.id).flatMap(g=>{
      const bands=new Set(g.players.map(gp=>band(getPlayer(record,gp.id_roster).rating)));
      return bands.size===1?[...bands]:[];
    }));
    for (const court of courts||Array.from({length:s.court_count},(_,i)=>i+1)) {
      if (!rebuild&&active.some(g=>g.court===court)) continue;
      const players=record.players.filter(p=>p.attendance==='present'&&p.queue_state==='waiting'&&eligible(p)).sort((a,b)=>a.ticket-b.ticket||a.id-b.id);
      let pools=[],chosenBand=null;
      if (['skill_separated','skill_courts'].includes(mode)) {
        const bands=['Beginner','Intermediate','Advanced','Competitive'];
        const byBand=new Map(bands.map(b=>[b,players.filter(p=>band(p.rating)===b)]));
        if (mode==='skill_separated') chosenBand=players[0]?band(players[0].rating):null;
        else {
          const available=bands.filter(b=>byBand.get(b).length>=4),unused=available.filter(b=>!usedBands.has(b));
          chosenBand=(unused.length?unused:available).sort((a,b)=>byBand.get(b).length-byBand.get(a).length)[0]||null;
        }
        pools=[[byBand.get(chosenBand)||[],'balanced']];
      } else if (mode==='winners_losers') {
        const anchorOutcome=outcomes.get(players[0]?.id),neutral=players.filter(p=>!outcomes.has(p.id));
        const results=anchorOutcome?[anchorOutcome]:outcomes.size?['winner','loser']:['neutral'];
        pools=results.map(result=>[[...players.filter(p=>outcomes.get(p.id)===result),...neutral],'balanced']);
      } else if (mode==='king_queen') {
        const targeted=players.filter(p=>outcomes.has(p.id)&&(outcomes.get(p.id)==='winner'?Math.max(1,lastCourts.get(p.id)-1):Math.min(s.court_count,lastCourts.get(p.id)+1))===court);
        const neutral=players.filter(p=>!outcomes.has(p.id));
        pools=[[[...targeted,...neutral],'balanced']];
      } else if (mode==='club_wars') {
        const group=players[0]?.club_group;
        pools=[...new Set(players.map(p=>p.club_group).filter(Boolean))].filter(g=>g!==group&&group).sort().map(g=>[players.filter(p=>p.club_group===group||p.club_group===g),'club_wars']);
      } else pools=[[players,mode]];
      const preferredIds=new Set(preferred?.players.map(p=>p.id_roster)||[]);
      const preferredTeams=preferred?teamsKey(['a','b'].map(side=>preferred.players.filter(p=>p.side===side).map(p=>({id:p.id_roster})))):null;
      const announced=pools.map(([pool,objective])=>choose(pool.filter(p=>preferredIds.has(p.id)),counts,objective,excluded,preferredTeams)).find(Boolean);
      const matches=announced?[announced]:pools.map(([pool,objective])=>choose(pool,counts,objective,excluded)).filter(Boolean).sort((a,b)=>compareKeys(a.key,b.key));
      const match=matches[0];
      if (!match) {
        const detail=players.length<4?'need four eligible players':({skill_separated:'need four eligible players in the same skill band',skill_courts:'need four eligible players in the same skill band',winners_losers:'need four available players from a winners or losers group',king_queen:'need four players at this court level',mixed_doubles:'need one self-identified man and woman on each team',club_wars:'need valid group assignments and partner preferences'})[mode]||'no balanced split can include the oldest waiting player';
        messages.push(`Court ${court}: ${detail}.`);
        break;
      }
      const game=rebuild||{id:record.next_game++,id_session:s.id,court,status:'assigned',started_at:null,completed_at:null,score_a:null,score_b:null};
      Object.assign(game,{assigned_at:now(),mean_a:match.mean_a,mean_b:match.mean_b,expected_a:match.expected_a,cost:match.cost,
        reason:({social_mix:'Social Mix: rotates partners first and avoids recent opponent repeats; ratings are not used.',skill_separated:`Skill Separated: ${chosenBand} players only.`,skill_courts:`Skill Courts: ${chosenBand} group.`,winners_losers:'Winners / Losers: same recent-result group, with newcomers allowed to join.',king_queen:`King/Queen: court ${court} promotion and demotion rotation.`,mixed_doubles:'Mixed Doubles: one self-identified man and woman on each team.',club_wars:'Club Wars: each team represents one player group.'})[mode]||'Oldest waiting player included; balanced teams and recent pairing history.',players:[]});
      for (let side=0;side<2;side++) for (const player of match.teams[side]) {
        player.queue_state='assigned';
        game.players.push({id_game:game.id,id_roster:player.id,side:side===0?'a':'b',name:player.name,gender:player.gender,rating:player.rating,deviation:player.deviation,volatility:player.volatility});
      }
      if (!rebuild) record.games.push(game);
      assigned.push(game.id);
      if (chosenBand) usedBands.add(chosenBand);
      if (mode==='social_mix') break;
    }
    if (rebuild&&!assigned.length) fail('No alternative valid matchup available. The existing Up Next plan was kept.',409);
    if (assigned.length&&!rebuild) audit(record,'courts.assigned',{games:assigned});
    return `Assigned ${assigned.length} court(s). ${messages.join(' ')}`;
  }

  function advanceCourts(record,planned=[],excluded=null) {
    for(const game of record.games.filter(g=>g.status==='assigned')) gameAction(record,{id_game:game.id,action:'start'});
    let started=0;
    for(let court=1;court<=record.session.court_count;court++) {
      if(record.games.some(g=>g.court===court&&ACTIVE.includes(g.status))) continue;
      const preferred=planned.find(game=>(record.session.mode!=='king_queen'||game.court===court)&&game.players.every(gp=>record.players.some(p=>p.id===gp.id_roster&&p.queue_state==='waiting'&&eligible(p))));
      fill(record,[court],null,excluded,preferred);
      const game=record.games.find(g=>g.court===court&&g.status==='assigned');
      if(game) {gameAction(record,{id_game:game.id,action:'start'});started++;}
    }
    return started;
  }

  function gameAction(record,data) {
    const game=record.games.find(g=>g.id===data.id_game);
    if (!game) fail('Game not found.',404);
    const players=game.players.map(gp=>getPlayer(record,gp.id_roster)).sort((a,b)=>a.ticket-b.ticket||a.id-b.id);
    const action=data.action;
    if (action==='start') {
      if (game.status!=='assigned') fail('Only assigned games can start.',409);
      if (players.length!==4||players.some(p=>p.attendance!=='present'||!eligible(p))) fail('Four present, eligible players are required.',409);
      game.status='playing'; game.started_at=now(); players.forEach(p=>p.queue_state='playing');
    } else if (action==='complete') {
      if (game.status!=='playing') fail('Start the game before recording its result.',409);
      let scoreA,scoreB;
      if (Object.hasOwn(data,'winner')) {
        if (!['a','b'].includes(data.winner)) fail('Choose Team 1 or Team 2 as the winner.');
        if (Object.hasOwn(data,'score_a')||Object.hasOwn(data,'score_b')) fail('Submit a winner or scores, not both.');
        [scoreA,scoreB]=data.winner==='a'?[1,0]:[0,1];
      } else { scoreA=integer(data.score_a,'Team A score',0,99); scoreB=integer(data.score_b,'Team B score',0,99); }
      if (scoreA===scoreB) fail('A completed game needs a winner.');
      Object.assign(game,{status:'completed',score_a:scoreA,score_b:scoreB,completed_at:now()});
      for (const id of participants(game)) getPlayer(record,id).games_played++;
      for (const p of players) { if (p.attendance==='present'&&eligible(p)) enqueue(record,p); else off(p); }
    } else if (action==='substitute') {
      if (!ACTIVE.includes(game.status)) fail('Only an active game can have a substitute.',409);
      const outgoing=getPlayer(record,data.outgoing_id),incoming=getPlayer(record,data.incoming_id);
      const slot=game.players.find(gp=>gp.id_roster===outgoing.id);
      if (!slot||outgoing.id===incoming.id) fail('Choose a current player and a different replacement.');
      if (incoming.attendance!=='present'||!eligible(incoming)||!['waiting','assigned'].includes(incoming.queue_state)) fail('The replacement must be present, eligible, and in the queue.',409);
      if (data.disposition!=='break') fail('A substitute always sends the departing player on a break.')
      if ((game.substitutions||[]).length>=200) fail('This game has reached its substitution limit.',409);
      const reserved=record.games.find(g=>g.status==='assigned'&&g.id!==game.id&&g.players.some(p=>p.id_roster===incoming.id));
      if (incoming.queue_state==='assigned'&&!reserved) fail('The replacement is no longer available.',409);
      if (reserved) {
        reserved.status='cancelled';reserved.completed_at=now();
        reserved.players.forEach(gp=>getPlayer(record,gp.id_roster).queue_state='waiting');
        audit(record,'game.preview_released',{id_game:reserved.id,for_substitution:game.id});
      }
      const during_play=game.status==='playing';
      (game.substitutions??=[]).push({outgoing_id:outgoing.id,incoming_id:incoming.id,side:slot.side,during_play,at:now(),disposition:data.disposition});
      Object.assign(slot,{id_roster:incoming.id,name:incoming.name,gender:incoming.gender,rating:incoming.rating,deviation:incoming.deviation,volatility:incoming.volatility});
      const means=['a','b'].map(side=>game.players.filter(p=>p.side===side).reduce((sum,p)=>sum+p.rating,0)/2);
      Object.assign(game,{mean_a:means[0],mean_b:means[1],expected_a:record.session.mode==='social_mix'?.5:1/(1+10**((means[1]-means[0])/400)),cost:0,reason:'Manual lineup change by organizer.'});
      incoming.queue_state=game.status;
      if(during_play) enqueue(record,outgoing);
      outgoing.queue_state='off';outgoing.queued_at=null;
      record.version=2;
      audit(record,'game.substituted',{id_game:game.id,outgoing_id:outgoing.id,incoming_id:incoming.id,disposition:data.disposition});
      return during_play?'Player substituted. This game counts participation only; no individual wins, losses, or rating changes.':'Player replaced before play. The game remains rated.';
    } else if (action==='swap_winner') {
      if (game.status!=='completed') fail('Only completed games have a winner to correct.',409);
      [game.score_a,game.score_b]=[game.score_b,game.score_a];
      audit(record,'game.winner_swapped',{id_game:game.id});
      return 'Winner corrected. Games played and Up Next teams are unchanged.';
    } else if (action==='rebuild') {
      if (game.status!=='assigned') fail('Only an unstarted Up Next game can be rebuilt.',409);
      if (game.substitutions?.length) fail('Cancel a manually changed lineup to plan a new match; its substitution history must be kept.',409);
      const old=teamsKey(['a','b'].map(side=>game.players.filter(p=>p.side===side).map(p=>({id:p.id_roster}))));
      players.forEach(p=>p.queue_state='waiting');
      fill(record,[game.court],game,old);
      audit(record,'game.rebuilt',{id_game:game.id});
      return 'Up Next rebuilt using current results and queue rules.';
    } else if (action==='cancel') {
      if (!ACTIVE.includes(game.status)) fail('This game is already finished.',409);
      const reason=text(data.reason||'Cancelled by organizer','Cancellation reason',200);
      game.status='cancelled'; game.completed_at=now(); players.forEach(p=>enqueue(record,p));
      audit(record,'game.cancelled',{id_game:game.id,reason});
      return '';
    } else fail('Unknown game action.');
    audit(record,`game.${action}`,{id_game:game.id});
    return '';
  }

  function updateRating(player,results) {
    const scale=173.7178,mu=(player.value-1500)/scale,phi=player.deviation/scale,tau=.5;
    let information=0,improvement=0;
    for (const [opponent,score] of results) {
      const g=1/Math.sqrt(1+3*(opponent.deviation/scale)**2/Math.PI**2);
      const expected=1/(1+Math.exp(Math.max(-700,Math.min(700,-g*(mu-(opponent.value-1500)/scale)))));
      information+=g*g*expected*(1-expected); improvement+=g*(score-expected);
    }
    if (!(information>0)) fail('Rating observations have no usable information.');
    const variance=1/information,delta=variance*improvement,a=Math.log(player.volatility**2);
    const f=x=>{
      const e=Math.exp(x),total=phi*phi+variance+e;
      return e*(delta*delta-phi*phi-variance-e)/(2*total*total)-(x-a)/tau**2;
    };
    let left=a,right;
    if (delta*delta>phi*phi+variance) right=Math.log(delta*delta-phi*phi-variance);
    else {
      let k=1;
      while (f(a-k*tau)<0) { if (++k>1000) fail('Could not bracket rating volatility.'); }
      right=a-k*tau;
    }
    let fl=f(left),fr=f(right),converged=false;
    for (let i=0;i<1000;i++) {
      if (Math.abs(right-left)<=.000001) { converged=true; break; }
      const c=left+(left-right)*fl/(fr-fl),fc=f(c);
      if (fc*fr<=0) { left=right; fl=fr; } else fl/=2;
      right=c; fr=fc;
    }
    if (!converged) fail('Rating volatility did not converge.');
    const volatility=Math.exp(left/2),phiStar=Math.sqrt(phi*phi+volatility*volatility),nextPhi=1/Math.sqrt(1/(phiStar*phiStar)+1/variance);
    return {rating:Math.max(0,Math.min(4000,scale*(mu+nextPhi*nextPhi*improvement)+1500)),deviation:Math.min(350,scale*nextPhi),volatility};
  }

  function reconcile(record) {
    if (now()<record.session.starts_at+30*60) fail('No-show reconciliation opens 30 minutes after the session start.');
    let count=0;
    for (const player of record.players) if (player.rsvp==='yes'&&player.attendance==='absent'&&player.checked_in_at===null) { player.attendance='no_show'; count++; }
    return count;
  }

  function close(record) {
    if (record.games.some(g=>ACTIVE.includes(g.status))) fail('Complete or cancel every active court before closing.',409);
    const bases=new Map(record.players.map(p=>[p.id,{value:p.base_rating,deviation:p.base_deviation,volatility:p.base_volatility}]));
    for (const player of record.players) {
      const results=[];
      for (const game of record.games.filter(g=>g.status==='completed'&&ratedGame(g))) {
        const gp=game.players.find(p=>p.id_roster===player.id);
        if (!gp) continue;
        const partner=bases.get(game.players.find(p=>p.side===gp.side&&p.id_roster!==player.id).id_roster);
        const opponents=game.players.filter(p=>p.side!==gp.side).map(p=>bases.get(p.id_roster));
        const base=bases.get(player.id);
        const opponent={value:opponents[0].value+opponents[1].value-partner.value,deviation:Math.sqrt(opponents[0].deviation**2+opponents[1].deviation**2+partner.deviation**2)};
        results.push([opponent,Number((game.score_a>game.score_b)===(gp.side==='a'))]);
      }
      if (results.length) { Object.assign(player,updateRating(bases.get(player.id),results)); player.rated_games+=results.length; }
      if (player.attendance==='present') { player.attendance='left'; player.checked_out_at=now(); }
      off(player);
    }
    if (now()>=record.session.starts_at+30*60) reconcile(record);
    record.session.status='closed';
    audit(record,'session.closed');
    return 'Session closed. One Glicko-2 period was applied to completed results.';
  }

  function mutate(record,action,data) {
    if (record.session.revision!==data.revision) fail('This session changed. Refresh and try again.',409);
    if (record.session.status!=='active') fail('This session is closed.',409);
    const planned=['game','add-court'].includes(action)?upcoming(record).matches:[];
    const excluded=action==='game'&&data.action==='cancel'?record.games.find(g=>g.id===data.id_game)?.players.map(p=>p.id_roster):null;
    let notice='';
    if (action==='start-session') {
      if(!advanceCourts(record)) fail('No valid match is ready. Check in at least four players and review the selected matching mode.',409);
      notice='Session started. Available courts fill automatically.';
    } else if (action==='add-court') {
      if(record.session.court_count>=8) fail('A session supports at most 8 courts.',409);
      record.session.court_count+=1;
      audit(record,'court.added',{court:record.session.court_count});
    } else if (action==='configure') {
      const modeOnly=data.mode!==undefined&&Object.keys(data).every(key=>key==='revision'||key==='mode');
      if (record.games.length&&!modeOnly) fail('Session details are locked after preparing the first game. You can still change the matching mode.',409);
      const name=text(data.name??record.session.name,'Session name');
      const court_count=integer(data.court_count??record.session.court_count,'Courts',1,8);
      const max_players=integer(data.max_players??record.session.max_players,'Capacity',4,200);
      const mode=data.mode??record.session.mode;
      if (!MODES.includes(mode)) fail('Choose a supported play mode.');
      if (max_players<record.players.filter(p=>p.attendance==='present').length) fail('Capacity cannot be less than the checked-in player count.',409);
      const previousMode=record.session.mode;
      const released= mode!==previousMode ? record.games.filter(game=>game.status==='assigned') : [];
      for(const game of released) {
        game.status='cancelled';game.completed_at=now();
        for(const player of game.players) getPlayer(record,player.id_roster).queue_state='waiting';
      }
      Object.assign(record.session,{name,court_count,max_players,mode});
      if(mode!==previousMode) {
        audit(record,'session.mode_changed',{previous_mode:previousMode,mode,released_games:released.map(game=>game.id)});
        notice=`Mode changed to ${mode.replaceAll('_',' ')}. Up Next is recalculated; games already on court continue unchanged.`;
      } else audit(record,'session.configured',{court_count,max_players,mode});
    } else if (action==='checkin-confirmed') {
      if (!Array.isArray(data.id_rosters)||!data.id_rosters.length||data.id_rosters.length>200||new Set(data.id_rosters).size!==data.id_rosters.length) fail('Choose distinct players to check in.');
      const players=data.id_rosters.map(id=>getPlayer(record,id));
      players.forEach(available);
      if (record.players.filter(p=>p.attendance==='present').length+players.filter(p=>p.attendance!=='present').length>record.session.max_players) fail('Session capacity is full.',409);
      for (const player of players) {
        player.membership='active';player.waiver='valid';
        if (player.attendance!=='present') checkin(record,player);
        else if (player.queue_state==='off') rejoin(record,player);
      }
      audit(record,'players.checked_in_confirmed',{players:players.length});
      notice=`Checked in ${players.length} players. They are ready for the queue.`;
    } else if (action==='import-reviewed') notice=importPlayers(record,data);
    else if (action==='demo') {
      const names=['Avery','Blake','Cameron','Drew','Ellis','Frankie','Gray','Harper','Indigo','Jules','Kai','Lane','Morgan','Noel','Oak','Parker','Quinn','Reese','Sage','Taylor','Uma','Vale','Winter','Xan','Yael','Zion','Alex','Briar','Casey','Devon'];
      const ratings=[1800,1750,1200,1150,1350,1400,1250,1300,1500,1550,1000,1050,1600,1450,1100];
      importPlayers(record,{source:'demo',club_key:`demo-session-${record.session.id}`,players:names.map((name,i)=>({external_id:`demo-${String(i+1).padStart(2,'0')}`,name:`${name} (demo)`,rating:ratings[i%ratings.length]}))},true);
      notice='Loaded 30 synthetic demo players. Check them in to start.';
    } else if (action==='checkin-all') {
      const players=record.players.filter(p=>p.rsvp==='yes'&&['absent','no_show'].includes(p.attendance)).sort((a,b)=>a.id-b.id);
      if (record.players.filter(p=>p.attendance==='present').length+players.length>record.session.max_players) fail('There are more absent players than the remaining session capacity.',409);
      players.forEach(p=>checkin(record,p)); audit(record,'players.checked_in_all',{players:players.length});
      notice=`Checked in ${players.length} players. Eligibility is still required to join the queue.`;
    } else if (action==='player') playerAction(record,data);
    else if (action==='pair') {
      if (data.action==='pair') { pairPlayers(record,data.id_a,data.id_b); audit(record,'players.paired'); }
      else if (data.action==='unpair') {
        const player=getPlayer(record,data.id_roster); available(player);
        if (!player.paired_roster_id) fail('This player is not paired.',409);
        const partner=getPlayer(record,player.paired_roster_id); available(partner);
        player.paired_roster_id=null; partner.paired_roster_id=null; audit(record,'players.unpaired');
      } else fail('Unknown pairing action.');
    } else if (action==='fill') notice=fill(record);
    else if (action==='game') notice=gameAction(record,data);
    else if (action==='reconcile') { const count=reconcile(record); audit(record,'attendance.reconciled',{no_shows:count}); notice=`Marked ${count} absent RSVPs as no-shows. No penalties applied.`; }
    else if (action==='close') notice=close(record);
    else fail('Action not found.',404);
    if(action!=='start-session'&&!(action==='configure'&&data.mode!==undefined)&&!(action==='player'&&data.action==='rename')&&!(action==='game'&&data.action==='substitute')&&record.games.length&&record.session.status==='active') advanceCourts(record,planned,excluded);
    record.session.revision++;
    return notice;
  }

  async function publicGet(path) {
    const response=await fetch(`https://api.reclub.co${path}`,{headers:{Accept:'application/json','x-output-casing':'camelCase'},credentials:'omit',redirect:'error',signal:AbortSignal.timeout(10000)});
    if (!response.ok) fail(`Reclub could not load this event (HTTP ${response.status}).`,502);
    const data=await response.json();
    if (!data||typeof data!=='object'||Array.isArray(data)) fail('Reclub returned an unsupported response.',502);
    return data;
  }

  async function preview(link) {
    let url;
    try { url=new URL(link); } catch { fail('Paste a public Reclub event link.'); }
    const match=url.pathname.match(/^\/m\/([a-z0-9]{4,12})\/?$/i);
    if (url.protocol!=='https:'||!['reclub.co','www.reclub.co'].includes(url.hostname)||url.username||url.password||url.port||!match) fail('Use a public event link such as https://reclub.co/m/ABC123.');
    const ref=match[1].toUpperCase(),event=await publicGet(`/meets/by-ref/${ref}`);
    if (!Array.isArray(event.participants)||event.participants.length>1000) fail('Reclub returned an unsupported or oversized participant list.',502);
    const confirmed=event.participants.map((slot,index)=>({slot,index})).filter(({slot})=>slot&&slot.status===1);
    if (confirmed.length>200) fail('Review events with at most 200 confirmed players.');
    const ids=[...new Set(confirmed.filter(({slot})=>slot.referenceType===1&&Number.isSafeInteger(slot.referenceId)&&slot.referenceId>0).map(({slot})=>slot.referenceId))];
    const profiles=new Map();
    for (let start=0;start<ids.length;start+=50) {
      const result=await publicGet(`/players/userIds?userIds=${ids.slice(start,start+50).join(',')}&scopes=BASIC_PROFILE`);
      if (!Array.isArray(result.players)) fail('Reclub returned an unsupported profile list.',502);
      for (const p of result.players) if (p&&Number.isSafeInteger(p.userId)&&typeof p.name==='string'&&p.name.trim()) profiles.set(p.userId,p);
    }
    const players=[];
    for (const {slot,index} of confirmed) {
      if (![1,2,3].includes(slot.referenceType)) continue;
      const profile=slot.referenceType===1?profiles.get(slot.referenceId):null;
      const ext=slot.externalReference;
      const name=slot.referenceType===1 ? (profile?.name || 'Player (name unavailable)') : (slot.referenceType===3&&typeof ext?.name==='string'&&ext.name.trim()?ext.name:'Guest (name unavailable)');
      const gender=profile?.gender || (slot.referenceType===3?ext?.gender:null);
      const stable=slot.id ?? slot.participantId ?? `${ref}:${index}`;
      players.push({external_id:`slot:${String(stable).slice(0,100)}`,name:name.trim().slice(0,80),rating:null,gender:['M','F'].includes(gender)?gender:null,club_group:null});
    }
    return {reference:ref,event_name:typeof event.name==='string'?event.name.slice(0,120):`Reclub event ${ref}`,club_key:Number.isSafeInteger(event.groupId)?`group:${event.groupId}`:`event:${ref}`,players};
  }

  async function request(path,data) {
    if (path==='/api/reclub/preview') return preview(data.url);
    if (path==='/api/sessions'&&data!==undefined) return create(data);
    const record=read(currentToken);
    if (path==='/api/sessions') return {sessions:record?[structuredClone(record.session)]:[]};
    if (!record) fail('This session is unavailable or expired. Generate a new link.',404);
    const parts=path.split('/');
    if (parts[1]!=='api'||parts[2]!=='sessions'||Number(parts[3])!==record.session.id) fail('Session not found.',404);
    if (parts.length===4&&data===undefined) return snapshot(record);
    if (parts.length!==5||data===undefined) fail('Action not found.',404);
    if (!navigator.locks) fail('This browser cannot safely save session changes. Use a current browser on HTTPS.');
    return navigator.locks.request(PREFIX+currentToken,()=>{
      const latest=read(currentToken);
      if (!latest) fail('Session not found.',404);
      const notice=mutate(latest,parts[4],data);
      save(latest);
      return {...snapshot(latest),notice};
    });
  }

  function validateSnapshot(value,token) {
    if (!value||![1,2].includes(value.version)||value.token!==token||!value.session||!Array.isArray(value.players)||!Array.isArray(value.games)||!Array.isArray(value.audit)) fail('This session link contains an unsupported snapshot.');
    const s=value.session;
    integer(s.id,'Session ID',1,Number.MAX_SAFE_INTEGER);
    text(s.name,'Session name'); integer(s.court_count,'Courts',1,8); integer(s.max_players,'Capacity',4,200);
    integer(s.revision,'Revision',0,Number.MAX_SAFE_INTEGER); integer(s.next_ticket,'Queue ticket',0,Number.MAX_SAFE_INTEGER);
    if (!MODES.includes(s.mode)||!['active','closed'].includes(s.status)||!Number.isFinite(s.starts_at)||s.starts_at<=0||s.starts_at>=4102444800||!Number.isFinite(s.created_at)||s.created_at<=0||s.created_at>now()+60||value.expires_at!==s.created_at+LIFETIME) fail('This link has invalid session settings or expiry.');
    if (value.expires_at<=now()) fail('This session link has expired after 48 hours. Generate a new link.',410);
    if (value.players.length>200||value.audit.length>30) fail('This session snapshot is too large.');
    const ids=new Set(),identities=new Set();
    for (const p of value.players) {
      if (!p||typeof p!=='object') fail('This link contains an invalid player.');
      integer(p.id,'Player ID',1,Number.MAX_SAFE_INTEGER);
      if (ids.has(p.id)) fail('This link contains duplicate player IDs.');
      ids.add(p.id);
      const identity=JSON.stringify([p.source,p.club_key,p.external_id]);
      if (identities.has(identity)) fail('This link contains duplicate player identities.');
      identities.add(identity);
      text(p.name,'Player name',80); text(p.external_id,'Player ID'); text(p.club_key,'Club identifier');
      if (!['manual','reclub','demo'].includes(p.source)||!['yes','no','waitlist','cancelled'].includes(p.rsvp)||!['absent','present','left','no_show'].includes(p.attendance)||!['active','expired','unknown'].includes(p.membership)||!['valid','missing','unknown'].includes(p.waiver)||!['off','waiting','assigned','playing'].includes(p.queue_state)) fail('This link contains an invalid player state.');
      if (p.gender!==null&&!['M','F'].includes(p.gender)) fail('This link contains an invalid player category.');
      if (p.club_group!==null) text(p.club_group,'Club group',40);
      for (const key of ['rating','base_rating']) if (!Number.isFinite(p[key])||p[key]<0||p[key]>4000) fail('This link contains an invalid rating.');
      for (const key of ['deviation','base_deviation','volatility','base_volatility']) if (!Number.isFinite(p[key])||p[key]<=0) fail('This link contains invalid rating uncertainty.');
      for (const key of ['games_played','rated_games']) integer(p[key],key,0,Number.MAX_SAFE_INTEGER);
      integer(p.is_late,'Late flag',0,1);
      for (const key of ['checked_in_at','checked_out_at','queued_at']) if (p[key]!==null&&(!Number.isFinite(p[key])||p[key]<0)) fail('This link contains an invalid player timestamp.');
      if (p.ticket!==null) integer(p.ticket,'Queue ticket',1,s.next_ticket);
      if (p.queue_state!=='off'&&(p.ticket===null||p.attendance!=='present'||!eligible(p))) fail('This link contains an invalid queue assignment.');
    }
    for (const p of value.players) if (p.paired_roster_id!==null) {
      const partner=value.players.find(q=>q.id===p.paired_roster_id);
      if (!partner||partner.id===p.id||partner.paired_roster_id!==p.id) fail('This link contains an invalid player pair.');
    }
    const games=new Set(),activePlayers=new Map(),courts=new Set(),played=new Map();
    for (const g of value.games) {
      if (!g||!Array.isArray(g.players)||g.players.length!==4||!['assigned','playing','completed','cancelled'].includes(g.status)) fail('This link contains an invalid game.');
      integer(g.id,'Game ID',1,Number.MAX_SAFE_INTEGER); integer(g.court,'Court',1,s.court_count);
      if (games.has(g.id)||new Set(g.players.map(p=>p.id_roster)).size!==4||g.players.filter(p=>p.side==='a').length!==2||g.players.filter(p=>p.side==='b').length!==2) fail('This link contains an invalid team assignment.');
      games.add(g.id); text(g.reason,'Match reason',500);
      for (const key of ['mean_a','mean_b','expected_a','cost']) if (!Number.isFinite(g[key])) fail('This link contains an invalid game estimate.');
      if (g.expected_a<0||g.expected_a>1||!Number.isFinite(g.assigned_at)||g.assigned_at<0) fail('This link contains an invalid game estimate or timestamp.');
      for (const key of ['started_at','completed_at']) if (g[key]!==null&&(!Number.isFinite(g[key])||g[key]<0)) fail('This link contains an invalid game timestamp.');
      if (g.status==='completed') {
        integer(g.score_a,'Team A score',0,99); integer(g.score_b,'Team B score',0,99);
        if (g.score_a===g.score_b) fail('This link contains a completed game without a winner.');
      }
      if (ACTIVE.includes(g.status)) {
        if (courts.has(g.court)) fail('This link assigns a court twice.');
        courts.add(g.court);
      }
      const changes=g.substitutions??[];
      if (!Array.isArray(changes)||changes.length>200||(changes.length&&value.version!==2)) fail('This link contains invalid substitutions.');
      const lineup=g.players.map(p=>({id:p.id_roster,side:p.side}));
      let previous=g.completed_at??now()+60;
      for (const change of [...changes].reverse()) {
        if (!change||!ids.has(change.outgoing_id)||!ids.has(change.incoming_id)||change.outgoing_id===change.incoming_id||!['a','b'].includes(change.side)||typeof change.during_play!=='boolean'||!['break','checkout'].includes(change.disposition)||!Number.isFinite(change.at)||change.at<g.assigned_at||change.at>previous||change.at>now()+60) fail('This link contains an invalid substitution.');
        if (change.during_play&&(g.status==='assigned'||g.started_at===null||change.at<g.started_at)||!change.during_play&&g.started_at!==null&&change.at>g.started_at) fail('This link contains an invalid substitution time.');
        const slot=lineup.find(p=>p.id===change.incoming_id&&p.side===change.side);
        if (!slot||lineup.some(p=>p.id===change.outgoing_id)) fail('This link contains an inconsistent substitution history.');
        slot.id=change.outgoing_id;previous=change.at;
      }
      for (const gp of g.players) {
        if (!ids.has(gp.id_roster)) fail('This link assigns a player outside its roster.');
        for (const key of ['rating','deviation','volatility']) if (!Number.isFinite(gp[key])||(key!=='rating'&&gp[key]<=0)) fail('This link contains an invalid frozen rating.');
        if (ACTIVE.includes(g.status)) {
          if (activePlayers.has(gp.id_roster)) fail('This link assigns a player twice.');
          activePlayers.set(gp.id_roster,g.status);
        }
      }
      if (g.status==='completed') for (const id of participants(g)) played.set(id,(played.get(id)||0)+1);
    }
    for (const p of value.players) if (p.games_played!==(played.get(p.id)||0)|| (ACTIVE.includes(p.queue_state) ? activePlayers.get(p.id)!==p.queue_state : activePlayers.has(p.id))) fail('This link contains inconsistent player results or assignments.');
    for (const a of value.audit) {
      if (!a||typeof a.action!=='string'||typeof a.detail!=='string'||!Number.isFinite(a.created_at)) fail('This link contains invalid activity.');
      integer(a.id,'Activity ID',1,Number.MAX_SAFE_INTEGER);
    }
    for (const key of ['next_player','next_game','next_audit']) integer(value[key],key,1,Number.MAX_SAFE_INTEGER);
    if (value.next_player<=Math.max(0,...ids)||value.next_game<=Math.max(0,...games)||value.next_audit<=Math.max(0,...value.audit.map(a=>a.id))) fail('This link contains invalid record counters.');
    if (s.status==='closed'&&(activePlayers.size||value.players.some(p=>p.queue_state!=='off'))) fail('This closed session has an active queue.');
    return value;
  }

  async function open(token,encoded) {
    currentToken=token||null;
    if (!token) { purgeExpired(); return null; }
    if (!/^[a-f0-9-]{36}$/.test(token)) fail('This session link is invalid.');
    const existing=read(token);
    if (existing||!encoded) return existing;
    if (encoded.length>3_000_000||!/^[A-Za-z0-9_-]+$/.test(encoded)) fail('This session link is too large or invalid.');
    let raw;
    try { raw=Uint8Array.from(atob(encoded.replace(/-/g,'+').replace(/_/g,'/')),c=>c.charCodeAt(0)); }
    catch { fail('This session link contains an unreadable snapshot.'); }
    const reader=new Blob([raw]).stream().pipeThrough(new DecompressionStream('deflate')).getReader();
    const chunks=[];
    let length=0;
    try {
      while (true) {
        const {value,done}=await reader.read();
        if (done) break;
        length+=value.byteLength;
        if (length>2_000_000) { await reader.cancel(); fail('This session snapshot exceeds the 2 MB browser import limit.'); }
        chunks.push(value);
      }
    } catch (error) { fail(error?.status?error.message:'This session snapshot could not be decompressed.'); }
    let value;
    try { value=JSON.parse(await new Blob(chunks).text()); }
    catch { fail('This session snapshot could not be read.'); }
    const record=validateSnapshot(value,token);
    save(record);
    return record;
  }

  async function share(id) {
    const record=read(currentToken);
    if (!record||record.session.id!==id) fail('Session not found.',404);
    const json=JSON.stringify(record);
    if (new TextEncoder().encode(json).length>2_000_000) fail('This session exceeds the 2 MB link export limit.');
    const bytes=new Uint8Array(await new Response(new Blob([json]).stream().pipeThrough(new CompressionStream('deflate'))).arrayBuffer());
    let binary='';
    for (const byte of bytes) binary+=String.fromCharCode(byte);
    const encoded=btoa(binary).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
    const hash=new URLSearchParams({link:currentToken,snapshot:encoded,view:'queue'});
    return `${location.origin}${location.pathname}#${hash}`;
  }

  window.CourtsideBrowser={request,open,share,
    tokenFor(id) { const record=read(currentToken); return record?.session.id===id?currentToken:null; },
    lifetime:LIFETIME};
})();
