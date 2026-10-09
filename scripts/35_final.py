"""Итоговый прогноз с внешними сигналами — одним запуском.

Цепочка, собранная из опытов results/signal_value:
1. 11_factor_signals.py — недельный ноукаст расходов (поправки по категориям);
2. 26_robust_selection.py — ноукаст, фонд оплаты труда для моногородов и общая часть
   возрастной активности поверх ансамбля, силы выбраны на целях до мая 2024 года,
   шаги 1—3 с затуханием 0,5;
3. 30_factor_growth.py, debiased — рост фактора на шагах 4—12 из недельного ряда
   со смещением, выученным по истории до точки;
4. 28_intervals.py — конформные интервалы на 80 и 90 %.

Итог — results/forecasts/ensemble_signals.parquet (те же колонки, что у прочих
прогнозов, плюс lo80, hi80, lo90, hi90) и results/metrics/ensemble_signals.csv —
сравнение с ансамблем и с Prophet по умолчанию на отчётном окне и на всех точках.

    python scripts/35_final.py            # пересчитать цепочку и итог
    python scripts/35_final.py --only-assemble   # только собрать итог из готовых файлов
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sbi import metrics  # noqa: E402

SV = ROOT / "results/signal_value"
LAST, REPORT_FROM = "2024-12", "2024-06"
COLS = ["row", "origin", "step", "target", "y", "y_origin", "yhat"]


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / f"scripts/{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    if "--only-assemble" not in sys.argv:
        load("11_factor_signals").main()
        load("26_robust_selection").main()
        load("30_factor_growth").debiased()
        load("28_intervals").main()
    f = pd.read_parquet(SV / "fc_ensemble+robust+growth_adj.parquet")[COLS]
    # интервалы — по остаткам самого итога, правилами 28_intervals.py
    iv = interval_quantiles(f)
    f = f.merge(iv, on=["row", "origin", "step"], how="left")
    for lv in (80, 90):
        f[f"lo{lv}"] = f.yhat * np.exp(-f[f"q{lv}"])
        f[f"hi{lv}"] = f.yhat * np.exp(f[f"q{lv}"])
    out = ROOT / "results/forecasts/ensemble_signals.parquet"
    f.drop(columns=["q80", "q90"]).to_parquet(out, index=False)
    rows = []
    for ref in ("ensemble", "prophet_default"):
        r = pd.read_parquet(ROOT / f"results/forecasts/{ref}.parquet")
        for window, lo in (("отчёт", REPORT_FROM), ("все точки", "2023-12")):
            for H in (1, 3, 6, 12):
                if H == 12 and window == "отчёт":
                    continue
                c = metrics.compare(f[f.origin >= lo][COLS], r[r.origin >= lo][COLS], H, LAST, 2000, 42)
                rows.append({"против": ref, "окно": window, **c})
    res = pd.DataFrame(rows)
    res.to_csv(ROOT / "results/metrics/ensemble_signals.csv", index=False)
    cov = []
    rep = f[f.origin >= REPORT_FROM]
    for h in (1, 3, 6):
        d = rep[rep.step == h]
        cov.append({"шаг": h, "покрытие80": ((d.y >= d.lo80) & (d.y <= d.hi80)).mean(), "покрытие90": ((d.y >= d.lo90) & (d.y <= d.hi90)).mean()})
    pd.set_option("display.width", 220)
    print(res[["против", "окно", "H", "MAE", "MAE_ref", "gain_pct", "share_series_better", "boot_ci_low", "boot_ci_high"]].round(2).to_string(index=False))
    print(pd.DataFrame(cov).round(3).to_string(index=False))
    print("итог:", out)


def interval_quantiles(f: pd.DataFrame) -> pd.DataFrame:
    """Те же правила, что в 28_intervals.py, но по остаткам самого итога."""
    from sbi import backtest
    panel = backtest.load_panel(ROOT / "data/processed")
    cats = panel.index.category.astype(str).to_numpy()
    f = f.assign(category=cats[f.row.to_numpy()], r=np.abs(np.log(f.y / f.yhat)))
    out = []
    for o in sorted(f.origin.unique()):
        cur = f[f.origin == o][["row", "origin", "step", "category"]].copy()
        past = f[f.target <= o]
        for c, cpart in cur.groupby("category"):
            pc = past[past.category == c]
            known = {h: {lv: np.quantile(pc[pc.step == h].r, lv) for lv in (0.8, 0.9)}
                     for h in sorted(pc.step.unique()) if pc[pc.step == h].origin.nunique() >= 3}
            for h, part in cpart.groupby("step"):
                for lv in (0.8, 0.9):
                    if h in known:
                        qv = known[h][lv]
                    elif known:
                        h0 = max(known)
                        qv = known[h0][lv] * np.sqrt(h / h0)
                    else:
                        res = pc[pc.step <= h].r
                        qv = np.quantile(res, lv) if len(res) >= 100 else np.nan
                    cur.loc[part.index, f"q{int(lv * 100)}"] = qv
        out.append(cur)
    return pd.concat(out)[["row", "origin", "step", "q80", "q90"]]


if __name__ == "__main__":
    main()
