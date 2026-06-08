from __future__ import annotations


def rounded_money(value: float) -> float:
    return round(float(value), 2)


def krw(value: float) -> float:
    return round(float(value), 0)
