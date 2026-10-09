"""Память ошибки МО: поправка на последнюю известную ошибку ряда.

После сигналов дня муниципальный слой ошибки не изменился: 196/218/254 руб.
на 1/3/6 месяцах (10_layers.py на итоговом прогнозе). Проверка: повторяется ли
ошибка ряда от месяца к месяцу. На точке T известна ошибка прогноза шага 1,
сделанного в T−1 на месяц T. Из неё вычитается общая часть — медиана по группе
«категория × город/район», чтобы не задваивать сигналы фактора, — и остаток e
идёт в поправку: yhat·exp(−φ·e·ρ^(h−1)). φ из (0; 0,25; 0,5; 0,75; 1) и ρ из
(0,5; 0,8; 1) выбираются на целях до мая 2024 года, отчёт — точки с июня, база —
итоговый прогноз дня (fc_ensemble+robust).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sbi import backtest, metrics  # noqa: E402
from sbi.models.panel import groups  # noqa: E402

OUT = ROOT / "results/signal_value"
LAST, REPORT_FROM = "2024-12", "2024-06"
COLS = ["row", "origin", "step", "target", "y", "y_origin", "yhat"]


def main():
    panel = backtest.load_panel(ROOT / "data/processed")
    mo = pd.read_parquet(ROOT / "data/processed/mo.parquet")
    gt = groups(panel.index, mo, "type")
    f = pd.read_parquet(OUT / "fc_ensemble+robust.parquet")
    # ошибка шага 1 из точки T−1 на месяц T — известна на T
    one = f[f.step == 1].copy()
    one["e"] = np.log(one.yhat / one.y)
    one["e"] -= one.groupby([one.origin, gt[one.row.to_numpy()]]).e.transform("median")
    one["origin_next"] = one.target           # эта ошибка известна в точке, равной её цели
    last = one.set_index(["row", "origin_next"]).e
    f["e_last"] = pd.MultiIndex.from_arrays([f.row, f.origin]).map(last.to_dict()).fillna(0.0).to_numpy()
    # медленная ошибка: среднее трёх последних известных
    lag = {k: one.assign(origin_next=(pd.PeriodIndex(one.target, freq="M") + k).astype(str)).set_index(["row", "origin_next"]).e
           for k in (0, 1, 2)}
    f["e_avg3"] = np.nanmean(np.stack([pd.MultiIndex.from_arrays([f.row, f.origin]).map(lag[k].to_dict()).to_numpy(dtype=float)
                                       for k in lag]), axis=0)
    f["e_avg3"] = f.e_avg3.fillna(0.0)
    print("корреляция ошибки МО шага 1 с прошлой (точки с марта 2024):",
          round(np.corrcoef(*one.assign(prev=pd.MultiIndex.from_arrays([one.row, one.origin]).map(last.to_dict()))
                             .dropna(subset=["prev"])[["e", "prev"]].to_numpy().T)[0, 1], 3))
    sel = f[f.target <= "2024-05"]
    rows = []
    for col in ("e_last", "e_avg3"):
        grid = {(phi, rho): (sel.yhat * np.exp(-phi * sel[col] * rho ** (sel.step - 1)) - sel.y).abs().mean()
                for phi in (0.0, 0.25, 0.5, 0.75, 1.0) for rho in (0.5, 0.8, 1.0)}
        phi, rho = min(grid, key=grid.get)
        print(col, "φ, ρ →", (phi, rho), round(grid[(phi, rho)], 1), "без поправки", round(grid[(0.0, 0.5)], 1))
        g = f.assign(yhat=f.yhat * np.exp(-phi * f[col] * rho ** (f.step - 1)))
        g[COLS].to_parquet(OUT / f"fc_ensemble+robust+{col}.parquet")
        for H in (1, 3, 6):
            rows.append({"signal": col, "phi": phi, "rho": rho,
                         **metrics.compare(g[g.origin >= REPORT_FROM][COLS], f[f.origin >= REPORT_FROM][COLS], H, LAST, 2000, 42)})
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "error_memory.csv", index=False)
    print(res[["signal", "phi", "rho", "H", "MAE", "MAE_ref", "gain_pct", "share_series_better", "boot_ci_low", "boot_ci_high"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
