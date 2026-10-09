"""Модели на панели: ряд МО = общий фактор × отклонение МО.

В логарифмах: log y[i,t] = m[g,t] + d[i,t], где m[g,t] — медиана логарифма
по рядам группы g в месяце t (группа — категория или категория × тип
поселения), d — отклонение МО от неё. 24 точек на ряд мало, чтобы оценить
сезонность ряда, а в одном месяце наблюдаются сразу все МО: сезонность
и тренд занимаются поперёк панели, на уровне МО прогнозируется только
отклонение.

Фактор прогнозируется так:
* panel — сезонность самой панели: m[T+h−12] плюс средний рост фактора
  г/г за последние месяцы (с точки 2023-12 — рост РФ из ряда СберИндекса);
* national — сезонный профиль общероссийского ряда СберИндекса за
  2019—T без 2020 года плюс тренд;
* blend — среднее двух.

Отклонение:
* last — последнее значение (контроль: модель без единого параметра МО);
* ses — экспоненциальное сглаживание с постоянной alpha;
* ses_seas — то же плюс доля w прошлогоднего сезонного отклонения:
  курортный МО летом отходит от фактора иначе, чем зимой.

Всё считается только по данным до точки прогноза.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

URBAN = {"городской округ", "внутригородская территория города федерального значения"}


def groups(index: pd.DataFrame, mo: pd.DataFrame, by: str) -> np.ndarray:
    cat = index.category.astype(str).to_numpy()
    if by == "category":
        return cat
    t = index.merge(mo[["territory_id", "mo_type"]], on="territory_id", how="left").mo_type
    kind = np.where(t.isin(URBAN), "город", "район")
    return np.char.add(np.char.add(cat.astype(str), "|"), kind.astype(str))


def _seasonal_profile(level: pd.Series, upto: str) -> pd.Series:
    """Сезонный профиль ряда в логарифмах: отклонение от центрированной
    скользящей средней 2×12, медиана по годам, без 2020-го; сумма по месяцам — ноль."""
    s = np.log(level[level.index <= upto])
    trend = s.rolling(12, center=True).mean().rolling(2).mean().shift(-1)
    dev = (s - trend).dropna()
    dev = dev[~dev.index.str.startswith("2020")]
    prof = dev.groupby(dev.index.str[5:7]).median()
    return prof - prof.mean()


def make(ctx: dict, factor: str = "panel", dev: str = "ses", by: str = "category",
         alpha: float = 0.5, w: float = 0.5, months: int = 3):
    g_all = ctx["groups"][by]
    names = np.unique(g_all)
    periods = ctx["periods"]
    nat = ctx["national"]

    def parts(hist, t0, steps, cx):
        """Фактор и отклонение по отдельности: прогноз фактора, прогноз отклонения,
        история фактора и история отклонения (всё в логарифмах)."""
        lh = np.log(hist)
        m = np.zeros_like(lh)
        for g in names:
            sel = g_all == g
            m[sel] = np.median(lh[sel], axis=0)
        d = lh - m

        # — прогноз фактора по группам
        fac = np.zeros((hist.shape[0], steps))
        avail = [t for t in range(t0 - months + 1, t0 + 1) if t - 12 >= 0]
        nat_growth = np.log(cx["national_growth"](t0))       # рост РФ г/г по ряду, на точку T
        for g in names:
            sel = np.where(g_all == g)[0]
            mg = m[sel[0]]
            if avail:
                gr = np.mean([mg[t] - mg[t - 12] for t in avail])
            else:
                gr = np.median(nat_growth[sel])
            f_panel = np.array([mg[t0 + h - 12] + gr for h in range(1, steps + 1)])
            if factor == "panel":
                f = f_panel
            else:
                ntype = cx["national_type"][g.split("|")[0]]
                prof = _seasonal_profile(nat[f"spend_bn:{ntype}"].dropna(), periods[t0])
                mon = lambda t: periods[t][5:7] if t < len(periods) else str((int(periods[-1][5:7]) + t - len(periods)) % 12 + 1).zfill(2)
                f_nat = np.array([mg[t0] + prof[mon(t0 + h)] - prof[mon(t0)] + gr * h / 12
                                  for h in range(1, steps + 1)])
                f = f_nat if factor == "national" else (f_nat + f_panel) / 2
            fac[sel] = f

        # — прогноз отклонения
        if dev == "last":
            dd = np.repeat(d[:, -1:], steps, axis=1)
        else:
            lvl = d[:, 0].copy()
            for t in range(1, d.shape[1]):
                lvl = alpha * d[:, t] + (1 - alpha) * lvl
            dd = np.repeat(lvl[:, None], steps, axis=1)
            if dev == "ses_seas":
                # прошлогоднее сезонное отклонение: d[t+h−12] против среднего d того года
                base = d[:, max(0, t0 - 11): t0 + 1].mean(axis=1)
                seas = np.stack([d[:, t0 + h - 12] - base for h in range(1, steps + 1)], axis=1)
                dd = dd + w * seas
        return fac, dd, m, d

    def model(hist, t0, steps, cx):
        fac, dd, _, _ = parts(hist, t0, steps, cx)
        return np.exp(fac + dd)
    model.parts = parts
    return model


def variants(ctx: dict) -> dict:
    out = {}
    for by in ("category", "type"):
        tag = "" if by == "category" else "_bytype"
        out[f"factor_only{tag}"] = make(ctx, "panel", "last", by)
        for factor in ("panel", "national", "blend"):
            out[f"panel_{factor}_ses{tag}"] = make(ctx, factor, "ses", by)
            out[f"panel_{factor}_sesseas{tag}"] = make(ctx, factor, "ses_seas", by)
    return out
