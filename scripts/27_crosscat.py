"""Связь категорий: переток в маркетплейсы и офлайн-категории.

Мысль из особого мнения в листе практик: уход покупок в маркетплейсы выглядит
как спад офлайна. Сигнал МО на точке T: изменение лог-доли «Маркетплейсов»
во «Всех категориях» за три месяца до T минус медиана того же изменения
по группе «город/район» — то есть насколько МО уходит в онлайн быстрее похожих.
Поправка офлайн-категорий («Продовольствие», «Общественное питание», «Здоровье»,
«Транспорт»): yhat·exp(β·m·0,5^(h−1)) на шагах 1—3. β из (−0,5; −0,25; 0; 0,25; 0,5)
выбирается на целях до мая 2024 года, отчёт — по точкам с июня, против ансамбля
и против итога с сигналами дня (26_robust_selection.py).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sbi import backtest, metrics  # noqa: E402
from sbi.models.panel import URBAN  # noqa: E402

OUT = ROOT / "results/signal_value"
LAST, REPORT_FROM = "2024-12", "2024-06"
COLS = ["row", "origin", "step", "target", "y", "y_origin", "yhat"]
OFFLINE = {"Продовольствие", "Общественное питание", "Здоровье", "Транспорт"}


def signal(panel) -> pd.DataFrame:
    idx = panel.index.assign(category=panel.index.category.astype(str))
    y = pd.DataFrame(np.log(panel.y), columns=panel.periods)
    y["territory_id"], y["category"] = idx.territory_id.to_numpy(), idx.category.to_numpy()
    mp = y[y.category == "Маркетплейсы"].set_index("territory_id")[panel.periods]
    al = y[y.category == "Все категории"].set_index("territory_id")[panel.periods]
    share = (mp - al).dropna()
    ch = share - share.shift(3, axis=1)
    mo = pd.read_parquet(ROOT / "data/processed/mo.parquet").set_index("territory_id").mo_type
    kind = mo.reindex(ch.index).isin(URBAN)
    return ch - ch.groupby(kind).transform("median")


def main():
    panel = backtest.load_panel(ROOT / "data/processed")
    cats = panel.index.category.astype(str).to_numpy()
    tid = panel.index.territory_id.to_numpy()
    sig = signal(panel)
    rows = []
    for name, path in [("ensemble", ROOT / "results/forecasts/ensemble.parquet"), ("ensemble+robust", OUT / "fc_ensemble+robust.parquet")]:
        f = pd.read_parquet(path)[COLS]
        off = np.isin(cats[f.row.to_numpy()], list(OFFLINE))
        t = tid[f.row.to_numpy()]
        m = np.array([sig.at[a, o] if a in sig.index and o in sig.columns else 0.0 for a, o in zip(t, f.origin)])
        m = np.nan_to_num(m) * off * np.where(f.step <= 3, 0.5 ** (f.step - 1), 0.0)
        sel = (f.target <= "2024-05").to_numpy()
        mae = {b: (f.yhat[sel] * np.exp(b * m[sel]) - f.y[sel]).abs().mean() for b in (-0.5, -0.25, 0.0, 0.25, 0.5)}
        beta = min(mae, key=mae.get)
        print(name, {k: round(v, 2) for k, v in mae.items()}, "→", beta)
        g = f.assign(yhat=f.yhat * np.exp(beta * m))
        for H in (1, 3, 6):
            rows.append({"base": name, "beta": beta, **metrics.compare(g[g.origin >= REPORT_FROM], f[f.origin >= REPORT_FROM], H, LAST, 2000, 42)})
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "crosscat.csv", index=False)
    print(res[["base", "beta", "H", "MAE", "MAE_ref", "gain_pct", "boot_ci_low", "boot_ci_high"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
