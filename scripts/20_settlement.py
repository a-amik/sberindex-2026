"""Заселение: прирост населения МО как сигнал дрейфа расходов на жителя.

Растущий пригород набирает жителей, и его расходы растут быстрее фактора;
сглаженное отклонение МО за этим ростом не успевает. Сигнал — годовой
прирост населения МО по Росстату (1 января 2024 → 1 января 2025 года,
data/external/rosstat/population_mo*.parquet). Этот прирост опубликован
в 2025 году, позже окна проверки: он берётся как приближение прироста
предыдущего года — заселение районов идёт несколько лет подряд. Это допущение,
не историческая версия данных.

Поправка: yhat·exp(β·g·h/12), g ограничен ±10 %. β из (0; 0,5; 1; 2; 3)
выбирается на целях до мая 2024 года, отчёт — по точкам с июня.
Отдельно — разрез по квантилям прироста: где поправка работает.
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
BETAS = (0.0, 0.5, 1.0, 2.0, 3.0)


def growth() -> pd.Series:
    a = pd.read_parquet(ROOT / "data/external/rosstat/population_mo_2024.parquet")
    b = pd.read_parquet(ROOT / "data/external/rosstat/population_mo.parquet")
    j = a.merge(b, on="oktmo8", suffixes=("_24", "_25"))
    j = j[(j.pop_24 > 0) & (j.pop_25 > 0)].drop_duplicates("oktmo8")
    mo = pd.read_parquet(ROOT / "data/processed/mo.parquet")[["territory_id", "oktmo8"]]
    g = mo.merge(j.assign(g=j.pop_25 / j.pop_24 - 1)[["oktmo8", "g"]], on="oktmo8", how="left")
    return g.set_index("territory_id").g.clip(-0.1, 0.1)


def main():
    panel = backtest.load_panel(ROOT / "data/processed")
    g_mo = growth()
    g_row = panel.index.territory_id.map(g_mo).fillna(0.0).to_numpy()
    print("МО с приростом:", int(g_mo.notna().sum()), "из", len(g_mo))
    rows, slices = [], []
    for name in ["ensemble", "panel_blend_ses_bytype"]:
        f = pd.read_parquet(ROOT / f"results/forecasts/{name}.parquet")
        f["g"] = g_row[f.row.to_numpy()]
        # дрейф ошибки: связь лог-ошибки с приростом на окне выбора
        sel = f[f.target <= "2024-05"]
        e = np.log(sel.y / sel.yhat)
        print(name, "corr(лог-недопрогноз, g·h):", round(np.corrcoef(e, sel.g * sel.step)[0, 1], 3))
        mae = {b: (sel.yhat * np.exp(b * sel.g * sel.step / 12) - sel.y).abs().mean() for b in BETAS}
        beta = min(mae, key=mae.get)
        print(name, {k: round(v, 2) for k, v in mae.items()}, "→", beta)
        g = f.assign(yhat=f.yhat * np.exp(beta * f.g * f.step / 12))
        g[COLS].to_parquet(OUT / f"fc_{name}+settlement.parquet")
        for H in (1, 3, 6):
            r = metrics.compare(g[g.origin >= REPORT_FROM][COLS], f[f.origin >= REPORT_FROM][COLS], H, LAST, 2000, 42)
            rows.append({"base": name, "beta": beta, **r})
        if name == "ensemble":
            rep = f[(f.origin >= REPORT_FROM) & (f.step <= 6)].copy()
            rep["new"] = rep.yhat * np.exp(beta * rep.g * rep.step / 12)
            rep["q"] = pd.cut(rep.g, [-1, -0.02, -0.005, 0.005, 0.02, 1],
                              labels=["убыль >2 %", "убыль 0,5—2 %", "±0,5 %", "рост 0,5—2 %", "рост >2 %"])
            for q, s in rep.groupby("q", observed=True):
                slices.append({"прирост": q, "рядов": s.row.nunique(), "MAE": (s.yhat - s.y).abs().mean(),
                               "MAE_new": (s.new - s.y).abs().mean(), "bias_pct": np.mean(np.log(s.yhat / s.y)) * 100})
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "settlement.csv", index=False)
    pd.DataFrame(slices).to_csv(OUT / "settlement_slices.csv", index=False)
    pd.set_option("display.width", 220)
    print(res[["base", "beta", "H", "MAE", "MAE_ref", "gain_pct", "share_series_better", "boot_ci_low", "boot_ci_high"]].round(3).to_string(index=False))
    print(pd.DataFrame(slices).round(2).to_string(index=False))


if __name__ == "__main__":
    main()
