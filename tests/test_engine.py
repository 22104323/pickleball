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

    def test_rsvp_does_not_queue(self):
        self.import_players()
        self.assertEqual(self.state()['metrics']['waiting'],0)
        self.assertEqual(self.fill()['assigned'],[])

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

    def test_foreign_origin_cannot_mutate(self):
        request=Request(f'http://127.0.0.1:{self.port}/api/sessions',data=b'{"name":"Bad"}',headers={'Content-Type':'application/json','Origin':'https://other.example'})
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code,403)
        error.exception.close()
        self.assertEqual(self.engine.list_sessions(),[])

    def test_static_assets_and_missing_route(self):
        for path in ('/','/app.js','/styles.css','/favicon.svg'):
            with urlopen(f'http://127.0.0.1:{self.port}{path}') as response:
                self.assertEqual(response.status,200)
                self.assertIn("frame-ancestors 'none'",response.headers['Content-Security-Policy'])
        with self.assertRaises(HTTPError) as error:
            urlopen(f'http://127.0.0.1:{self.port}/../../etc/passwd')
        self.assertEqual(error.exception.code,404)
        error.exception.close()


if __name__=='__main__':
    unittest.main()
