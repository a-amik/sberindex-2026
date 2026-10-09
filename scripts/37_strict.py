"""Строгий прогноз: итог без данных о месяце после точки прогноза.

Итог 35_final.py опирается на допущение, что недельные ряды СберИндекса
за месяц T+1 выходят раньше муниципального показателя за месяц T. Его берут
два слоя: недельный ноукаст (шаг 1) и общая часть возрастной активности.
Здесь оба обнулены, остальное — тем же порядком и теми же правилами:
фонд оплаты труда моногородов (лаг публикации два месяца), рост фактора
на шагах 4—12 из недельного ряда на месяц самой точки, конформные интервалы.
Силы выбираются на целях до мая 2024 года, отчёт — точки с июня.

    python scripts/37_strict.py            # бэктест, затем — прогноз вперёд, если есть forward-ансамбль
    python scripts/37_strict.py --forward  # только прогноз вперёд
Итог — results/forecasts/ensemble_strict.parquet и
results/metrics/ensemble_strict.csv (против ансамбля, Prophet и итога с ноукастом);
вперёд — results/forecasts_forward/ensemble_strict.parquet (yhat, lo80…hi90):
это сдаваемая и рабочая модель сайта (web/scripts/export_data.py, MAIN).
"""
from __future__ import annotations

import json

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sbi import backtest, metrics  # noqa: E402

OUT = ROOT / "results/signal_value/strict"
LAST, REPORT_FROM = "2024-12", "2024-06"
COLS = ["row", "origin", "step", "target", "y", "y_origin", "yhat"]


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / f"scripts/{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rs = load("26_robust_selection")
    panel = backtest.load_panel(ROOT / "data/processed")
    f = rs.components(pd.read_parquet(ROOT / "results/forecasts/ensemble.parquet"), panel, with_age=False)  # слой T+1 строгому не нужен
    f = f.assign(now=0.0, agec=0.0)
    p = rs.select(f, "2024-05")
    print("силы:", p)
    json.dump(p, open(OUT / "strengths.json", "w"), ensure_ascii=False)   # силы — прогнозу вперёд
    g = f.assign(yhat=f.yhat * np.exp(p["mono"] * f.mono))
    g[COLS].to_parquet(OUT / "fc_ensemble+robust.parquet")
    fg = load("30_factor_growth")
    fg.OUT = OUT
    fg.debiased()
    s = pd.read_parquet(OUT / "fc_ensemble+robust+growth_adj.parquet")[COLS]
    iv = load("35_final").interval_quantiles(s)
    s = s.merge(iv, on=["row", "origin", "step"], how="left")
    for lv in (80, 90):
        s[f"lo{lv}"] = s.yhat * np.exp(-s[f"q{lv}"])
        s[f"hi{lv}"] = s.yhat * np.exp(s[f"q{lv}"])
    s.drop(columns=["q80", "q90"]).to_parquet(ROOT / "results/forecasts/ensemble_strict.parquet", index=False)
    rows = []
    for ref in ("ensemble", "prophet_default", "ensemble_signals"):
        r = pd.read_parquet(ROOT / f"results/forecasts/{ref}.parquet")
        for window, lo in (("отчёт", REPORT_FROM), ("все точки", "2023-12")):
            for H in (1, 3, 6, 12):
                if H == 12 and window == "отчёт":
                    continue
                c = metrics.compare(s[s.origin >= lo][COLS], r[r.origin >= lo][COLS], H, LAST, 2000, 42)
                rows.append({"против": ref, "окно": window, **c})
    res = pd.DataFrame(rows)
    res.to_csv(ROOT / "results/metrics/ensemble_strict.csv", index=False)
    rep = s[s.origin >= REPORT_FROM]
    cov = [{"шаг": h, "покрытие90": ((d.y >= d.lo90) & (d.y <= d.hi90)).mean()} for h, d in rep.groupby("step") if h in (1, 3, 6)]
    pd.set_option("display.width", 220)
    print(res[["против", "окно", "H", "MAE", "MAE_ref", "gain_pct", "share_series_better", "boot_ci_low", "boot_ci_high"]].round(2).to_string(index=False))
    print(pd.DataFrame(cov).round(3).to_string(index=False))
    if (ROOT / "results/forecasts_forward/ensemble.parquet").exists():
        forward()


