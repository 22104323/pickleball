"""Deterministic doubles assignment with oldest-player protection."""

from itertools import combinations
from math import pow


def split_cost(teams, partner_counts, opponent_counts, mode='balanced'):
    a, b = teams
    mean_a = sum(p['rating'] for p in a) / 2
    mean_b = sum(p['rating'] for p in b) / 2
    delta = abs(mean_a - mean_b)
    expected = 1 / (1 + pow(10, (mean_b - mean_a) / 400))
    partner_repeat = sum(partner_counts.get(tuple(sorted((t[0]['id'], t[1]['id']))), 0) for t in teams)
    opponent_repeat = sum(opponent_counts.get(tuple(sorted((x['id'], y['id']))), 0) for x in a for y in b)
    internal_gap = (abs(a[0]['rating'] - a[1]['rating']) + abs(b[0]['rating'] - b[1]['rating'])) / 2
    if mode == 'social_mix':
        cost = 8 * partner_repeat + 2 * opponent_repeat
    else:
        cost = 8 * delta / 75 + 4 * internal_gap / 350 + 3 * partner_repeat + 2 * opponent_repeat
    return {'cost': cost, 'delta': delta, 'expected': expected,
            'partner_repeats': partner_repeat, 'opponent_repeats': opponent_repeat}


def choose_game(players, partner_counts=None, opponent_counts=None, window=12, mode='balanced', excluded_teams=None):
    """Require the oldest player, expand once if no acceptable split exists."""
    if len(players) < 4:
        return None
    partner_counts, opponent_counts = partner_counts or {}, opponent_counts or {}
    excluded = tuple(sorted(tuple(sorted(team)) for team in excluded_teams)) if excluded_teams else None
    ordered = sorted(players, key=lambda p: (p['ticket'], p['id']))
    anchor = ordered[0]
    for size in sorted(set((min(window, len(ordered)), min(16, len(ordered))))):
        pool_ids = {p['id'] for p in ordered[:size]}
        # Pair preferences are a hard constraint once either player is selected.
        # Pull the other half into the candidate pool even when they sit just
        # beyond the normal wait-priority window.
        for player in ordered[:size]:
            partner = player.get('paired_with')
            if partner is not None and partner not in pool_ids:
                paired_player = next((p for p in ordered if p['id'] == partner), None)
                if paired_player is not None:
                    pool_ids.add(partner)
        pool = [p for p in ordered if p['id'] in pool_ids]
        positions = {p['id']: i for i, p in enumerate(ordered)}
        best = None
        for others in combinations(pool[1:], 3):
            quartet = (anchor, *others)
            quartet_ids = {p['id'] for p in quartet}
            if any(p.get('paired_with') is not None and p['paired_with'] not in quartet_ids for p in quartet):
                continue
            for partner_index in (1, 2, 3):
                team_a = (anchor, quartet[partner_index])
                team_b = tuple(p for i, p in enumerate(quartet) if i not in (0, partner_index))
                team_by_player = {p['id']: side for side, team in enumerate((team_a, team_b)) for p in team}
                if any(p.get('paired_with') is not None and
                       team_by_player[p['id']] != team_by_player.get(p['paired_with']) for p in quartet):
                    continue
                if mode == 'mixed_doubles':
                    if sorted(p.get('gender') or '' for p in quartet) != ['F','F','M','M']:
                        continue
                    if any({p.get('gender') for p in team} != {'M','F'} for team in (team_a, team_b)):
                        continue
                if mode == 'club_wars':
                    groups_a = {p.get('club_group') for p in team_a}
                    groups_b = {p.get('club_group') for p in team_b}
                    if len(groups_a) != 1 or len(groups_b) != 1 or groups_a == groups_b or None in groups_a | groups_b:
                        continue
                if excluded == tuple(sorted(tuple(sorted(p['id'] for p in team)) for team in (team_a, team_b))):
                    continue
                stats = split_cost((team_a, team_b), partner_counts, opponent_counts, mode)
                if mode != 'social_mix' and (stats['delta'] > 150 or not .40 <= stats['expected'] <= .60):
                    continue
                skip_cost = sum(positions[p['id']] for p in quartet) - 6
                first_game_bonus = sum(p.get('games_played',1) == 0 and
                                        (mode == 'social_mix' or p.get('rated_games',10) < 10)
                                        for p in quartet) / 2
                cost = stats['cost'] + skip_cost - first_game_bonus
                key = ((cost, stats['partner_repeats'], stats['opponent_repeats'], tuple(p['id'] for p in (*team_a, *team_b)))
                       if mode == 'social_mix' else (cost, stats['delta'], tuple(p['id'] for p in (*team_a, *team_b))))
                if best is None or key < best['key']:
                    best = {'teams': (team_a, team_b), **stats,
                            'expected': .5 if mode == 'social_mix' else stats['expected'],
                            'cost': cost, 'key': key,
                            'window': size, 'reason': 'Oldest waiting player included; balanced teams and recent pairing history.'}
        if best is not None:
            return best
    return None
