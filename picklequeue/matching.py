"""Deterministic doubles assignment with oldest-player protection."""

from itertools import combinations
from math import pow


def split_cost(teams, partner_counts, opponent_counts):
    a, b = teams
    mean_a = sum(p['rating'] for p in a) / 2
    mean_b = sum(p['rating'] for p in b) / 2
    delta = abs(mean_a - mean_b)
    expected = 1 / (1 + pow(10, (mean_b - mean_a) / 400))
    partner_repeat = sum(partner_counts.get(tuple(sorted((t[0]['id'], t[1]['id']))), 0) for t in teams)
    opponent_repeat = sum(opponent_counts.get(tuple(sorted((x['id'], y['id']))), 0) for x in a for y in b)
    internal_gap = (abs(a[0]['rating'] - a[1]['rating']) + abs(b[0]['rating'] - b[1]['rating'])) / 2
    cost = 8 * delta / 75 + 4 * internal_gap / 350 + 3 * partner_repeat + 2 * opponent_repeat
    return {'cost': cost, 'delta': delta, 'expected': expected,
            'partner_repeats': partner_repeat, 'opponent_repeats': opponent_repeat}


def choose_game(players, partner_counts=None, opponent_counts=None, window=12):
    """Require the oldest player, expand once if no acceptable split exists."""
    if len(players) < 4:
        return None
    partner_counts, opponent_counts = partner_counts or {}, opponent_counts or {}
    ordered = sorted(players, key=lambda p: (p['ticket'], p['id']))
    anchor = ordered[0]
    for size in sorted(set((min(window, len(ordered)), min(16, len(ordered))))):
        pool = ordered[:size]
        positions = {p['id']: i for i, p in enumerate(pool)}
        best = None
        for others in combinations(pool[1:], 3):
            quartet = (anchor, *others)
            for partner_index in (1, 2, 3):
                team_a = (anchor, quartet[partner_index])
                team_b = tuple(p for i, p in enumerate(quartet) if i not in (0, partner_index))
                stats = split_cost((team_a, team_b), partner_counts, opponent_counts)
                if stats['delta'] > 150 or not .40 <= stats['expected'] <= .60:
                    continue
                skip_cost = sum(positions[p['id']] for p in quartet) - 6
                first_game_bonus = sum(p.get('rated_games',10) < 10 and p.get('games_played',1) == 0 for p in quartet) / 2
                cost = stats['cost'] + skip_cost - first_game_bonus
                key = (cost, stats['delta'], tuple(p['id'] for p in (*team_a, *team_b)))
                if best is None or key < best['key']:
                    best = {'teams': (team_a, team_b), **stats, 'cost': cost, 'key': key,
                            'window': size, 'reason': 'Oldest waiting player included; balanced teams and recent pairing history.'}
        if best is not None:
            return best
    return None
