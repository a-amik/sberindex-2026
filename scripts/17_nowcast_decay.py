"""Недельный ноукаст на шагах дальше первого.

В 11_factor_signals.py поправка ноукаста стоит только на шаге 1. Ускорение
недельного прироста может держаться и дальше: шаг h получает поправку
k_cat·δ·ρ^(h−1). k_cat — те же, что выбраны в 11; ρ из (0; 0,25; 0,5; 0,75; 1)
выбирается на целях до мая 2024 года, отчёт — по точкам с июня.
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
K = {"Все категории": 1.0, "Продовольствие": 1.0, "Общественное питание": 1.0,
     "Здоровье": 1.0, "Маркетплейсы": 0.0, "Транспорт": 0.0}


def main():
    panel = backtest.load_panel(ROOT / "data/processed")
    cats = panel.index.category.astype(str).to_numpy()
    adj = pd.read_csv(OUT / "factor_adjustments.csv")
    d1 = adj[adj.step == 1][["origin", "category", "now"]].rename(columns={"now": "d"})
    rows = []
    for name in ["ensemble", "panel_blend_ses_bytype"]:
        f = pd.read_parquet(ROOT / f"results/forecasts/{name}.parquet")
        f["category"] = cats[f.row.to_numpy()]
        f = f.merge(d1, on=["origin", "category"], how="left").fillna({"d": 0.0})
        f["k"] = f.category.map(K)
        sel = f[f.target <= "2024-05"]
        mae = {r: (sel.yhat * np.exp(sel.k * sel.d * r ** (sel.step - 1)) - sel.y).abs().mean() for r in (0.0, 0.25, 0.5, 0.75, 1.0)}
        rho = min(mae, key=mae.get)
        g = f.assign(yhat=f.yhat * np.exp(f.k * f.d * rho ** (f.step - 1)))
        g[COLS].to_parquet(OUT / f"fc_{name}+now_decay.parquet")
        for H in (1, 3, 6):
            r = metrics.compare(g[g.origin >= REPORT_FROM][COLS], f[f.origin >= REPORT_FROM][COLS], H, LAST, 2000, 42)
            rows.append({"base": name, "rho": rho, **r})
        print(name, {k: round(v, 1) for k, v in mae.items()}, "→", rho)
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "nowcast_decay.csv", index=False)
    print(res[["base", "rho", "H", "MAE", "MAE_ref", "gain_pct", "share_series_better", "boot_ci_low", "boot_ci_high"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
