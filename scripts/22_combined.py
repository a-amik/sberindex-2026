"""Итоговый прогноз с внешними сигналами: ансамбль + ноукаст + моногорода.

Обе поправки — множители к прогнозу ансамбля, параметры взяты из своих опытов
без перенастройки: недельный ноукаст с силой по категориям и затуханием 0,5,
только шаги 1—3 (17_nowcast_decay.py); фонд оплаты труда отрасли для рядов
моногородов, β = 0,25, тоже шаги 1—3 (21_monotowns.py). Ограничение шагами
выбрано после отчётного окна — это отмечено в листе. Отчёт — точки с июня 2024
против ансамбля и против Prophet в настройках по умолчанию.
"""
from __future__ import annotations

import importlib.util
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
K = {"Все категории": 1.0, "Продовольствие": 1.0, "Общественное питание": 1.0,
     "Здоровье": 1.0, "Маркетплейсы": 0.0, "Транспорт": 0.0}


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"scripts/{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    panel = backtest.load_panel(ROOT / "data/processed")
    cats = panel.index.category.astype(str).to_numpy()
    mo = pd.read_parquet(ROOT / "data/processed/mo.parquet")
    is_mono = panel.index.territory_id.isin(set(mo[mo.mono_status.str.strip() != ""].territory_id)).to_numpy()
    s = load("21_monotowns").signal()
    adj = pd.read_csv(OUT / "factor_adjustments.csv")
    d1 = adj[adj.step == 1][["origin", "category", "now"]].rename(columns={"now": "d"})
    f = pd.read_parquet(ROOT / "results/forecasts/ensemble.parquet")
    f["category"] = cats[f.row.to_numpy()]
    f = f.merge(d1, on=["origin", "category"], how="left").fillna({"d": 0.0})
    short = f.step <= 3
    now = f.category.map(K) * f.d * 0.5 ** (f.step - 1)
    mono = np.where(is_mono[f.row.to_numpy()], 0.25 * f.origin.map(s).fillna(0.0), 0.0)
    g = f.assign(yhat=f.yhat * np.exp(np.where(short, now + mono, 0.0)))
    g[COLS].to_parquet(OUT / "fc_ensemble+signals.parquet")
    rows = []
    for ref in ["ensemble", "prophet_default"]:
        r = pd.read_parquet(ROOT / f"results/forecasts/{ref}.parquet")
        for H in (1, 3, 6):
            rows.append({"reference": ref, **metrics.compare(g[g.origin >= REPORT_FROM][COLS], r[r.origin >= REPORT_FROM][COLS], H, LAST, 2000, 42)})
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "combined.csv", index=False)
    pd.set_option("display.width", 220)
    print(res[["reference", "H", "MAE", "MAE_ref", "gain_pct", "share_series_better", "wilcoxon_p", "boot_ci_low", "boot_ci_high"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
