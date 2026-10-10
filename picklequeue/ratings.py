"""Glicko-2 period updates; doubles observations are an explicit approximation."""

from dataclasses import dataclass
from math import exp, isfinite, log, pi, sqrt

SCALE = 173.7178


@dataclass(frozen=True)
class Rating:
    value: float = 1200.0
    deviation: float = 350.0
    volatility: float = 0.06


def update_rating(player: Rating, results, tau=0.5) -> Rating:
    """Apply one period of (opponent Rating, score) observations."""
    mu = (player.value - 1500) / SCALE
    phi = player.deviation / SCALE
    if not (isfinite(mu) and phi > 0 and player.volatility > 0 and tau > 0):
        raise ValueError("Invalid rating parameters")
    if not results:
        return Rating(player.value, SCALE * sqrt(phi * phi + player.volatility**2), player.volatility)
    information = improvement = 0.0
    for opponent, score in results:
        if score not in (0, 0.5, 1):
            raise ValueError("Rating score must be 0, 0.5, or 1")
        g = 1 / sqrt(1 + 3 * (opponent.deviation / SCALE)**2 / pi**2)
        exponent = max(-700, min(700, -g * (mu - (opponent.value - 1500) / SCALE)))
        expected = 1 / (1 + exp(exponent))
        information += g * g * expected * (1 - expected)
        improvement += g * (score - expected)
    if information <= 0:
        raise ValueError("Rating observations have no usable information")
    variance = 1 / information
    delta = variance * improvement
    a = log(player.volatility**2)

    def f(x):
        e = exp(x)
        total = phi * phi + variance + e
        return e * (delta * delta - phi * phi - variance - e) / (2 * total * total) - (x - a) / tau**2

    left = a
    if delta * delta > phi * phi + variance:
        right = log(delta * delta - phi * phi - variance)
    else:
        k = 1
        while f(a - k * tau) < 0:
            k += 1
            if k > 1000:
                raise ValueError("Could not bracket volatility")
        right = a - k * tau
    fl, fr = f(left), f(right)
    for _ in range(1000):
        if abs(right - left) <= 0.000001:
            break
        c = left + (left - right) * fl / (fr - fl)
        fc = f(c)
        if fc * fr <= 0:
            left, fl = right, fr
        else:
            fl /= 2
        right, fr = c, fc
    else:
        raise ValueError("Volatility did not converge")
    sigma = exp(left / 2)
    phi_star = sqrt(phi * phi + sigma * sigma)
    next_phi = 1 / sqrt(1 / phi_star**2 + 1 / variance)
    return Rating(SCALE * (mu + next_phi**2 * improvement) + 1500, SCALE * next_phi, sigma)


def doubles_opponent(player: Rating, partner: Rating, opponents) -> Rating:
    """Opponent strength adjusted for partner support; not canonical doubles Glicko."""
    a, b = opponents
    return Rating(
        a.value + b.value - partner.value,
        sqrt(a.deviation**2 + b.deviation**2 + partner.deviation**2),
        0.06,
    )
