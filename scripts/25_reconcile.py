"""Согласование категорий: «Все категории» и сумма пяти категорий.

Пять категорий набора — около 72 % «Всех категорий», и доля эта у МО
устойчива: стандартное отклонение по месяцам 1,9 п.п., месячное изменение
около 1 п.п. Значит, у «Всех категорий» две оценки: прямой прогноз A и сумма
прогнозов категорий C, делённая на долю s (средняя доля трёх последних месяцев
до точки прогноза). Согласованный итог Â = λ·A + (1 − λ)·C/s. Категории
подтягиваются к нему множителем (Â·s / C)^κ.

λ из (1; 0,75; 0,5; 0,25; 0) и κ из (0; 0,5; 1) выбираются на целях до мая 2024 года
по MAE всех рядов; отчёт — по точкам с июня. Базы — ансамбль и ансамбль
со всеми сигналами дня.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sbi import backtest, metrics  # noqa: E402

OUT = ROOT / "results/signal_value"
LAST, REPORT_FROM = "2024-12", "2024-06"
COLS = ["row", "origin", "step", "target", "y", "y_origin", "yhat"]
ALL = "Все категории"


def shares(panel) -> pd.DataFrame:
    """Доля пяти категорий во «Всех» по МО и месяцу — по факту, только для истории до точки."""
    idx = panel.index.assign(category=panel.index.category.astype(str))
    y = pd.DataFrame(panel.y, columns=panel.periods)
    y["territory_id"], y["category"] = idx.territory_id.to_numpy(), idx.category.to_numpy()
    allv = y[y.category == ALL].set_index("territory_id")[panel.periods]
    cats = y[y.category != ALL].groupby("territory_id")[panel.periods].sum(min_count=5)
    return (cats / allv).dropna(how="all")


def apply(f: pd.DataFrame, idx: pd.DataFrame, sh: pd.DataFrame, lam: float, kap: float) -> pd.DataFrame:
    g = f.merge(idx, on="row")
    is_all = g.category == ALL
    a = g[is_all].set_index(["territory_id", "origin", "step"]).yhat
    c = g[~is_all].groupby(["territory_id", "origin", "step"]).yhat.agg(["sum", "size"])
    c = c[c["size"] == 5]["sum"]
    key = pd.MultiIndex.from_frame(c.index.to_frame()[["territory_id", "origin"]])
    s = pd.Series([sh.loc[t, [str(pd.Period(o, "M") - k) for k in range(3)]].mean() if t in sh.index else np.nan
                   for t, o in key], index=c.index)
    j = pd.concat({"a": a, "c": c, "s": s}, axis=1).dropna()
    j["ahat"] = lam * j.a + (1 - lam) * j.c / j.s
    j["kc"] = (j.ahat * j.s / j.c) ** kap
    g = g.join(j[["ahat", "kc"]], on=["territory_id", "origin", "step"])
    g["yhat"] = np.where(is_all & g.ahat.notna(), g.ahat, np.where(~is_all & g.kc.notna(), g.yhat * g.kc, g.yhat))
    return g[COLS]


def main():
    panel = backtest.load_panel(ROOT / "data/processed")
    idx = panel.index.assign(category=panel.index.category.astype(str), row=np.arange(len(panel.index)))[["row", "territory_id", "category"]]
    sh = shares(panel)
    rows = []
    for name, path in [("ensemble", ROOT / "results/forecasts/ensemble.parquet"),
                       ("ensemble+signals+age", OUT / "fc_ensemble+signals+age.parquet")]:
        f = pd.read_parquet(path)[COLS]
        sel = f[f.target <= "2024-05"]
        grid = {}
        for lam in (1.0, 0.75, 0.5, 0.25, 0.0):
            for kap in (0.0, 0.5, 1.0):
                g = apply(sel, idx, sh, lam, kap)
                grid[(lam, kap)] = (g.yhat - g.y).abs().mean()
        best = min(grid, key=grid.get)
        print(name, "λ, κ →", best, {k: round(v, 1) for k, v in sorted(grid.items(), key=lambda kv: kv[1])[:4]})
        g = apply(f, idx, sh, *best)
        g.to_parquet(OUT / f"fc_{name}+reconcile.parquet")
        cat = idx.set_index("row").category
        for H in (1, 3, 6):
            r = metrics.compare(g[g.origin >= REPORT_FROM], f[f.origin >= REPORT_FROM], H, LAST, 2000, 42)
            rows.append({"base": name, "lam": best[0], "kap": best[1], **r})
        rep = g[(g.origin >= REPORT_FROM) & (g.step <= 3)].assign(cat=lambda d: d.row.map(cat))
        ref = f[(f.origin >= REPORT_FROM) & (f.step <= 3)].assign(cat=lambda d: d.row.map(cat))
        print((ref.assign(e=(ref.yhat - ref.y).abs()).groupby("cat").e.mean().rename("было").to_frame()
               .join(rep.assign(e=(rep.yhat - rep.y).abs()).groupby("cat").e.mean().rename("стало")).round(1)))
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "reconcile.csv", index=False)
    pd.set_option("display.width", 220)
    print(res[["base", "lam", "kap", "H", "MAE", "MAE_ref", "gain_pct", "share_series_better", "boot_ci_low", "boot_ci_high"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
