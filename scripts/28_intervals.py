"""Конформные интервалы для итогового прогноза.

У ансамбля только точечный прогноз. Интервал на точке T строится из лог-ошибок
прошлых прогнозов той же категории и того же шага, чьи цели уже наступили
к T (цель ≤ T): квантили остатков по модулю на 80 и 90 %. Для шага, у которого
ошибки пришли меньше чем из трёх точек прогноза (ошибки одной точки связаны
общим шоком месяца и занижают ширину), ширина берётся с последнего обеспеченного шага h0
и растёт как √(h/h0): первая версия брала ошибки коротких шагов как есть,
и на шестом шаге интервал на 90 % накрывал только 81 % фактов. Отчёт — покрытие
и средняя ширина в отчётном окне (точки с июня 2024 года) по горизонтам
и категориям; для сравнения — интервалы Chronos-2, если они сохранены.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sbi import backtest  # noqa: E402

OUT = ROOT / "results/signal_value"
REPORT_FROM = "2024-06"
LEVELS = (0.8, 0.9)


def main():
    panel = backtest.load_panel(ROOT / "data/processed")
    cats = panel.index.category.astype(str).to_numpy()
    f = pd.read_parquet(OUT / "fc_ensemble+robust.parquet")
    f["category"] = cats[f.row.to_numpy()]
    f["r"] = np.abs(np.log(f.y / f.yhat))
    out = []
    for o in sorted(f.origin.unique()):
        cur = f[f.origin == o].copy()
        past = f[f.target <= o]
        for c, cpart in cur.groupby("category"):
            pc = past[past.category == c]
            # квантили по шагам, где своих ошибок хватает; дальше — рост ширины с шагом по корню
            known = {h: {lv: np.quantile(pc[pc.step == h].r, lv) for lv in LEVELS}
                     for h in sorted(pc.step.unique()) if pc[pc.step == h].origin.nunique() >= 3}
            for h, part in cpart.groupby("step"):
                for lv in LEVELS:
                    if h in known:
                        q = known[h][lv]
                    elif known:
                        h0 = max(known)
                        q = known[h0][lv] * np.sqrt(h / h0)
                    else:
                        res = pc[pc.step <= h].r
                        q = np.quantile(res, lv) if len(res) >= 100 else np.nan
                    cur.loc[part.index, f"q{int(lv * 100)}"] = q
        out.append(cur)
    g = pd.concat(out)
    rep = g[(g.origin >= REPORT_FROM)].dropna(subset=["q80", "q90"])
    rows = []
    for H in (1, 3, 6):
        d = rep[rep.step == H]
        for lv in LEVELS:
            q = d[f"q{int(lv * 100)}"]
            inside = d.r <= q
            width = (d.yhat * (np.exp(q) - np.exp(-q))) / d.y
            rows.append({"шаг": H, "уровень": lv, "покрытие": inside.mean(), "ширина_доля_факта": width.median(), "n": len(d)})
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "intervals.csv", index=False)
    bycat = rep[rep.step == 1].groupby("category").apply(lambda d: pd.Series({"покрытие90": (d.r <= d.q90).mean(), "ширина90": (np.exp(d.q90) - np.exp(-d.q90)).median()}))
    bycat.to_csv(OUT / "intervals_by_category.csv")
    print("точек без интервала (мало прошлых ошибок):", int(g[g.origin >= REPORT_FROM].q90.isna().sum()))
    print(res.round(3).to_string(index=False))
    print(bycat.round(3).to_string())


if __name__ == "__main__":
    main()