def forward():
    """Строгий прогноз вперёд от декабря 2024: forward-ансамбль (та же свёртка, что в бэктесте)
    × сдвиг роста фактора на шагах 4+ (сила 1, как в бэктесте) × ФОТ моногородов на шагах 1—3
    с силой из отбора (на окне до мая 2024 она ноль). Интервалы — конформные квантили
    лог-остатков строгого бэктеста по категории и шагу, не убывающие с шагом; дальше
    последнего шага с тремя и более точками прогноза (h0 = 10) — q(h0)·√(h/h0).
    В бэктесте сдвиг роста проверен на шагах 4—6: точкам без трёх месяцев истории он нулевой."""
    FW = ROOT / "results/forecasts_forward"
    base = pd.read_parquet(FW / "ensemble.parquet").sort_values(["row", "target"]).reset_index(drop=True)
    base["step"] = base.groupby("row").cumcount() + 1
    panel = backtest.load_panel(ROOT / "data/processed")
    d, gt = load("30_factor_growth").growth_shift()
    adj = d[d.origin == LAST].set_index("g").d_adj
    g = pd.Series(gt[base.row.to_numpy()])
    shift = np.where(base.step >= 4, g.map(adj).fillna(0.0).to_numpy(), 0.0)
    p = json.load(open(OUT / "strengths.json")) if (OUT / "strengths.json").exists() else {"mono": 0.0}
    mono = np.zeros(len(base))
    if p.get("mono"):
        mo = pd.read_parquet(ROOT / "data/processed/mo.parquet")
        is_mono = np.isin(panel.index.territory_id.to_numpy(), mo[mo.mono_status.str.strip() != ""].territory_id)[base.row.to_numpy()]
        sig = load("21_monotowns").signal().get(LAST, 0.0)
        mono = np.where(is_mono & (base.step <= 3), p["mono"] * sig, 0.0)
    out = base.assign(yhat=base.yhat * np.exp(shift + mono))
    # Интервалы: остатки строгого бэктеста, все цели уже наступили.
    bt = pd.read_parquet(ROOT / "results/forecasts/ensemble_strict.parquet", columns=["row", "origin", "step", "y", "yhat"])
    cats = panel.index.category.astype(str).to_numpy()
    bt["category"] = cats[bt.row.to_numpy()]
    bt["r"] = np.abs(np.log(bt.y / bt.yhat))
    out["category"] = cats[out.row.to_numpy()]
    for lv in (80, 90):
        q = bt.groupby(["category", "step"]).r.quantile(lv / 100)
        n = bt.groupby(["category", "step"]).origin.nunique()
        q = q[n >= 3]
        # Квантиль по шагам считается на 3—12 точках, и шаг 8 выходил уже шага 7:
        # интервал не должен сужаться с горизонтом — берётся накопленный максимум.
        q = q.groupby(level="category").cummax()
        h0 = q.reset_index().groupby("category").step.max()
        key = pd.MultiIndex.from_arrays([out.category, out.step.clip(upper=out.category.map(h0).to_numpy())])
        qv = key.map(q.to_dict()).to_numpy(float) * np.sqrt(out.step / np.minimum(out.step, out.category.map(h0).to_numpy()))
        out[f"lo{lv}"], out[f"hi{lv}"] = out.yhat * np.exp(-qv), out.yhat * np.exp(qv)
    out = out[["row", "target", "yhat", "lo80", "hi80", "lo90", "hi90"]]
    out.to_parquet(FW / "ensemble_strict.parquet", index=False)
    print(f"вперёд: {out.row.nunique()} рядов × {out.groupby('row').size().iloc[0]} шагов → forecasts_forward/ensemble_strict.parquet; "
          f"сдвиг роста по группам: {adj.round(3).to_dict()}")


if __name__ == "__main__":
    if "--forward" in sys.argv:
        forward()
    else:
        main()
