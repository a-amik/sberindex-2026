"""Сигналы общего фактора: календарь месяца и недельный ноукаст.

Разложение ошибки (10_layers.py) показало, что общий слой — главный
доступный резерв: на шесть месяцев он почти половина MAE. Здесь два
сигнала, которые известны на дату прогноза и бьют именно в него.

Календарь. Фактор панели прогнозируется как m[T+h−12] плюс средний рост
г/г за три последних месяца. Если в целевом месяце на день больше, чем год
назад (февраль 2024-го), или другой состав выходных, этого прогноз не видит.
Эффект календаря оценивается по общероссийскому ряду СберИндекса с 2019 года
на месяцах до точки прогноза: годовой прирост минус среднее соседних месяцев
против того же преобразования календаря (лог числа дней, доля нерабочих).
Месяцы ковидной базы (2020-03…2021-06) исключены.

Ноукаст. Недельные расходы СберИндекса по России выходят с лагом около
недели, муниципальные — позже. Если к публикации месяца T недельный ряд
месяца T+1 уже есть, поправка шага 1 — ускорение недельного прироста г/г
против трёх последних месяцев. Недельный прирост считается к той же неделе
прошлого года, поэтому календаря в нём нет и сигналы не дублируют друг друга.
Лаг публикации — допущение, его надо подтвердить у владельца данных.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sbi import backtest, metrics  # noqa: E402
from sbi.config import load as load_cfg  # noqa: E402

OUT = ROOT / "results/signal_value"
LAST = "2024-12"
REPORT_FROM = "2024-06"
COVID = ("2020-03", "2021-06")
WEEKLY = {
    "Все категории": ["Все категории "],
    "Продовольствие": ["Продовольственные товары"],
    "Общественное питание": ["Общественное питание"],
    "Маркетплейсы": ["Маркетплейсы"],
    "Здоровье": ["Лекарства и медицинские товары", "Медицинские услуги"],
    "Транспорт": ["Локальный транспорт", "Такси, каршеринг, аренда автомобилей", "Топливо"],
}


def calendar_table() -> pd.DataFrame:
    """Производственный календарь 2018—2025 годов по дням (isdayoff.ru); качается один раз."""
    path = OUT / "days_2018_2025.parquet"
    if not path.exists():
        from sbi import net
        s, rows = net.session(), []
        for y in range(2018, 2026):
            flags = net.fetch(s, f"https://isdayoff.ru/api/getdata?year={y}").text.strip()
            rows.append(pd.DataFrame({"date": pd.date_range(f"{y}-01-01", periods=len(flags), freq="D"),
                                      "off": [int(c) for c in flags]}))
        OUT.mkdir(parents=True, exist_ok=True)
        pd.concat(rows).to_parquet(path)
    d = pd.read_parquet(path)
    d["period"] = d.date.dt.strftime("%Y-%m")
    g = d.groupby("period")
    return pd.DataFrame({"ldays": np.log(g.size()), "off": g.off.mean()})


def calendar_betas(nat: pd.Series, cal: pd.DataFrame, upto: str) -> np.ndarray:
    """β по лог-приросту г/г: x(t) − (x(t−1) + x(t+1))/2 снимает тренд, остаётся календарь."""
    s = np.log(nat.dropna())
    yoy = (s - s.shift(12)).dropna()
    c12 = (cal - cal.shift(12)).reindex(yoy.index)
    dd = lambda x: x - (x.shift(1) + x.shift(-1)) / 2
    y, X = dd(yoy), c12.apply(dd)
    ok = y.notna() & X.notna().all(axis=1) & (y.index < upto)
    ok &= ~((y.index >= COVID[0]) & (y.index <= COVID[1]))
    ok &= ~((y.index >= "2021-03") & (y.index <= "2022-06"))   # годовая база ковидных месяцев
    beta, *_ = np.linalg.lstsq(X[ok].to_numpy(), y[ok].to_numpy(), rcond=None)
    return beta


def main():
    cfg = load_cfg()
    panel = backtest.load_panel(ROOT / "data/processed")
    cats = panel.index.category.astype(str).to_numpy()
    nat = pd.read_parquet(ROOT / "data/processed/national.parquet").set_index("period")
    cal = calendar_table()
    c12 = cal - cal.shift(12)
    ntype = cfg["models"]["snaive_growth"]["national_type"]
    wk = pd.DataFrame({c: np.log1p(nat[[f"weekly_yoy:{x}" for x in cols]].mean(axis=1) / 100)
                       for c, cols in WEEKLY.items()})

    betas, adj_rows = [], []
    origins = sorted(pd.read_parquet(ROOT / "results/forecasts/panel_blend_ses_bytype.parquet", columns=["origin"]).origin.unique())
    for o in origins:
        T = pd.Period(o, "M")
        recent = [str(T - k) for k in range(3)]
        for c in WEEKLY:
            b = calendar_betas(nat[f"spend_bn:{ntype[c]}"], cal, o)
            betas.append({"origin": o, "category": c, "b_ldays": b[0], "b_off": b[1]})
            base_cal = c12.loc[recent].mean().to_numpy() @ b
            w_recent = wk.loc[[r for r in recent if r in wk.index], c].dropna()
            for h in range(1, 13):
                t = str(T + h)
                if t > LAST:
                    break
                cal_adj = c12.loc[t].to_numpy() @ b - base_cal
                now = wk.at[t, c] - w_recent.mean() if (h == 1 and len(w_recent) and pd.notna(wk.at[t, c])) else 0.0
                adj_rows.append({"origin": o, "step": h, "category": c, "cal": cal_adj, "now": now})
    betas = pd.DataFrame(betas)
    adj = pd.DataFrame(adj_rows)
    betas.to_csv(OUT / "calendar_betas.csv", index=False)
    adj.to_csv(OUT / "factor_adjustments.csv", index=False)

    results, made = [], {}
    for name in ["panel_blend_ses_bytype", "ensemble"]:
        f = pd.read_parquet(ROOT / f"results/forecasts/{name}.parquet")
        f["category"] = cats[f.row.to_numpy()]
        f = f.merge(adj, on=["origin", "step", "category"], how="left").fillna({"cal": 0.0, "now": 0.0})
        # сила ноукаста — на окне выбора: шаг 1, цели до мая 2024
        sel = f[(f.step == 1) & (f.target <= "2024-05")]
        mae = {k: (sel.yhat * np.exp(k * sel.now) - sel.y).abs().mean() for k in (0.0, 0.5, 1.0)}
        k_now = min(mae, key=mae.get)
        variants = {"cal": f.cal, "now": k_now * f.now, "cal_now": f.cal + k_now * f.now}
        for v, a in variants.items():
            g = f.assign(yhat=f.yhat * np.exp(a))[["row", "origin", "step", "target", "y", "y_origin", "yhat"]]
            made[f"{name}+{v}"] = g
            g.to_parquet(OUT / f"fc_{name}+{v}.parquet")
            for window, src in (("отчёт", g[g.origin >= REPORT_FROM]), ("все точки", g)):
                ref = f[f.origin >= REPORT_FROM] if window == "отчёт" else f
                for H in (1, 3, 6):
                    r = metrics.compare(src, ref[["row", "origin", "step", "target", "y", "y_origin", "yhat"]], H, LAST, 2000, 42)
                    results.append({"base": name, "variant": v, "k_now": k_now, "window": window, **r})
        print(name, "сила ноукаста на окне выбора:", {k: round(v, 1) for k, v in mae.items()}, "→", k_now)
    res = pd.DataFrame(results)
    res.to_csv(OUT / "factor_signals.csv", index=False)
    pd.set_option("display.width", 220)
    print(betas.groupby("category")[["b_ldays", "b_off"]].agg(["min", "max"]).round(2))
    print(res[["base", "variant", "k_now", "window", "H", "MAE", "MAE_ref", "gain_pct", "share_series_better", "boot_ci_low", "boot_ci_high"]].round(3).to_string(index=False))




def per_category():
    """Сила ноукаста своя у каждой категории: выбор на целях до мая 2024, отчёт с июня.
    Недельные категории сопоставлены с категориями набора по названию, и у
    «Маркетплейсов», «Здоровья» и «Транспорта» сопоставление приблизительное."""
    panel = backtest.load_panel(ROOT / "data/processed")
    cats = panel.index.category.astype(str).to_numpy()
    adj = pd.read_csv(OUT / "factor_adjustments.csv")
    rows = []
    for name in ["panel_blend_ses_bytype", "ensemble"]:
        f = pd.read_parquet(ROOT / f"results/forecasts/{name}.parquet")
        f["category"] = cats[f.row.to_numpy()]
        f = f.merge(adj, on=["origin", "step", "category"], how="left").fillna({"now": 0.0})
        sel = f[(f.step == 1) & (f.target <= "2024-05")]
        k = {}
        for c, s in sel.groupby("category"):
            mae = {kk: (s.yhat * np.exp(kk * s.now) - s.y).abs().mean() for kk in (0.0, 0.5, 1.0)}
            k[c] = min(mae, key=mae.get)
        g = f.assign(yhat=f.yhat * np.exp(f.category.map(k) * f.now))
        cols = ["row", "origin", "step", "target", "y", "y_origin", "yhat"]
        g[cols].to_parquet(OUT / f"fc_{name}+now_bycat.parquet")
        for H in (1, 3, 6):
            r = metrics.compare(g[g.origin >= REPORT_FROM][cols], f[f.origin >= REPORT_FROM][cols], H, LAST, 2000, 42)
            rows.append({"base": name, "k": k, **r})
        for c in WEEKLY:
            s, b = g[(g.step == 1) & (g.origin >= REPORT_FROM) & (g.category == c)], f[(f.step == 1) & (f.origin >= REPORT_FROM) & (f.category == c)]
            rows.append({"base": name, "category": c, "H": "шаг 1", "MAE": (s.yhat - s.y).abs().mean(), "MAE_ref": (b.yhat - b.y).abs().mean(), "k_cat": k[c]})
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "nowcast_bycat.csv", index=False)
    print(res.drop(columns=["k"]).round(3).to_string(index=False))
    print(k)


if __name__ == "__main__":
    main()
    per_category()
