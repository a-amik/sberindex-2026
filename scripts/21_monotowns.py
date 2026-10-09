"""Работодатели: моногорода и фонд оплаты труда их отраслей.

Моногород живёт зарплатой одного-двух предприятий. Если фонд оплаты труда
в обработке и добыче ускоряется быстрее, чем во всей экономике, расходы
моногородов должны отрываться от фактора вверх, и наоборот. Перечень —
Росстат (164 МО с ненулевым статусом в mo.parquet), отрасль градообразующего
предприятия в нём не указана, поэтому берётся среднее двух отраслей.
Фонд — СберИндекс, лаг публикации два месяца, как в 13_factor_model.py.

Поправка рядов моногородов: yhat·exp(β·s), s — ускорение разрыва годовых
приростов фонда за три месяца. β из (−0,5; −0,25; 0; 0,25; 0,5) — первая сетка (−2…2) оказалась вчетверо грубее сигнала — выбирается на целях
до мая 2024 года, отчёт — по точкам с июня, отдельно по рядам моногородов.
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


def signal() -> pd.Series:
    f = pd.read_parquet(ROOT / "data/external/sberindex/izmenenie-obema-fot.parquet")
    f["period"] = (pd.to_datetime(f.period) + pd.Timedelta(days=1)).dt.strftime("%Y-%m")
    w = np.log(f.pivot_table(index="period", columns="activity", values="value"))
    yoy = w - w.shift(12)
    gap = yoy[["Обрабатывающие производства", "Добыча полезных ископаемых"]].mean(axis=1) - yoy["Все отрасли"]
    return (gap - gap.shift(3)).shift(2)


def main():
    panel = backtest.load_panel(ROOT / "data/processed")
    mo = pd.read_parquet(ROOT / "data/processed/mo.parquet")
    mono = set(mo[mo.mono_status.str.strip() != ""].territory_id)
    is_mono = panel.index.territory_id.isin(mono).to_numpy()
    s = signal()
    print("сигнал по точкам:", s.loc["2023-12":"2024-11"].round(4).to_dict())
    rows = []
    for name in ["ensemble", "panel_blend_ses_bytype"]:
        f = pd.read_parquet(ROOT / f"results/forecasts/{name}.parquet")
        f["s"] = np.where(is_mono[f.row.to_numpy()], f.origin.map(s).fillna(0.0), 0.0)
        sel = f[(f.target <= "2024-05") & is_mono[f.row.to_numpy()]]
        mae = {b: (sel.yhat * np.exp(b * sel.s) - sel.y).abs().mean() for b in (-0.5, -0.25, 0.0, 0.25, 0.5)}
        beta = min(mae, key=mae.get)
        print(name, {k: round(v, 2) for k, v in mae.items()}, "→", beta)
        g = f.assign(yhat=f.yhat * np.exp(beta * f.s))
        mono_rows = np.flatnonzero(is_mono)
        for scope, keep in (("моногорода", mono_rows), ("все ряды", np.arange(len(is_mono)))):
            a = g[(g.origin >= REPORT_FROM) & g.row.isin(keep)][COLS]
            b = f[(f.origin >= REPORT_FROM) & f.row.isin(keep)][COLS]
            for H in (1, 3, 6):
                rows.append({"base": name, "scope": scope, "beta": beta, **metrics.compare(a, b, H, LAST, 2000, 42)})
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "monotowns.csv", index=False)
    pd.set_option("display.width", 220)
    print(res[["base", "scope", "beta", "H", "MAE", "MAE_ref", "gain_pct", "share_series_better", "boot_ci_low", "boot_ci_high"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
