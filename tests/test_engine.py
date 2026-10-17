import io
import csv
import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from picklequeue.engine import Engine, Problem
from picklequeue.matching import choose_game
from picklequeue.ratings import Rating, update_rating
from picklequeue.server import serve


def csv_roster(ratings=(1800,1750,1200,1150), waiver='valid'):
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(['external_id','name','rsvp','membership','waiver','initial_rating'])
    for i, rating in enumerate(ratings):
        writer.writerow([f'p{i}',f'Player {i+1}','yes','active',waiver,rating])
    return stream.getvalue()


class RatingsTests(unittest.TestCase):
    def test_official_glickman_worked_example(self):
        result = update_rating(Rating(1500,200,.06), [(Rating(1400,30),1),(Rating(1550,100),0),(Rating(1700,300),0)])
        # The published example rounds intermediate values.
        self.assertAlmostEqual(result.value,1464.06,delta=.02)
        self.assertAlmostEqual(result.deviation,151.52,places=2)
        self.assertAlmostEqual(result.volatility,.05999,delta=.00001)

    def test_no_results_increases_uncertainty_only(self):
        original = Rating(1350,70,.06)
        result = update_rating(original,[])
        self.assertEqual(result.value,original.value)
        self.assertEqual(result.volatility,original.volatility)
        self.assertGreater(result.deviation,original.deviation)

    def test_uncertain_players_move_more(self):
        opponent = Rating(1200,50)
        high = update_rating(Rating(1200,350),[(opponent,1)])
        low = update_rating(Rating(1200,50),[(opponent,1)])
        self.assertGreater(high.value-1200,low.value-1200)


