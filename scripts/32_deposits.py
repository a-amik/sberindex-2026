"""Вклады населения: сбережения как сигнал потребления.

Банк России публикует помесячно остатки вкладов физлиц по субъектам
(data/raw/cbr/02_06_Dep_ind.xlsx, с 2012 года, на первое число месяца).
Остаток на 1-е число месяца T+1 публикуется примерно через три недели,
поэтому на точке T известен остаток на 1-е число T, то есть за конец T−1.

Два сигнала. Общий: ускорение годового прироста вкладов России за три месяца.
Региональный: то же для субъекта минус Россия. Поправки на шагах 1—3
с затуханием 0,5; силы из (−1; −0,5; −0,25; 0; 0,25) выбираются на целях
до мая 2024 года, отчёт — точки с июня, база — итоговый прогноз дня.
Знак ожидается отрицательный: деньги ушли во вклады — расходы ниже.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sbi import backtest, metrics  # noqa: E402
from sbi.regions import key as region_key  # noqa: E402

OUT = ROOT / "results/signal_value"
LAST, REPORT_FROM = "2024-12", "2024-06"
COLS = ["row", "origin", "step", "target", "y", "y_origin", "yhat"]
GRID = (-1.0, -0.5, -0.25, 0.0, 0.25)


def deposits() -> pd.DataFrame:
    d = pd.read_excel(ROOT / "data/raw/cbr/02_06_Dep_ind.xlsx", sheet_name="итого", header=None)
    dates = pd.to_datetime(d.iloc[1, 1:], dayfirst=True, errors="coerce")
    keep = dates.notna().to_numpy()
    # остаток на 1-е число месяца m — это конец месяца m−1
    periods = [(p - pd.offsets.MonthBegin(1)).strftime("%Y-%m") for p in dates[keep]]
    rows = {}
    for _, r in d.iloc[2:].iterrows():
        name = str(r.iloc[0]).strip()
        if not name or name == "nan" or "ОКРУГ" in name:
            continue
        key = "*" if name == "РОССИЙСКАЯ ФЕДЕРАЦИЯ" else region_key(name)
        if key:
            rows[key] = pd.to_numeric(r.iloc[1:], errors="coerce").to_numpy()[keep]
    w = pd.DataFrame(rows, index=periods)
    w = w[~w.index.duplicated()].sort_index()
    lw = np.log(w)
    yoy = lw - lw.shift(12)
    return yoy - yoy.shift(1).rolling(3).mean()


def main():
    panel = backtest.load_panel(ROOT / "data/processed")
    mo = pd.read_parquet(ROOT / "data/processed/mo.parquet")[["territory_id", "region_key"]]
    rk = panel.index.merge(mo, on="territory_id", how="left").region_key.to_numpy()
    acc = deposits()
    print("субъектов сопоставлено:", acc.shape[1] - 1, "; точки:", acc.index[0], acc.index[-1])
    f = pd.read_parquet(OUT / "fc_ensemble+robust+growth_adj.parquet")
    prev = f.origin.map(lambda o: str(pd.Period(o, "M") - 1))      # известен остаток за конец T−1
    dec = np.where(f.step <= 3, 0.5 ** (f.step - 1), 0.0)
    nat = prev.map(acc["*"]).fillna(0.0).to_numpy() * dec
    reg_acc = np.array([acc.at[p, k] - acc.at[p, "*"] if (k in acc.columns and p in acc.index) else 0.0
                        for p, k in zip(prev, rk[f.row.to_numpy()])])
    reg = np.nan_to_num(reg_acc) * dec
    sel = (f.target <= "2024-05").to_numpy()
    rows = []
    for name, x in (("Россия", nat), ("субъект минус Россия", reg)):
        mae = {b: (f.yhat[sel] * np.exp(b * x[sel]) - f.y[sel]).abs().mean() for b in GRID}
        beta = min(mae, key=mae.get)
        print(name, {k: round(v, 2) for k, v in mae.items()}, "→", beta)
        g = f.assign(yhat=f.yhat * np.exp(beta * x))
        for H in (1, 3, 6):
            rows.append({"signal": name, "beta": beta, **metrics.compare(g[g.origin >= REPORT_FROM][COLS], f[f.origin >= REPORT_FROM][COLS], H, LAST, 2000, 42)})
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "deposits.csv", index=False)
    print(res[["signal", "beta", "H", "MAE", "MAE_ref", "gain_pct", "share_series_better", "boot_ci_low", "boot_ci_high"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
