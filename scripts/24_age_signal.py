"""Возрастной сигнал МО: активность его возрастных групп против всех возрастов.

Индекс потребительской активности СберИндекса по возрастам — недельный,
по России (data/external/sberindex/potrebitelskaya-aktivnost-...). Возрастная
структура МО — база муниципальных показателей Росстата на 1 января 2023 года
(23_age_mo.py). Для месяца m и группы g: a_g(m) — ускорение годового прироста
месячного индекса против трёх предыдущих месяцев. Сигнал МО:
δ = Σ_g w_g·a_g − a_всех, w_g — доли групп 15—24, 25—34, 35—64, 65+ среди
жителей старше 15 лет. МО, где много пенсионеров, получает своё в январе,
когда индексируют пенсии; МО молодых — своё.

Месяц T+1 известен к публикации месяца T по тому же допущению, что
у недельного ноукаста (11_factor_signals.py). Поправка: yhat·exp(β·δ·0,5^(h−1))
на шагах 1—3; β из (0; 1; 2; 4) выбирается на целях до мая 2024 года,
отчёт — по точкам с июня, против ансамбля и против ансамбля с сигналами.
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
GROUPS = {"15 - 24 лет": "15-24", "25 - 34 лет": "25-34", "35 - 64 лет": "35-64", "65+ лет": "65+"}


def accel() -> pd.DataFrame:
    d = pd.read_parquet(ROOT / "data/external/sberindex/potrebitelskaya-aktivnost-po-kategoriyam-tovarov-v-razreze-vozrastov.parquet")
    d["period"] = (pd.to_datetime(d.period) + pd.Timedelta(days=1)).dt.strftime("%Y-%m")
    m = np.log(d.pivot_table(index="period", columns="age", values="value", aggfunc="mean"))
    yoy = m - m.shift(12)
    a = yoy - yoy.shift(1).rolling(3).mean()
    return a


def main():
    panel = backtest.load_panel(ROOT / "data/processed")
    mo = pd.read_parquet(ROOT / "data/processed/mo.parquet")[["territory_id", "oktmo8"]]
    age = pd.read_parquet(ROOT / "data/external/rosstat/age_mo_2023.parquet").dropna(subset=list(GROUPS.values()))
    a = accel()
    adult = age[list(GROUPS.values())].sum(axis=1)
    w = age[list(GROUPS.values())].div(adult, axis=0).assign(oktmo8=age.oktmo8)
    w = mo.merge(w, on="oktmo8", how="left").set_index("territory_id")
    print("МО с возрастной структурой:", int(w["65+"].notna().sum()), "из", len(w))
    print("доля 65+ среди взрослых: медиана", round(w["65+"].median(), 3), "размах", round(w["65+"].quantile(0.05), 3), "—", round(w["65+"].quantile(0.95), 3))
    # δ(МО, месяц) = Σ w_g a_g − a_всех
    months = a.index
    dmo = pd.DataFrame(0.0, index=w.index, columns=months)
    for src, g in GROUPS.items():
        dmo += np.outer(w[g].fillna(0).to_numpy(), a[src].fillna(0).to_numpy())
    dmo -= np.outer(w["65+"].notna().to_numpy(), a["Все возрасты"].fillna(0).to_numpy())
    dmo[w["65+"].isna()] = 0.0
    tid = panel.index.territory_id.to_numpy()
    rows = []
    for name in ["ensemble", "panel_blend_ses_bytype"]:
        f = pd.read_parquet(ROOT / f"results/forecasts/{name}.parquet")
        nxt = f.origin.map(lambda o: str(pd.Period(o, "M") + 1))
        d = dmo.reindex(columns=sorted(set(nxt))).to_numpy()
        col = {c: i for i, c in enumerate(sorted(set(nxt)))}
        rowpos = pd.Series(np.arange(len(dmo)), index=dmo.index)
        f["delta"] = d[rowpos.reindex(tid[f.row.to_numpy()]).to_numpy(), nxt.map(col).to_numpy()]
        f["delta"] = np.where(f.step <= 3, f.delta * 0.5 ** (f.step - 1), 0.0)
        sel = f[f.target <= "2024-05"]
        mae = {b: (sel.yhat * np.exp(b * sel.delta) - sel.y).abs().mean() for b in (0.0, 1.0, 2.0, 4.0)}
        beta = min(mae, key=mae.get)
        print(name, {k: round(v, 2) for k, v in mae.items()}, "→", beta)
        g = f.assign(yhat=f.yhat * np.exp(beta * f.delta))
        g[COLS].to_parquet(OUT / f"fc_{name}+age.parquet")
        refs = {name: f}
        if name == "ensemble":
            comb = pd.read_parquet(OUT / "fc_ensemble+signals.parquet")
            refs["ensemble+signals"] = comb
            gc = comb.merge(f[["row", "origin", "step", "delta"]], on=["row", "origin", "step"])
            gc = gc.assign(yhat=gc.yhat * np.exp(beta * gc.delta))
            gc[COLS].to_parquet(OUT / "fc_ensemble+signals+age.parquet")
        for ref_name, ref in refs.items():
            src = g if ref_name == name else gc
            for H in (1, 3, 6):
                r = metrics.compare(src[src.origin >= REPORT_FROM][COLS], ref[ref.origin >= REPORT_FROM][COLS], H, LAST, 2000, 42)
                rows.append({"base": ref_name, "beta": beta, **r})
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "age_signal.csv", index=False)
    pd.set_option("display.width", 220)
    print(res[["base", "beta", "H", "MAE", "MAE_ref", "gain_pct", "share_series_better", "boot_ci_low", "boot_ci_high"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
