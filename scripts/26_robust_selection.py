"""Устойчивость итогового прогноза к выбору окна отбора.

Три сигнала дня — недельный ноукаст (сила по категории), фонд оплаты труда
для моногородов, возрастная активность (общая по месяцу часть) — стоят
на шагах 1—3 с затуханием 0,5. Их силы выбраны раньше на целях до мая 2024 года,
и граница «шаги 1—3» выбрана уже после взгляда на отчётное окно. Здесь все силы
выбираются заново, последовательно, на трёх окнах отбора — цели до марта,
апреля и мая 2024 года; отчёт — всегда точки с июня. Если выигрыш на трёх
месяцах держится при любом окне, его можно заявлять.
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


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"scripts/{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def components(f: pd.DataFrame, panel, with_age: bool = True) -> pd.DataFrame:
    """Три поправки в логарифмах при силе 1, уже с затуханием и только на шагах 1—3."""
    cats = panel.index.category.astype(str).to_numpy()
    tid = panel.index.territory_id.to_numpy()
    dec = np.where(f.step <= 3, 0.5 ** (f.step - 1), 0.0)
    f = f.assign(category=cats[f.row.to_numpy()])
    adj = pd.read_csv(OUT / "factor_adjustments.csv")
    d1 = adj[adj.step == 1].set_index(["origin", "category"]).now
    now = pd.MultiIndex.from_arrays([f.origin, f.category]).map(d1.to_dict()).fillna(0.0).to_numpy() * dec
    mo = pd.read_parquet(ROOT / "data/processed/mo.parquet")
    is_mono = np.isin(tid, mo[mo.mono_status.str.strip() != ""].territory_id)[f.row.to_numpy()]
    s = load("21_monotowns").signal()
    mono = np.where(is_mono, f.origin.map(s).fillna(0.0).to_numpy(), 0.0) * np.where(f.step <= 3, 1.0, 0.0)
    agec = np.zeros(len(f))
    if with_age:
        # Возрастная активность СберИндекса (набор potrebitelskaya-aktivnost-…-vozrastov, make data)
        # и возраст МО из БД ПМО (23_age_mo.py). Без любого из них слой нулевой, а не падение.
        try:
            a = load("24_age_signal").accel()
            groups = {"15 - 24 лет": "15-24", "25 - 34 лет": "25-34", "35 - 64 лет": "35-64", "65+ лет": "65+"}
            age = pd.read_parquet(ROOT / "data/external/rosstat/age_mo_2023.parquet").dropna(subset=list(groups.values()))
            w = age[list(groups.values())].div(age[list(groups.values())].sum(axis=1), axis=0).mean()
            common = sum(w[g] * a[src] for src, g in groups.items()) - a["Все возрасты"]
            agec = f.origin.map(lambda o: common.get(str(pd.Period(o, "M") + 1), 0.0)).fillna(0.0).to_numpy() * dec
        except FileNotFoundError as e:
            print(f"возрастной слой пропущен, нет входа: {e.filename}")
        except KeyError as e:   # файл есть, но без возрастных групп — сбой сбора (23_age_mo.py)
            print(f"возрастной слой пропущен, в age_mo_2023.parquet нет групп {e}")
    return f.assign(now=now, mono=mono, agec=agec)


def select(f: pd.DataFrame, end: str) -> dict:
    sel = f[f.target <= end]
    mae = lambda x: (sel.yhat * np.exp(x) - sel.y).abs().mean()
    k = {}
    for c in sorted(sel.category.unique()):
        part = sel.category == c
        k[c] = min((0.0, 0.5, 1.0), key=lambda v: mae(np.where(part, v * sel.now, 0.0)))
    base = sel.category.map(k).to_numpy() * sel.now.to_numpy()
    bm = min((0.0, 0.25, 0.5), key=lambda b: mae(base + b * sel.mono))
    base = base + bm * sel.mono.to_numpy()
    ba = min((0.0, 1.0, 2.0, 4.0), key=lambda b: mae(base + b * sel.agec))
    return {"k": k, "mono": bm, "age": ba}


def main():
    panel = backtest.load_panel(ROOT / "data/processed")
    f = components(pd.read_parquet(ROOT / "results/forecasts/ensemble.parquet"), panel)
    rows = []
    for end in ("2024-03", "2024-04", "2024-05"):
        p = select(f, end)
        x = f.category.map(p["k"]).to_numpy() * f.now + p["mono"] * f.mono + p["age"] * f.agec
        g = f.assign(yhat=f.yhat * np.exp(x))
        if end == "2024-05":
            g[COLS].to_parquet(OUT / "fc_ensemble+robust.parquet")
        for H in (1, 3, 6):
            r = metrics.compare(g[g.origin >= REPORT_FROM][COLS], f[f.origin >= REPORT_FROM][COLS], H, LAST, 2000, 42)
            rows.append({"select_end": end, "k_zero": sum(v == 0 for v in p["k"].values()), "mono": p["mono"], "age": p["age"], **r})
        print(end, p)
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "robust_selection.csv", index=False)
    pd.set_option("display.width", 220)
    print(res[["select_end", "k_zero", "mono", "age", "H", "MAE", "MAE_ref", "gain_pct", "share_series_better", "boot_ci_low", "boot_ci_high"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
