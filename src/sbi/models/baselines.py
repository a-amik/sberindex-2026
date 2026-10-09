"""Эталоны. Каждая модель — функция (hist, t0, steps, ctx) -> ряды × steps."""
from __future__ import annotations

import numpy as np


def naive(hist, t0, steps, ctx):
    return np.repeat(hist[:, -1:], steps, axis=1)


def snaive(hist, t0, steps, ctx):
    """Значение того же месяца год назад. С точки 2023-12 «год назад» уже есть у всех шагов."""
    return np.stack([hist[:, t0 + h - 12] for h in range(1, steps + 1)], axis=1)


def snaive_growth(hist, t0, steps, ctx):
    """Год назад × темп роста г/г за последние месяцы.

    Темп — среднее геометрическое отношений y_t / y_{t−12} за последние
    `months` месяцев, где оно уже считается. С точки 2023-12 своего темпа нет:
    берём темп РФ по ближайшей категории из ряда СберИндекса на ту же дату.
    """
    k = ctx["months"]
    avail = [t for t in range(t0 - k + 1, t0 + 1) if t - 12 >= 0]
    if avail:
        ratios = np.stack([hist[:, t] / hist[:, t - 12] for t in avail], axis=1)
        g = np.exp(np.log(ratios).mean(axis=1))
    else:
        g = ctx["national_growth"](t0)
    return snaive(hist, t0, steps, ctx) * g[:, None]


def ar1(hist, t0, steps, ctx):
    """AR(1) по месячному лог-приросту, по каждому ряду, без сезонности —
    эталон, который у Norges Bank бил большинство внешних предикторов."""
    d = np.diff(np.log(hist), axis=1)
    x, y = d[:, :-1], d[:, 1:]
    xm, ym = x.mean(axis=1, keepdims=True), y.mean(axis=1, keepdims=True)
    phi = ((x - xm) * (y - ym)).sum(axis=1) / np.clip(((x - xm) ** 2).sum(axis=1), 1e-12, None)
    phi = np.clip(phi, -0.99, 0.99)
    c = ym[:, 0] - phi * xm[:, 0]
    last, lv = d[:, -1], np.log(hist[:, -1])
    out = []
    for _ in range(steps):
        last = c + phi * last
        lv = lv + last
        out.append(np.exp(lv))
    return np.stack(out, axis=1)


MODELS = {"naive": naive, "snaive": snaive, "snaive_growth": snaive_growth, "ar1": ar1}
