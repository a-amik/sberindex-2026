"""Сжатие прогноза МО к соседям и к субъекту.

Около 117 руб. из 196 муниципальной ошибки на первом шаге — шум ряда
(10_layers.py). Шум МО не связан с шумом соседей, поэтому среднее по соседям
его гасит. Сжимается прогнозный прирост от точки прогноза в логарифмах:
r = (1 − λ)·r_МО + λ·r_опоры, где опора — средний прирост восьми ближайших
по дороге соседей той же категории (connection.parquet) или медиана субъекта.
λ из (0; 0,1; 0,2; 0,3; 0,5) выбирается на целях до мая 2024 года, отдельно
для каждой категории; отчёт — по точкам с июня.
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
LAMS = (0.0, 0.1, 0.2, 0.3, 0.5)


def main():
    panel = backtest.load_panel(ROOT / "data/processed")
    idx = panel.index.copy()
    idx["category"] = idx.category.astype(str)
    idx["row"] = np.arange(len(idx))
    mo = pd.read_parquet(ROOT / "data/processed/mo.parquet")
    idx = idx.merge(mo[["territory_id", "region"]], on="territory_id", how="left")
    nb = pd.read_parquet(ROOT / "data/processed/neighbours.parquet")
    pairs = (idx[["territory_id", "category", "row"]]
             .merge(nb[["territory_id", "neighbour_id"]], on="territory_id")
             .merge(idx[["territory_id", "category", "row"]].rename(columns={"territory_id": "neighbour_id", "row": "nrow"}),
                    on=["neighbour_id", "category"]))[["row", "nrow"]]
    rows = []
    for name in ["ensemble", "panel_blend_ses_bytype"]:
        f = pd.read_parquet(ROOT / f"results/forecasts/{name}.parquet")
        f["r"] = np.log(f.yhat / f.y_origin)
        f = f.merge(idx[["row", "category", "region"]], on="row")
        # опора 1: соседи по дороге
        p = pairs.merge(f[["row", "origin", "step", "r"]].rename(columns={"row": "nrow", "r": "rn"}), on="nrow")
        nbm = p.groupby(["row", "origin", "step"]).rn.mean().rename("r_nb")
        f = f.merge(nbm, on=["row", "origin", "step"], how="left")
        f["r_nb"] = f.r_nb.fillna(f.r)
        # опора 2: медиана субъекта
        f["r_reg"] = f.groupby(["origin", "step", "category", "region"]).r.transform("median")
        for anchor in ("r_nb", "r_reg"):
            sel = f[f.target <= "2024-05"]
            lam = {}
            for c, s in sel.groupby("category"):
                mae = {l: (s.y_origin * np.exp((1 - l) * s.r + l * s[anchor]) - s.y).abs().mean() for l in LAMS}
                lam[c] = min(mae, key=mae.get)
            L = f.category.map(lam)
            g = f.assign(yhat=f.y_origin * np.exp((1 - L) * f.r + L * f[anchor]))
            g[COLS].to_parquet(OUT / f"fc_{name}+shrink_{anchor}.parquet")
            for H in (1, 3, 6):
                r = metrics.compare(g[g.origin >= REPORT_FROM][COLS], f[f.origin >= REPORT_FROM][COLS], H, LAST, 2000, 42)
                rows.append({"base": name, "anchor": anchor, "lam": str(lam), **r})
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "shrink.csv", index=False)
    pd.set_option("display.width", 250)
    print(res[["base", "anchor", "H", "MAE", "MAE_ref", "gain_pct", "share_series_better", "wilcoxon_p", "boot_ci_low", "boot_ci_high"]].round(3).to_string(index=False))
    for a in res.drop_duplicates(["base", "anchor"]).itertuples():
        print(a.base, a.anchor, a.lam)


if __name__ == "__main__":
    main()