class MatchingTests(unittest.TestCase):
    def players(self, values):
        return [{'id':i+1,'ticket':i+1,'rating':rating} for i,rating in enumerate(values)]

    def test_strong_players_split_and_equal_totals(self):
        match = choose_game(self.players([1800,1750,1200,1150]))
        sides = [{p['id'] for p in t} for t in match['teams']]
        self.assertEqual(sides,[{1,4},{2,3}])
        self.assertEqual(match['delta'],0)
        self.assertEqual(match['expected'],.5)

    def test_history_changes_choice_when_ratings_equal(self):
        match = choose_game(self.players([1200]*4), {(1,2):4,(3,4):4})
        self.assertNotEqual({p['id'] for p in match['teams'][0]},{1,2})

    def test_no_valid_match_does_not_skip_oldest(self):
        self.assertIsNone(choose_game(self.players([3000,1000,1000,1000,1000])))

    def test_oldest_is_included_among_larger_pool(self):
        match = choose_game(self.players([1200]*20))
        self.assertIn(1,{p['id'] for t in match['teams'] for p in t})

    def test_expands_window_for_balance_without_skipping_anchor(self):
        values=[3000]+[1000]*11+[3000,1000,1000]
        result=choose_game(self.players(values))
        self.assertEqual(result['window'],15)
        self.assertIn(1,{p['id'] for t in result['teams'] for p in t})

    def test_pair_preference_brings_partner_into_candidate_window(self):
        players=self.players([1200]*20)
        players[0]['paired_with']=20
        players[-1]['paired_with']=1
        result=choose_game(players,window=4)
        sides=[{player['id'] for player in team} for team in result['teams']]
        self.assertTrue(any({1,20} <= side for side in sides))

    def test_social_mix_does_not_use_ratings_for_team_choice(self):
        players=self.players([1800,1000,1500,1200,1300,1600])
        first=choose_game(players,mode='social_mix')
        for player in players:
            player['rating']=4000-player['rating']
        second=choose_game(players,mode='social_mix')
        self.assertEqual([[p['id'] for p in team] for team in first['teams']],
                         [[p['id'] for p in team] for team in second['teams']])
        self.assertEqual(first['expected'],.5)

    def test_mixed_doubles_and_club_wars_enforce_team_constraints(self):
        players=self.players([1200]*4)
        for player,gender,group in zip(players,['M','F','M','F'],['A','A','B','B']):
            player['gender']=gender
            player['club_group']=group
        mixed=choose_game(players,mode='mixed_doubles')
        self.assertTrue(all({p['gender'] for p in team}=={'M','F'} for team in mixed['teams']))
        war=choose_game(players,mode='club_wars')
        self.assertEqual([{p['club_group'] for p in team} for team in war['teams']],[{'A'},{'B'}])


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.now = 1800000000
        self.engine = Engine(Path(self.directory.name)/'test.sqlite3',clock=lambda:self.now)
        self.id_session = self.engine.create_session({'name':'Test open play','starts_at':self.now,'court_count':2,'max_players':30})

    def tearDown(self):
        self.directory.cleanup()

    def state(self):
        return self.engine.state(self.id_session)

    def revision(self):
        return self.state()['session']['revision']

    def import_players(self, ratings=(1800,1750,1200,1150), waiver='valid'):
        self.engine.import_roster(self.id_session,self.revision(),csv_roster(ratings,waiver),'manual','test-club')

    def check_all(self):
        for player in self.state()['players']:
            self.engine.player_action(self.id_session,self.revision(),player['id'],'checkin')

    def fill(self):
        return self.engine.fill_courts(self.id_session,self.revision())

    def test_substitute_keeps_court_side_and_history_without_rating_partial_game(self):
        self.import_players([1200]*5); self.check_all(); self.fill()
        before=self.state(); game=before['games'][0]
        outgoing=game['players'][0]; incoming=next(p for p in before['players'] if p['queue_state']=='waiting')
        self.engine.game_action(self.id_session,self.revision(),game['id'],'start')
        counter=self.state()['session']['next_ticket']
        self.engine.game_action(self.id_session,self.revision(),game['id'],'substitute',{'outgoing_id':outgoing['id_roster'],'incoming_id':incoming['id'],'disposition':'break'})
        state=self.state(); changed=state['games'][0]
        departed=next(p for p in state['players'] if p['id']==outgoing['id_roster'])
        self.assertEqual((departed['attendance'],departed['queue_state'],departed['ticket'],departed['queued_at']),('present','off',counter+1,None))
        self.assertEqual((changed['id'],changed['court'],changed['status']),(game['id'],game['court'],'playing'))
        self.assertFalse(changed['rating_eligible'])
        self.assertEqual(next(p for p in changed['players'] if p['id_roster']==incoming['id'])['side'],outgoing['side'])
        self.assertEqual(changed['substitutions'][0]['outgoing_name'],outgoing['name'])
        with self.engine.connect() as db:
            self.assertIsNone(db.execute('SELECT 1 FROM active_assignments WHERE id_roster=?',(outgoing['id_roster'],)).fetchone())
            self.assertEqual(db.execute('SELECT id_game FROM active_assignments WHERE id_roster=?',(incoming['id'],)).fetchone()[0],game['id'])
        self.engine.game_action(self.id_session,self.revision(),game['id'],'complete',{'winner':'a'})
        state=self.state()
        self.assertTrue(all(p['games_played']==1 and p['wins']==0 and p['losses']==0 and p['last_outcome'] is None for p in state['players']))
        self.assertEqual(next(p for p in state['players'] if p['id']==departed['id'])['queue_state'],'off')
        with self.engine.connect() as db:
            self.assertEqual(self.engine.histories(db,self.id_session),({},{}))
        self.engine.close_session(self.id_session,self.revision())
        self.assertTrue(all(p['rating']==1200 and p['rated_games']==0 for p in self.state()['players']))

    def test_repeated_substitutions_count_each_participant_once(self):
        self.import_players([1200]*5); self.check_all(); self.fill()
        state=self.state(); game=state['games'][0]
        original=game['players'][0]['id_roster']; replacement=next(p for p in state['players'] if p['queue_state']=='waiting')['id']
        self.engine.game_action(self.id_session,self.revision(),game['id'],'start')
        self.engine.game_action(self.id_session,self.revision(),game['id'],'substitute',{'outgoing_id':original,'incoming_id':replacement,'disposition':'break'})
        self.engine.player_action(self.id_session,self.revision(),original,'resume')
        self.engine.game_action(self.id_session,self.revision(),game['id'],'substitute',{'outgoing_id':replacement,'incoming_id':original,'disposition':'break'})
        returned_ticket=next(p for p in self.state()['players'] if p['id']==replacement)['ticket']
        self.engine.game_action(self.id_session,self.revision(),game['id'],'complete',{'winner':'b'})
        state=self.state()
        self.assertEqual(len(state['games'][0]['substitutions']),2)
        self.assertTrue(all(p['games_played']==1 for p in state['players']))
        checked_out=next(p for p in state['players'] if p['id']==replacement)
        self.assertEqual((checked_out['attendance'],checked_out['queue_state'],checked_out['ticket']),('present','off',returned_ticket))

    def test_substitute_from_reserved_up_next_releases_and_replans_it(self):
        self.import_players([1200]*12); self.check_all(); self.fill()
        state=self.state(); current,preview=state['games']
        self.engine.game_action(self.id_session,self.revision(),current['id'],'start')
        incoming=preview['players'][0]['id_roster']; outgoing=current['players'][0]['id_roster']
        tickets={p['id']:p['ticket'] for p in state['players']}
        self.engine.game_action(self.id_session,self.revision(),current['id'],'substitute',{'outgoing_id':outgoing,'incoming_id':incoming,'disposition':'break'})
        state=self.state()
        self.assertEqual(next(g for g in state['games'] if g['id']==preview['id'])['status'],'cancelled')
        planned=next(g for g in state['games'] if g['status']=='assigned')
        self.assertNotIn(incoming,[p['id_roster'] for p in planned['players']])
        self.assertNotIn(outgoing,[p['id_roster'] for p in planned['players']])
        self.assertTrue(all(p['ticket']==tickets[p['id']] for p in state['players'] if p['id']!=outgoing))

    def test_substitute_before_start_keeps_normal_results_and_departing_priority(self):
        self.import_players([1200]*5); self.check_all(); self.fill()
        state=self.state(); game=state['games'][0]
        outgoing=game['players'][0]['id_roster']; incoming=next(p for p in state['players'] if p['queue_state']=='waiting')['id']
        ticket=next(p for p in state['players'] if p['id']==outgoing)['ticket']
        self.engine.game_action(self.id_session,self.revision(),game['id'],'substitute',{'outgoing_id':outgoing,'incoming_id':incoming,'disposition':'break'})
        self.assertEqual(next(p for p in self.state()['players'] if p['id']==outgoing)['ticket'],ticket)
        self.assertTrue(self.state()['games'][0]['rating_eligible'])
        with self.assertRaises(Problem):
            self.engine.game_action(self.id_session,self.revision(),game['id'],'rebuild')
        self.assertEqual(len(self.state()['games'][0]['substitutions']),1)
        self.engine.game_action(self.id_session,self.revision(),game['id'],'start')
        self.engine.game_action(self.id_session,self.revision(),game['id'],'complete',{'winner':'a'})
        self.engine.close_session(self.id_session,self.revision())
        state=self.state()
        self.assertEqual(next(p for p in state['players'] if p['id']==outgoing)['games_played'],0)
        self.assertEqual(sum(p['rated_games'] for p in state['players']),4)
        self.assertEqual(sum(p['wins'] for p in state['players']),2)
        self.assertEqual(sum(p['losses'] for p in state['players']),2)

    def test_invalid_and_stale_substitutions_roll_back(self):
        self.import_players([1200]*6); self.check_all(); self.fill()
        state=self.state(); game=state['games'][0]
        self.engine.game_action(self.id_session,self.revision(),game['id'],'start')
        waiting=[p for p in self.state()['players'] if p['queue_state']=='waiting']
        self.engine.player_action(self.id_session,self.revision(),waiting[0]['id'],'pause')
        state=self.state(); outgoing=game['players'][0]['id_roster']
        valid={'outgoing_id':outgoing,'incoming_id':waiting[1]['id'],'disposition':'break'}
        for invalid in ({'disposition':'checkout'},{'incoming_id':waiting[0]['id']},{'incoming_id':game['players'][1]['id_roster']},{'incoming_id':outgoing},{'incoming_id':99999},{'outgoing_id':waiting[1]['id']},{'disposition':'swap'},{'incoming_id':True}):
            with self.assertRaises(Problem):
                self.engine.game_action(self.id_session,self.revision(),game['id'],'substitute',{**valid,**invalid})
            self.assertEqual(self.state(),state)
        with self.assertRaises(Problem):
            self.engine.game_action(self.id_session,self.revision()-1,game['id'],'substitute',valid)
        self.assertEqual(self.state(),state)
        self.engine.game_action(self.id_session,self.revision(),game['id'],'substitute',valid)
        self.engine.game_action(self.id_session,self.revision(),game['id'],'cancel',{'reason':'Synthetic cancellation'})
        self.assertTrue(all(p['games_played']==0 for p in self.state()['players']))
        self.assertEqual(len(self.state()['games'][0]['substitutions']),1)
        with self.assertRaises(Problem):
            self.engine.game_action(self.id_session,self.revision(),game['id'],'substitute',valid)

    def test_version_two_substitution_migration_preserves_existing_game(self):
        self.import_players(); self.check_all(); self.fill()
        before=self.state()
        with self.engine.connect() as db:
            db.execute('DROP TABLE game_substitutions')
            db.execute('PRAGMA user_version=2')
        migrated=Engine(self.engine.path,clock=lambda:self.now)
        self.assertEqual(migrated.state(self.id_session),before)
        with migrated.connect() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],3)

    def test_rename_preserves_break_priority_and_game_identity(self):
        self.import_players(); self.check_all()
        player=self.state()['players'][0]
        self.engine.player_action(self.id_session,self.revision(),player['id'],'pause')
        before=self.state()
        self.engine.player_action(self.id_session,self.revision(),player['id'],'rename',{'name':'  QA <Renamed> & Player  '})
        after=self.state()
        renamed=next(p for p in after['players'] if p['id']==player['id'])
        self.assertEqual(renamed['name'],'QA <Renamed> & Player')
        for key in ('id','id_member','ticket','queued_at','queue_state','games_played'):
            self.assertEqual(renamed[key],before['players'][0][key])
        self.assertEqual(after['session']['next_ticket'],before['session']['next_ticket'])
        for name in (' ', 'x'*81):
            with self.assertRaises(Problem):
                self.engine.player_action(self.id_session,self.revision(),player['id'],'rename',{'name':name})
        self.engine.player_action(self.id_session,self.revision(),player['id'],'resume')
        self.fill()
        self.engine.player_action(self.id_session,self.revision(),player['id'],'rename',{'name':'QA On court'})
        state=self.state()
        participant=next(gp for g in state['games'] for gp in g['players'] if gp['id_roster']==player['id'])
        self.assertEqual(participant['name'],'QA On court')

    def test_break_excludes_player_then_restores_priority_and_restarts_wait_clock(self):
        self.import_players([1200]*8); self.check_all()
        player=self.state()['players'][0]
        ticket=player['ticket']
        counter=self.state()['session']['next_ticket']
        self.engine.player_action(self.id_session,self.revision(),player['id'],'pause')
        self.now+=600
        self.fill()
        paused=next(p for p in self.state()['players'] if p['id']==player['id'])
        self.assertEqual((paused['queue_state'],paused['ticket'],paused['queued_at']),('off',ticket,None))
        self.assertFalse(any(gp['id_roster']==player['id'] for g in self.state()['games'] for gp in g['players']))
        self.engine.player_action(self.id_session,self.revision(),player['id'],'resume')
        resumed=next(p for p in self.state()['players'] if p['id']==player['id'])
        self.assertEqual((resumed['ticket'],resumed['position'],resumed['wait_minutes']),(ticket,1,0))
        self.assertEqual(self.state()['session']['next_ticket'],counter)
        with self.assertRaises(Problem):
            self.engine.player_action(self.id_session,self.revision(),player['id'],'resume')

    def test_saving_valid_eligibility_does_not_end_a_break(self):
        self.import_players(); self.check_all()
        player=self.state()['players'][0]
        self.engine.player_action(self.id_session,self.revision(),player['id'],'pause')
        self.engine.player_action(self.id_session,self.revision(),player['id'],'eligibility',{'membership':'active','waiver':'valid'})
        paused=next(p for p in self.state()['players'] if p['id']==player['id'])
        self.assertEqual((paused['queue_state'],paused['ticket']),('off',player['ticket']))
        with self.engine.connect() as db:
            db.execute('UPDATE roster SET ticket=NULL WHERE id=?',(player['id'],))
            db.commit()
        self.engine.player_action(self.id_session,self.revision(),player['id'],'eligibility',{'membership':'active','waiver':'valid'})
        self.assertEqual(next(p for p in self.state()['players'] if p['id']==player['id'])['queue_state'],'off')

    def test_checkout_during_break_discards_held_priority(self):
        self.import_players(); self.check_all()
        player=self.state()['players'][0]
        self.engine.player_action(self.id_session,self.revision(),player['id'],'pause')
        self.engine.player_action(self.id_session,self.revision(),player['id'],'checkout')
        checked_out=next(p for p in self.state()['players'] if p['id']==player['id'])
        self.assertIsNone(checked_out['ticket'])
        self.engine.player_action(self.id_session,self.revision(),player['id'],'checkin')
        returned=next(p for p in self.state()['players'] if p['id']==player['id'])
        self.assertGreater(returned['ticket'],player['ticket'])
        self.assertEqual(returned['position'],4)

    def test_lost_eligibility_during_break_discards_held_priority(self):
        self.import_players(); self.check_all()
        player=self.state()['players'][0]
        self.engine.player_action(self.id_session,self.revision(),player['id'],'pause')
        self.engine.player_action(self.id_session,self.revision(),player['id'],'eligibility',{'membership':'expired','waiver':'valid'})
        self.assertIsNone(next(p for p in self.state()['players'] if p['id']==player['id'])['ticket'])
        self.engine.player_action(self.id_session,self.revision(),player['id'],'eligibility',{'membership':'active','waiver':'valid'})
        returned=next(p for p in self.state()['players'] if p['id']==player['id'])
        self.assertGreater(returned['ticket'],player['ticket'])
        self.assertEqual(returned['position'],4)

    def make_mode_session(self, mode, players, court_count=2):
        id_session=self.engine.create_session({'name':f'{mode} test','starts_at':self.now,
                                               'court_count':court_count,'max_players':40,'mode':mode})
        self.engine.import_reviewed(id_session,0,players,[],'manual',f'test-{mode}')
        with self.engine.connect() as db:
            db.execute("UPDATE roster SET membership='active',waiver='valid' WHERE id_session=?",(id_session,))
            db.commit()
        self.engine.checkin_all(id_session,1)
        return id_session

    def play_game(self, id_game, score_a=11, score_b=7):
        self.engine.game_action(self.id_session,self.revision(),id_game,'start')
        self.engine.game_action(self.id_session,self.revision(),id_game,'complete',
                                {'score_a':score_a,'score_b':score_b})

    def test_winner_only_result_and_correction(self):
        self.import_players()
        self.check_all()
        game = self.fill()['assigned'][0]
        self.engine.game_action(self.id_session,self.revision(),game,'start')
        for payload in ({'winner':'c'}, {'winner':'a','score_a':11,'score_b':0}):
            revision = self.revision()
            with self.assertRaises(Problem):
                self.engine.game_action(self.id_session,revision,game,'complete',payload)
            self.assertEqual(self.revision(),revision)
            self.assertEqual(self.state()['metrics']['completed_games'],0)
        self.engine.game_action(self.id_session,self.revision(),game,'complete',{'winner':'b'})
        before = self.state()
        result = next(g for g in before['games'] if g['id']==game)
        self.assertEqual((result['score_a'],result['score_b']),(0,1))
        self.assertEqual(before['metrics']['completed_games'],1)
        self.assertTrue(all(p['games_played']==1 for p in before['players']))
        self.assertEqual(sum(p['wins'] for p in before['players']),2)
        self.assertEqual(json.loads(before['audit'][0]['detail'])['result_type'],'winner_only')
        with self.assertRaises(Problem):
            self.engine.game_action(self.id_session,self.revision(),game,'complete',{'winner':'b'})
        self.engine.game_action(self.id_session,self.revision(),game,'swap_winner')
        after = self.state()
        result = next(g for g in after['games'] if g['id']==game)
        self.assertEqual((result['score_a'],result['score_b']),(1,0))
        self.assertTrue(all(p['games_played']==1 for p in after['players']))

    def test_swap_winner_preserves_counts_queue_and_staged_games(self):
        self.import_players([1200]*4)
        self.check_all()
        recorded=[]
        for _ in range(3):
            id_game=self.fill()['assigned'][0]
            self.play_game(id_game)
            recorded.append(id_game)
        staged=self.fill()['assigned'][0]
        before=self.state()
        target=next(g for g in before['games'] if g['id']==recorded[0])
        self.engine.game_action(self.id_session,self.revision(),target['id'],'swap_winner')
        after=self.state()
        corrected=next(g for g in after['games'] if g['id']==target['id'])
        self.assertEqual((corrected['score_a'],corrected['score_b']),(7,11))
        for key in ('id','court','players','completed_at','status'):
            self.assertEqual(corrected[key],target[key])
        self.assertEqual(len(after['games']),len(before['games']))
        self.assertEqual(after['metrics'],before['metrics'])
        self.assertEqual(next(g for g in after['games'] if g['id']==staged),
                         next(g for g in before['games'] if g['id']==staged))
        old={p['id']:p for p in before['players']}
        side={p['id_roster']:p['side'] for p in target['players']}
        for player in after['players']:
            self.assertEqual(player['games_played'],3)
            self.assertEqual(player['wins'],old[player['id']]['wins']+(-1 if side[player['id']]=='a' else 1))
            for key in ('ticket','queued_at','queue_state','rating','deviation'):
                self.assertEqual(player[key],old[player['id']][key])
        self.assertEqual(after['audit'][0]['action'],'game.winner_swapped')
        stale=before['session']['revision']
        with self.assertRaises(Problem):
            self.engine.game_action(self.id_session,stale,target['id'],'swap_winner')
        self.assertEqual(self.state(),after)

    def test_swap_rejects_unfinished_cancelled_cross_session_and_closed_games(self):
        self.import_players([1200]*4)
        self.check_all()
        id_game=self.fill()['assigned'][0]
        with self.assertRaises(Problem):
            self.engine.game_action(self.id_session,self.revision(),id_game,'swap_winner')
        other=self.engine.create_session({'name':'Other synthetic session'})
        with self.assertRaises(Problem):
            self.engine.game_action(other,0,id_game,'swap_winner')
        self.play_game(id_game)
        self.engine.close_session(self.id_session,self.revision())
        before=self.state()
        with self.assertRaises(Problem):
            self.engine.game_action(self.id_session,self.revision(),id_game,'swap_winner')
        self.assertEqual(before,self.state())

    def test_corrected_result_is_rated_once_at_close_and_cancellation_cannot_swap(self):
        self.import_players([1200]*4)
        self.check_all()
        id_game=self.fill()['assigned'][0]
        self.play_game(id_game)
        self.engine.game_action(self.id_session,self.revision(),id_game,'swap_winner')
        cancelled=self.fill()['assigned'][0]
        self.engine.game_action(self.id_session,self.revision(),cancelled,'cancel',{'reason':'Synthetic cancellation'})
        with self.assertRaises(Problem):
            self.engine.game_action(self.id_session,self.revision(),cancelled,'swap_winner')
        self.engine.close_session(self.id_session,self.revision())
        final=self.state()
        sides={p['id_roster']:p['side'] for p in next(g for g in final['games'] if g['id']==id_game)['players']}
        for player in final['players']:
            self.assertEqual(player['rated_games'],1)
            self.assertEqual(player['games_played'],1)
            if sides[player['id']]=='b':
                self.assertGreater(player['rating'],1200)
            else:
                self.assertLess(player['rating'],1200)

    def test_rebuild_keeps_game_identity_and_other_reserved_court(self):
        self.import_players([1200]*12)
        self.check_all()
        games=self.fill()['assigned']
        before=self.state()
        target=next(g for g in before['games'] if g['id']==games[0])
        other=next(g for g in before['games'] if g['id']==games[1])
        self.engine.game_action(self.id_session,self.revision(),target['id'],'rebuild')
        after=self.state()
        rebuilt=next(g for g in after['games'] if g['id']==target['id'])
        self.assertEqual(rebuilt['court'],target['court'])
        self.assertEqual(rebuilt['status'],'assigned')
        self.assertNotEqual([(p['id_roster'],p['side']) for p in rebuilt['players']],
                            [(p['id_roster'],p['side']) for p in target['players']])
        self.assertEqual(next(g for g in after['games'] if g['id']==other['id']),other)
        self.assertEqual(len(after['games']),len(before['games']))
        self.assertEqual(after['metrics']['on_court'],8)
        self.assertTrue(all(p['games_played']==0 for p in after['players']))
        self.engine.game_action(self.id_session,self.revision(),target['id'],'start')
        with self.assertRaises(Problem):
            self.engine.game_action(self.id_session,self.revision(),target['id'],'rebuild')

    def test_rebuild_without_alternative_rolls_back_plan_and_revision(self):
        self.import_players([1200]*4)
        self.check_all()
        players=self.state()['players']
        self.engine.pair_players(self.id_session,self.revision(),players[0]['id'],players[1]['id'])
        self.engine.pair_players(self.id_session,self.revision(),players[2]['id'],players[3]['id'])
        id_game=self.fill()['assigned'][0]
        before=self.state()
        with self.assertRaisesRegex(Problem,'No alternative valid matchup'):
            self.engine.game_action(self.id_session,self.revision(),id_game,'rebuild')
        self.assertEqual(self.state(),before)

    def test_rebuild_uses_corrected_winners_losers_history(self):
        players=[{'external_id':f'qa:{i}','name':f'QA Player {i}','rating':1200} for i in range(12)]
        self.id_session=self.make_mode_session('winners_losers',players,court_count=1)
        recorded=[]
        for _ in range(3):
            id_game=self.fill()['assigned'][0]
            self.play_game(id_game)
            recorded.append(id_game)
        staged=self.fill()['assigned'][0]
        before=self.state()
        self.engine.game_action(self.id_session,self.revision(),recorded[0],'swap_winner')
        after=self.state()
        self.assertEqual(next(g for g in before['games'] if g['id']==staged),
                         next(g for g in after['games'] if g['id']==staged))
        self.engine.game_action(self.id_session,self.revision(),staged,'rebuild')
        final=self.state()
        game=next(g for g in final['games'] if g['id']==staged)
        outcomes={p['id']:p['last_outcome'] for p in final['players']}
        self.assertEqual(len({outcomes[p['id_roster']] for p in game['players']}),1)
        old_game=next(g for g in before['games'] if g['id']==staged)
        self.assertNotEqual({p['id_roster'] for p in game['players']},
                            {p['id_roster'] for p in old_game['players']})

    def test_rsvp_does_not_queue(self):
        self.import_players()
        self.assertEqual(self.state()['metrics']['waiting'],0)
        self.assertEqual(self.fill()['assigned'],[])

    def test_reviewed_import_stays_absent_and_pairs_are_saved(self):
        players=[{'external_id':f'manual:{i}','name':f'Synthetic Player {i}','rating':1200,
                 'gender':None,'club_group':None} for i in range(4)]
        self.engine.import_reviewed(self.id_session,self.revision(),players,
                                    [['manual:0','manual:1']],'manual','test-review')
        state=self.state()
        self.assertTrue(all(player['attendance']=='absent' for player in state['players']))
        self.assertEqual(state['players'][0]['partner_name'],'Synthetic Player 1')
        self.assertEqual(state['players'][1]['partner_name'],'Synthetic Player 0')
        self.assertEqual(state['metrics']['waiting'],0)

    def test_reviewed_reimport_preserves_rating_and_blocks_active_pair_changes(self):
        players=[{'external_id':f'qa:{i}','name':f'QA Player {i}','rating':1200} for i in range(4)]
        self.id_session=self.make_mode_session('balanced',players,court_count=1)
        id_game=self.fill()['assigned'][0]
        changed=[dict(player,rating=1800) for player in players]
        self.engine.import_reviewed(self.id_session,self.revision(),changed,[],'manual','test-balanced')
        self.assertTrue(all(p['rating']==1200 for p in self.state()['players']))
        before=self.state()
        with self.assertRaises(Problem):
            self.engine.import_reviewed(self.id_session,self.revision(),players,
                                        [['qa:0','qa:1']],'manual','test-balanced')
        self.assertEqual(self.state(),before)
        changed=[dict(player,club_group='A') for player in players]
        with self.assertRaises(Problem):
            self.engine.import_reviewed(self.id_session,self.revision(),changed,[],'manual','test-balanced')
        self.assertEqual(self.state(),before)

    def test_checkin_all_skips_non_yes_rsvps(self):
        players=[{'external_id':f'manual:{i}','name':f'Synthetic Player {i}','rating':1200,
                 'gender':None,'club_group':None} for i in range(4)]
        self.engine.import_reviewed(self.id_session,self.revision(),players,[],'manual','checkin-all')
        with self.engine.connect() as db:
            db.execute("UPDATE roster SET rsvp='no' WHERE id_member=(SELECT id FROM members WHERE external_id='manual:3')")
            db.commit()
        count=self.engine.checkin_all(self.id_session,self.revision())
        self.assertEqual(count,3)
        self.assertEqual(self.state()['metrics']['present'],3)
        self.assertEqual(self.state()['metrics']['waiting'],0)

    def test_pair_preference_is_honored_by_court_fill(self):
        players=[{'external_id':f'manual:{i}','name':f'Synthetic Player {i}','rating':1200,
                 'gender':None,'club_group':None} for i in range(5)]
        self.engine.import_reviewed(self.id_session,self.revision(),players,
                                    [['manual:0','manual:4']],'manual','paired-roster')
        state=self.state()
        for player in state['players']:
            self.engine.player_action(self.id_session,self.revision(),player['id'],'eligibility',
                                     {'membership':'active','waiver':'valid'})
        self.engine.checkin_all(self.id_session,self.revision())
        result=self.fill()
        self.assertEqual(len(result['assigned']),1)
        game=self.state()['games'][0]
        sides={side:{p['id_roster'] for p in game['players'] if p['side']==side} for side in ('a','b')}
        first=next(p['id'] for p in self.state()['players'] if p['external_id']=='manual:0')
        partner=next(p['id'] for p in self.state()['players'] if p['external_id']=='manual:4')
        self.assertTrue(any({first,partner}<=side for side in sides.values()))

    def test_social_mix_plans_one_match_and_waits_for_start(self):
        players=[{'external_id':f'social:{i}','name':f'Social Player {i}','rating':1000+i*200,
                 'gender':None,'club_group':None} for i in range(12)]
        id_session=self.make_mode_session('social_mix',players,court_count=3)
        first=self.engine.fill_courts(id_session,self.engine.state(id_session)['session']['revision'])
        self.assertEqual(len(first['assigned']),1)
        blocked=self.engine.fill_courts(id_session,self.engine.state(id_session)['session']['revision'])
        self.assertEqual(blocked['assigned'],[])
        self.assertIn('start the planned match',blocked['messages'][0])
        id_game=first['assigned'][0]
        self.engine.game_action(id_session,self.engine.state(id_session)['session']['revision'],id_game,'start')
        next_match=self.engine.fill_courts(id_session,self.engine.state(id_session)['session']['revision'])
        self.assertEqual(len(next_match['assigned']),1)

    def test_changing_mode_replans_up_next_and_preserves_live_games_and_queue_places(self):
        self.import_players([1200]*12); self.check_all()
        original=self.fill()['assigned']
        self.assertEqual(len(original),2)
        active_id, staged_id=original
        self.engine.game_action(self.id_session,self.revision(),active_id,'start')
        before=self.state()
        active_before=next(game for game in before['games'] if game['id']==active_id)
        tickets={player['id']:player['ticket'] for player in before['players']}
        next_ticket=before['session']['next_ticket']

        result=self.engine.configure_mode(self.id_session,self.revision(),'social_mix')
        after=self.state()
        active_after=next(game for game in after['games'] if game['id']==active_id)
        staged_after=next(game for game in after['games'] if game['id']==staged_id)
        self.assertEqual((active_after['status'],active_after['players']),
                         (active_before['status'],active_before['players']))
        self.assertEqual(staged_after['status'],'cancelled')
        self.assertEqual(after['session']['mode'],'social_mix')
        self.assertEqual(after['session']['next_ticket'],next_ticket)
        self.assertEqual({player['id']:player['ticket'] for player in after['players']},tickets)
        self.assertEqual(len(result['assigned']),1)
        replacement=next(game for game in after['games'] if game['id']==result['assigned'][0])
        self.assertEqual((replacement['status'],replacement['court']),('assigned',2))
        self.assertTrue(replacement['reason'].startswith('Social Mix:'))

    def test_incompatible_mode_change_releases_staged_players_without_losing_priority(self):
        self.import_players([1800,1750,1200,1150]*2); self.check_all()
        original=self.fill()['assigned']
        active_id, staged_id=original
        self.engine.game_action(self.id_session,self.revision(),active_id,'start')
        before=self.state()
        tickets={player['id']:player['ticket'] for player in before['players']}
        next_ticket=before['session']['next_ticket']

        result=self.engine.configure_mode(self.id_session,self.revision(),'mixed_doubles')
        after=self.state()
        self.assertEqual(result['assigned'],[])
        self.assertTrue(result['messages'])
        self.assertEqual(next(game for game in after['games'] if game['id']==active_id)['status'],'playing')
        self.assertEqual(next(game for game in after['games'] if game['id']==staged_id)['status'],'cancelled')
        self.assertEqual(after['session']['mode'],'mixed_doubles')
        self.assertEqual(after['session']['next_ticket'],next_ticket)
        self.assertEqual({player['id']:player['ticket'] for player in after['players']},tickets)
        self.assertEqual(sum(player['queue_state']=='waiting' for player in after['players']),4)

    def test_skill_courts_assigns_distinct_skill_bands(self):
        players=[{'external_id':f'skill:{i}','name':f'Skill Player {i}','rating':rating,
                 'gender':None,'club_group':None}
                 for i,rating in enumerate([1000]*4+[1600]*4)]
        id_session=self.make_mode_session('skill_courts',players,court_count=2)
        result=self.engine.fill_courts(id_session,self.engine.state(id_session)['session']['revision'])
        self.assertEqual(len(result['assigned']),2)
        state=self.engine.state(id_session)
        bands=[]
        for game in state['games']:
            ratings={player['rating'] for player in game['players']}
            self.assertEqual(len(ratings),1)
            bands.append(next(iter(ratings)))
        self.assertEqual(set(bands),{1000,1600})

    def test_mixed_doubles_mode_requires_confirmed_categories(self):
        players=[{'external_id':f'mixed:{i}','name':f'Mixed Player {i}','rating':1200,
                 'gender':gender,'club_group':None}
                 for i,gender in enumerate(['M','F','M','F'])]
        id_session=self.make_mode_session('mixed_doubles',players,court_count=1)
        result=self.engine.fill_courts(id_session,self.engine.state(id_session)['session']['revision'])
        self.assertEqual(len(result['assigned']),1)
        game=self.engine.state(id_session)['games'][0]
        for side in ('a','b'):
            categories={player['gender'] for player in game['players'] if player['side']==side}
            self.assertEqual(categories,{'M','F'})

    def test_version_one_database_migrates_without_losing_roster(self):
        self.import_players()
        path=self.engine.path
        with self.engine.connect() as db:
            db.execute('DROP TABLE team_pairs')
            db.execute('ALTER TABLE roster DROP COLUMN club_group')
            db.execute('ALTER TABLE members DROP COLUMN gender')
            db.execute('ALTER TABLE sessions DROP COLUMN mode')
            db.execute('PRAGMA user_version=1')
            db.commit()
        migrated=Engine(path,clock=lambda:self.now)
        state=migrated.state(self.id_session)
        self.assertEqual(state['session']['mode'],'balanced')
        self.assertEqual(len(state['players']),4)
        with migrated.connect() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],3)

    def test_unverified_waivers_prevent_queue_but_not_presence(self):
        self.import_players(waiver='unknown')
        self.check_all()
        self.assertEqual(self.state()['metrics']['present'],4)
        self.assertEqual(self.state()['metrics']['waiting'],0)

    def test_eligibility_revoke_removes_waiting_player(self):
        self.import_players();self.check_all()
        p=self.state()['players'][0]
        self.engine.player_action(self.id_session,self.revision(),p['id'],'eligibility',{'membership':'active','waiver':'missing'})
        self.assertEqual(self.state()['metrics']['waiting'],3)

    def test_two_courts_have_eight_unique_players(self):
        self.import_players([1200]*30);self.check_all();self.fill()
        state=self.state()
        assigned=[p['id_roster'] for g in state['games'] for p in g['players']]
        self.assertEqual(len(assigned),8)
        self.assertEqual(len(set(assigned)),8)
        self.assertEqual(state['metrics']['waiting'],22)

    def test_concurrent_fill_one_succeeds_other_conflicts(self):
        self.import_players([1200]*8);self.check_all()
        revision=self.revision()
        def fill():
            try:
                self.engine.fill_courts(self.id_session,revision)
                return 'ok'
            except Problem as error:
                return error.status
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(list(pool.map(lambda _:fill(),range(2))),['ok',409])
        self.assertEqual(self.state()['metrics']['on_court'],8)

    def test_duplicate_result_does_not_repeat_ratings_or_history(self):
        self.import_players();self.check_all();id_game=self.fill()['assigned'][0]
        self.engine.game_action(self.id_session,self.revision(),id_game,'start')
        self.engine.game_action(self.id_session,self.revision(),id_game,'complete',{'score_a':11,'score_b':8})
        with self.assertRaises(Problem):
            self.engine.game_action(self.id_session,self.revision(),id_game,'complete',{'score_a':11,'score_b':8})
        self.assertEqual(self.state()['metrics']['completed_games'],1)
        self.assertEqual(sum(p['games_played'] for p in self.state()['players']),4)
        self.engine.close_session(self.id_session,self.revision())
        with self.assertRaises(Problem):
            self.engine.close_session(self.id_session,self.revision())
        with self.engine.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM rating_history').fetchone()[0],4)

    def test_cancel_returns_original_wait_priority_without_rating(self):
        self.import_players([1200]*8);self.check_all()
        tickets={p['id']:p['ticket'] for p in self.state()['players']}
        ids=self.fill()['assigned']
        self.engine.game_action(self.id_session,self.revision(),ids[0],'cancel',{'reason':'Player needs a break'})
        for p in self.state()['players']:
            self.assertEqual(p['ticket'],tickets[p['id']])
        self.assertEqual(self.state()['metrics']['completed_games'],0)

    def test_late_player_joins_back_and_prior_no_show_clears(self):
        self.import_players()
        self.engine.player_action(self.id_session,self.revision(),self.state()['players'][0]['id'],'checkin')
        self.now+=31*60
        self.engine.reconcile(self.id_session,self.revision())
        self.assertEqual(self.state()['metrics']['no_shows'],3)
        late=self.state()['players'][-1]
        self.engine.player_action(self.id_session,self.revision(),late['id'],'checkin')
        p=next(p for p in self.state()['players'] if p['id']==late['id'])
        self.assertEqual(p['position'],2)
        self.assertTrue(p['is_late'])
        self.assertEqual(self.state()['metrics']['no_shows'],2)

    def test_reimport_is_idempotent_preserves_attendance_and_ratings(self):
        self.import_players();self.check_all()
        self.import_players([2000]*4)
        self.assertEqual(len(self.state()['players']),4)
        self.assertEqual(self.state()['metrics']['waiting'],4)
        self.assertEqual(sorted(p['rating'] for p in self.state()['players']),[1150,1200,1750,1800])

    def test_invalid_import_rolls_back_all_rows(self):
        content=csv_roster().replace('Player 4,yes,active,valid','Player 4,yes,active,nope')
        with self.assertRaises(Problem):
            self.engine.import_roster(self.id_session,self.revision(),content,'manual','club')
        self.assertEqual(self.state()['players'],[])
        self.assertEqual(self.revision(),0)

    def test_partial_csv_is_rejected_cleanly(self):
        with self.assertRaises(Problem):
            self.engine.import_roster(self.id_session,self.revision(),'external_id,name,rsvp,membership,waiver\nx,Name','manual','club')

    def test_ineligible_assigned_import_rolls_back_member_name(self):
        self.import_players();self.check_all();self.fill()
        with self.assertRaises(Problem):
            self.engine.import_roster(self.id_session,self.revision(),csv_roster(waiver='missing'),'manual','test-club')
        self.assertTrue(all(p['waiver']=='valid' for p in self.state()['players']))

    def test_cannot_leave_assigned_court(self):
        self.import_players();self.check_all();self.fill()
        with self.assertRaises(Problem):
            self.engine.player_action(self.id_session,self.revision(),self.state()['players'][0]['id'],'checkout')

    def test_capacity_limits_checkins(self):
        with self.engine.connect() as db:
            db.execute('UPDATE sessions SET max_players=4 WHERE id=?',(self.id_session,))
        self.import_players([1200]*5)
        for p in self.state()['players'][:4]:
            self.engine.player_action(self.id_session,self.revision(),p['id'],'checkin')
        with self.assertRaises(Problem):
            self.engine.player_action(self.id_session,self.revision(),self.state()['players'][-1]['id'],'checkin')

    def test_results_only_change_ratings_at_close(self):
        self.import_players();self.check_all();id_game=self.fill()['assigned'][0]
        original={p['id']:p['rating'] for p in self.state()['players']}
        self.engine.game_action(self.id_session,self.revision(),id_game,'start')
        self.engine.game_action(self.id_session,self.revision(),id_game,'complete',{'score_a':11,'score_b':2})
        self.assertEqual({p['id']:p['rating'] for p in self.state()['players']},original)
        self.engine.close_session(self.id_session,self.revision())
        self.assertNotEqual({p['id']:p['rating'] for p in self.state()['players']},original)

    def test_late_checkout_does_not_become_no_show(self):
        self.import_players();self.check_all()
        p=self.state()['players'][0]
        self.engine.player_action(self.id_session,self.revision(),p['id'],'checkout')
        self.now+=3600
        self.engine.reconcile(self.id_session,self.revision())
        self.assertEqual(self.state()['metrics']['no_shows'],0)

    def test_demo_cannot_mix_with_real_roster(self):
        self.import_players()
        with self.assertRaises(Problem):
            self.engine.demo(self.id_session,self.revision())

    def test_real_import_cannot_mix_with_demo(self):
        self.engine.demo(self.id_session,self.revision())
        with self.assertRaises(Problem):
            self.import_players()
        self.assertEqual(len(self.state()['players']),30)

    def test_history_survives_between_sessions_with_stable_identities(self):
        self.import_players([1200]*4);self.check_all();id_game=self.fill()['assigned'][0]
        old=self.state()['games'][0]
        self.engine.game_action(self.id_session,self.revision(),id_game,'start')
        self.engine.game_action(self.id_session,self.revision(),id_game,'complete',{'score_a':11,'score_b':9})
        self.engine.close_session(self.id_session,self.revision())
        self.id_session=self.engine.create_session({'name':'Next session','starts_at':self.now})
        self.import_players([1200]*4)
        current={p['id_member']:p['id'] for p in self.state()['players']}
        with self.engine.connect() as db:
            prior={p['id']:p['id_member'] for p in db.execute('SELECT id,id_member FROM roster WHERE id_session=?',(old['id_session'],))}
            partners,opponents=self.engine.histories(db,self.id_session)
        team_a=[current[prior[p['id_roster']]] for p in old['players'] if p['side']=='a']
        team_b=[current[prior[p['id_roster']]] for p in old['players'] if p['side']=='b']
        self.assertEqual(partners[tuple(sorted(team_a))],1)
        self.assertEqual(partners[tuple(sorted(team_b))],1)
        self.assertEqual(len(opponents),4)

    def test_close_classifies_absent_rsvps_once_grace_passes(self):
        self.import_players();self.now+=31*60
        self.engine.close_session(self.id_session,self.revision())
        self.assertEqual(self.state()['metrics']['no_shows'],4)

    def test_member_cannot_play_in_two_unclosed_periods(self):
        self.import_players();self.check_all();id_game=self.fill()['assigned'][0]
        self.engine.game_action(self.id_session,self.revision(),id_game,'start')
        self.engine.game_action(self.id_session,self.revision(),id_game,'complete',{'score_a':11,'score_b':9})
        for p in self.state()['players']:
            self.engine.player_action(self.id_session,self.revision(),p['id'],'checkout')
        self.id_session=self.engine.create_session({'name':'Overlap','starts_at':self.now})
        self.import_players()
        with self.assertRaises(Problem):
            self.engine.player_action(self.id_session,self.revision(),self.state()['players'][0]['id'],'checkin')

    def test_reopen_persistent_database_preserves_roster(self):
        self.import_players()
        another=Engine(self.engine.path)
        self.assertEqual(len(another.state(self.id_session)['players']),4)


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.engine=Engine(Path(self.directory.name)/'api.sqlite3')
        self.server=serve(self.engine,0)
        self.port=self.server.server_address[1]
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.directory.cleanup()

    def test_json_api_and_error_contract(self):
        request=Request(f'http://127.0.0.1:{self.port}/api/sessions',data=json.dumps({'name':'API session'}).encode(),headers={'Content-Type':'application/json'})
        with urlopen(request) as response:
            self.assertEqual(response.status,201)
            self.assertEqual(json.load(response)['session']['name'],'API session')

    def test_matching_mode_route_returns_updated_session(self):
        request=Request(f'http://127.0.0.1:{self.port}/api/sessions',data=json.dumps({'name':'Mode API session'}).encode(),headers={'Content-Type':'application/json'})
        with urlopen(request) as response:
            state=json.load(response)
        id_session=state['session']['id']
        request=Request(f'http://127.0.0.1:{self.port}/api/sessions/{id_session}/configure',
                        data=json.dumps({'revision':state['session']['revision'],'mode':'social_mix'}).encode(),
                        headers={'Content-Type':'application/json'})
        with urlopen(request) as response:
            changed=json.load(response)
        self.assertEqual(changed['session']['mode'],'social_mix')
        self.assertIn('queue places are preserved',changed['notice'])

    def test_foreign_origin_cannot_mutate(self):
        request=Request(f'http://127.0.0.1:{self.port}/api/sessions',data=b'{"name":"Bad"}',headers={'Content-Type':'application/json','Origin':'https://other.example'})
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code,403)
        error.exception.close()
        self.assertEqual(self.engine.list_sessions(),[])

    def test_static_assets_and_missing_route(self):
        for path in ('/','/app.js','/styles.css','/favicon.svg','/fonts/patrick-hand-latin.woff2'):
            with urlopen(f'http://127.0.0.1:{self.port}{path}') as response:
                self.assertEqual(response.status,200)
                self.assertIn("frame-ancestors 'none'",response.headers['Content-Security-Policy'])
                if path.endswith('.woff2'):
                    self.assertEqual(response.headers['Content-Type'],'font/woff2')
        with self.assertRaises(HTTPError) as error:
            urlopen(f'http://127.0.0.1:{self.port}/../../etc/passwd')
        self.assertEqual(error.exception.code,404)
        error.exception.close()


if __name__=='__main__':
    unittest.main()
