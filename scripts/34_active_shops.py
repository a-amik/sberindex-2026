"""Активные торговые точки СберИндекса как ноукаст общего фактора.

Недельный ряд «изменение количества активных торгово-сервисных точек»
по 26 категориям, по России (national.parquet, active_shops:*). Сигнал —
ускорение годового прироста месяца T+1 против трёх последних месяцев, как
у недельного ноукаста расходов (11_factor_signals.py). Сопоставление
категорий задано заранее. Поправка — сверху итогового прогноза, на шагах 1—3
с затуханием 0,5; сила по категории из (0; 0,5; 1) выбирается на целях до мая
2024 года, отчёт — точки с июня. Главный интерес — «Здоровье» и «Транспорт»,
где недельный ряд расходов сопоставлен слабо.
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
SHOPS = {
    "Все категории": ["Все категории "],
    "Продовольствие": ["Продовольственные магазины"],
    "Общественное питание": ["Общественное питание"],
    "Маркетплейсы": ["Одежда, обувь и аксессуары", "Электроника и телекоммуникационное оборудование"],
    "Здоровье": ["Лекарства и медицинские товары", "Медицинские услуги"],
    "Транспорт": ["Топливо", "Сервис и обслуживание автомобилей"],
}


def main():
    nat = pd.read_parquet(ROOT / "data/processed/national.parquet").set_index("period")
    sig = {}
    for c, cols in SHOPS.items():
        v = nat[[f"active_shops:{x}" for x in cols]].mean(axis=1)
        s = np.log1p(v / 100) if v.abs().max() < 100 else np.log(v) - np.log(v).shift(12)
        sig[c] = s
    sig = pd.DataFrame(sig)
    acc = sig - sig.shift(1).rolling(3).mean()           # ускорение месяца m против трёх предыдущих
    panel = backtest.load_panel(ROOT / "data/processed")
    cats = panel.index.category.astype(str).to_numpy()
    f = pd.read_parquet(OUT / "fc_ensemble+robust+growth_adj.parquet")
    f["category"] = cats[f.row.to_numpy()]
    nxt = f.origin.map(lambda o: str(pd.Period(o, "M") + 1))
    x = np.array([acc.at[n, c] if n in acc.index else np.nan for n, c in zip(nxt, f.category)])
    f["x"] = np.nan_to_num(x) * np.where(f.step <= 3, 0.5 ** (f.step - 1), 0.0)
    sel = f[f.target <= "2024-05"]
    k = {}
    for c, s in sel.groupby("category"):
        mae = {v: (s.yhat * np.exp(v * s.x) - s.y).abs().mean() for v in (0.0, 0.5, 1.0)}
        k[c] = min(mae, key=mae.get)
    print("силы:", k)
    g = f.assign(yhat=f.yhat * np.exp(f.category.map(k) * f.x))
    rows = []
    for H in (1, 3, 6):
        rows.append(metrics.compare(g[g.origin >= REPORT_FROM][COLS], f[f.origin >= REPORT_FROM][COLS], H, LAST, 2000, 42))
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "active_shops.csv", index=False)
    rep = g[(g.origin >= REPORT_FROM) & (g.step <= 3)]
    ref = f[(f.origin >= REPORT_FROM) & (f.step <= 3)]
    print(pd.DataFrame({"до": (ref.yhat - ref.y).abs().groupby(ref.category).mean(),
                        "после": (rep.yhat - rep.y).abs().groupby(rep.category).mean()}).round(1))
    print(res[["H", "MAE", "MAE_ref", "gain_pct", "boot_ci_low", "boot_ci_high"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
