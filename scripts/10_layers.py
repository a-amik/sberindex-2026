"""Сколько ошибки вообще доступно внешним сигналам.

Ошибка прогноза раскладывается на три слоя с подсказкой из факта:
1. общий — медиана лог-ошибки по группе «категория × город/район» в той же
   точке и на том же шаге; её снимает идеальный общероссийский сигнал;
2. региональный — медиана оставшейся лог-ошибки по МО того же субъекта
   и категории, без самого МО (leave-one-out: иначе в малом субъекте медиана
   съедает собственную ошибку МО); её снимает идеальный сигнал субъекта;
3. муниципальный — остаток.

Это верхняя граница пользы сигналов каждого уровня, а не прогноз: идеального
сигнала не бывает. Отдельно — шумовой пол ряда: если отклонение МО от фактора
есть случайное блуждание плюс белый шум измерения, то ковариация соседних
приростов равна −σ²шума. Эту часть ошибки не снимает никакой сигнал.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sbi import backtest, metrics  # noqa: E402
from sbi.models.panel import groups  # noqa: E402

OUT = ROOT / "results/signal_value"
MODELS = ["panel_blend_ses_bytype", "ensemble", "prophet_default"]
REPORT_FROM = "2024-06"
LAST = "2024-12"


def loo_median(v: np.ndarray, g: np.ndarray) -> np.ndarray:
    """Медиана группы без самого элемента; группы из одного элемента — ноль."""
    out = np.zeros_like(v)
    order = np.lexsort((v, g))
    gs, vs = g[order], v[order]
    starts = np.r_[0, np.flatnonzero(gs[1:] != gs[:-1]) + 1]
    ends = np.r_[starts[1:], len(gs)]
    res = np.zeros_like(vs)
    for a, b in zip(starts, ends):
        s = vs[a:b]
        n = b - a
        if n < 3:
            continue
        r = np.arange(n)
        m = n - 1
        pick = lambda k: np.where(k < r, s[np.minimum(k, n - 1)], s[np.minimum(k + 1, n - 1)])
        if m % 2:
            res[a:b] = pick(np.full(n, (m - 1) // 2))
        else:
            res[a:b] = (pick(np.full(n, m // 2 - 1)) + pick(np.full(n, m // 2))) / 2
    out[order] = res
    return out


def main():
    panel = backtest.load_panel(ROOT / "data/processed")
    mo = pd.read_parquet(ROOT / "data/processed/mo.parquet")
    idx = panel.index.merge(mo[["territory_id", "region", "mo_type"]], on="territory_id", how="left")
    g_type = groups(panel.index, mo, "type")
    g_reg = (idx.category.astype(str) + "|" + idx.region.astype(str)).to_numpy()
    rows, by_cat = [], []
    for name in MODELS:
        f = pd.read_parquet(ROOT / f"results/forecasts/{name}.parquet")
        f = f[f.origin >= REPORT_FROM]
        e = np.log(np.clip(f.yhat.to_numpy(), 1e-9, None)) - np.log(f.y.to_numpy())
        key = f.origin.to_numpy() + "|" + f.step.astype(str).to_numpy()
        common = pd.Series(e).groupby(key + "|" + g_type[f.row.to_numpy()]).transform("median").to_numpy()
        e1 = e - common
        reg = loo_median(e1, key + "|" + g_reg[f.row.to_numpy()])
        e2 = e1 - reg
        f = f.assign(y1=f.y * np.exp(e1), y2=f.y * np.exp(e2))
        for H in (1, 3, 6):
            d = metrics.horizon_rows(f, H, LAST)
            mae0 = (d.yhat - d.y).abs().mean()
            mae1 = (d.y1 - d.y).abs().mean()
            mae2 = (d.y2 - d.y).abs().mean()
            rows.append({"model": name, "H": H, "MAE": mae0, "MAE_no_common": mae1, "MAE_no_region": mae2,
                         "common_rub": mae0 - mae1, "region_rub": mae1 - mae2, "mo_rub": mae2})
            if name == "ensemble":
                cat = panel.index.category.astype(str).to_numpy()[d.row.to_numpy()]
                for c in np.unique(cat):
                    s = d[cat == c]
                    by_cat.append({"H": H, "category": c, "MAE": (s.yhat - s.y).abs().mean(),
                                   "common_rub": (s.yhat - s.y).abs().mean() - (s.y1 - s.y).abs().mean(),
                                   "region_rub": (s.y1 - s.y).abs().mean() - (s.y2 - s.y).abs().mean(),
                                   "mo_rub": (s.y2 - s.y).abs().mean()})
    layers = pd.DataFrame(rows)
    layers.to_csv(OUT / "layers.csv", index=False)
    pd.DataFrame(by_cat).to_csv(OUT / "layers_by_category.csv", index=False)

    # шумовой пол: отклонение от медианы группы по всей истории
    lh = np.log(panel.y)
    m = np.zeros_like(lh)
    for gname in np.unique(g_type):
        sel = g_type == gname
        m[sel] = np.median(lh[sel], axis=0)
    dlt = np.diff(lh - m, axis=1)
    c1 = np.mean((dlt[:, 1:] - dlt[:, 1:].mean(1, keepdims=True)) * (dlt[:, :-1] - dlt[:, :-1].mean(1, keepdims=True)), axis=1)
    var = dlt.var(axis=1)
    noise_var = np.clip(-c1, 0, None)
    level = panel.y[:, -12:].mean(axis=1)
    # MAE, которую даёт один только белый шум измерения: E|N(0,σ)| = σ·√(2/π)
    floor_rub = np.sqrt(noise_var) * np.sqrt(2 / np.pi) * level
    noise = pd.DataFrame({"category": panel.index.category.astype(str), "noise_share_of_var": noise_var / np.where(var > 0, var, np.nan),
                          "noise_sd": np.sqrt(noise_var), "floor_rub": floor_rub, "level": level,
                          "lag1_corr": c1 / np.where(var > 0, var, np.nan)})
    noise.to_parquet(OUT / "noise.parquet")
    summary = noise.groupby("category").agg(level=("level", "median"), noise_sd=("noise_sd", "median"),
                                            noise_share=("noise_share_of_var", "median"), lag1_corr=("lag1_corr", "median"),
                                            floor_rub=("floor_rub", "mean"))
    summary.loc["все ряды"] = [noise.level.median(), noise.noise_sd.median(), noise.noise_share_of_var.median(),
                               noise.lag1_corr.median(), noise.floor_rub.mean()]
    summary.to_csv(OUT / "noise_floor.csv")
    pd.set_option("display.width", 200)
    print(layers.round(1).to_string(index=False))
    print(pd.DataFrame(by_cat).query("H == 1").round(1).to_string(index=False))
    print(summary.round(3).to_string())
    json.dump({"report_from": REPORT_FROM, "models": MODELS}, open(OUT / "layers_meta.json", "w"), ensure_ascii=False)


if __name__ == "__main__":
    main()
