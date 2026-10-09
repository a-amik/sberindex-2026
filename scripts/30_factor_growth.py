"""Рост фактора на длинных шагах: недельный годовой прирост вместо роста панели.

Фактор панели на шаге h — m[T+h−12] плюс средний годовой рост группы за три
последних месяца g3. На шагах 4—6 общий слой — почти половина ошибки
(10_layers.py). Сдвиг d = w(T) − g3, где w(T) — недельный годовой прирост
России за месяц T в категории ряда (известен на T), связан с общей ошибкой
шагов 4—6 на 0,77—0,84; рост за месяц, за полгода и затухающий рост — слабее.

Гипотеза без подбираемого параметра: годовой рост фактора берётся из недельного
ряда, то есть прогноз шагов 4—12 умножается на exp(d). Для сравнения —
половинная сила и вариант со сдвигом на всех шагах. База — итоговый прогноз дня
(fc_ensemble+robust), где шаги 1—3 уже поправлены ноукастом. Отчёт — по шагам
отдельно, по точкам с июня 2024 года и по всем точкам.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sbi import backtest, metrics  # noqa: E402
from sbi.models.panel import groups  # noqa: E402

OUT = ROOT / "results/signal_value"
LAST, REPORT_FROM = "2024-12", "2024-06"
COLS = ["row", "origin", "step", "target", "y", "y_origin", "yhat"]
WEEKLY = {"Все категории": ["Все категории "], "Продовольствие": ["Продовольственные товары"],
          "Общественное питание": ["Общественное питание"], "Маркетплейсы": ["Маркетплейсы"],
          "Здоровье": ["Лекарства и медицинские товары", "Медицинские услуги"],
          "Транспорт": ["Локальный транспорт", "Такси, каршеринг, аренда автомобилей", "Топливо"]}


def shift(panel) -> pd.DataFrame:
    mo = pd.read_parquet(ROOT / "data/processed/mo.parquet")
    gt = groups(panel.index, mo, "type")
    lh = np.log(panel.y)
    P = panel.periods
    nat = pd.read_parquet(ROOT / "data/processed/national.parquet").set_index("period")
    wk = {c: np.log1p(nat[[f"weekly_yoy:{x}" for x in v]].mean(axis=1) / 100) for c, v in WEEKLY.items()}
    rows = []
    for g in np.unique(gt):
        m = np.median(lh[gt == g], axis=0)
        for t in range(12, len(P)):
            g3 = np.mean([m[k] - m[k - 12] for k in range(max(12, t - 2), t + 1)])
            w = wk[g.split("|")[0]].get(P[t], np.nan)
            rows.append({"g": g, "origin": P[t], "d": w - g3 if pd.notna(w) else 0.0})
    return pd.DataFrame(rows), gt


def main():
    panel = backtest.load_panel(ROOT / "data/processed")
    d, gt = shift(panel)
    base = pd.read_parquet(OUT / "fc_ensemble+robust.parquet")
    base["g"] = gt[base.row.to_numpy()]
    base = base.merge(d, on=["g", "origin"], how="left").fillna({"d": 0.0})
    variants = {"рост из недельного ряда, шаги 4—12": np.where(base.step >= 4, 1.0, 0.0) * base.d,
                "половина сдвига, шаги 4—12": np.where(base.step >= 4, 0.5, 0.0) * base.d,
                "рост из недельного ряда, все шаги": base.d}
    rows = []
    for name, x in variants.items():
        g = base.assign(yhat=base.yhat * np.exp(x))
        if name.endswith("шаги 4—12") and name.startswith("рост"):
            g[COLS].to_parquet(OUT / "fc_ensemble+robust+growth.parquet")
        for window, lo in (("отчёт", REPORT_FROM), ("все точки", "2023-12")):
            a, b = g[g.origin >= lo], base[base.origin >= lo]
            for h in (1, 3, 4, 5, 6, 9, 12):
                sa, sb = a[a.step == h], b[b.step == h]
                if len(sa):
                    rows.append({"вариант": name, "окно": window, "шаг": h, "точек": sa.origin.nunique(),
                                 "MAE": (sa.yhat - sa.y).abs().mean(), "MAE_до": (sb.yhat - sb.y).abs().mean()})
            for H in (3, 6):
                r = metrics.compare(a[COLS], b[COLS], H, LAST, 2000, 42)
                rows.append({"вариант": name, "окно": window, "шаг": f"H={H}", "точек": None, "MAE": r["MAE"], "MAE_до": r["MAE_ref"],
                             "ci_low": r["boot_ci_low"], "ci_high": r["boot_ci_high"]})
    res = pd.DataFrame(rows)
    res["выигрыш_%"] = (1 - res.MAE / res.MAE_до) * 100
    res.to_csv(OUT / "factor_growth.csv", index=False)
    pd.set_option("display.width", 220)
    print(res.round(2).to_string(index=False))


if __name__ == "__main__":
    main()


def growth_shift() -> tuple[pd.DataFrame, np.ndarray]:
    """Сдвиг роста фактора d_adj по (группа, точка) со смещением по истории до точки:
    из сдвига d(T) вычитается среднее d за прошлые месяцы с известным недельным рядом.
    Если разница темпов России и панели постоянна, остаётся только её отклонение
    от обычного. Нужно не меньше трёх прошлых месяцев, иначе сдвиг нулевой.
    Тот же расчёт служит бэктесту (debiased) и прогнозу вперёд (37_strict.forward)."""
    panel = backtest.load_panel(ROOT / "data/processed")
    d, gt = shift(panel)
    d = d.sort_values(["g", "origin"])
    raw = d.d.where(d.d != 0.0)
    hist = raw.groupby(d.g).transform(lambda s: s.shift(1).expanding(min_periods=3).mean())
    d["d_adj"] = (raw - hist).fillna(0.0)
    return d, gt


def debiased():
    """Та же подмена, но со смещением по истории (growth_shift)."""
    d, gt = growth_shift()
    base = pd.read_parquet(OUT / "fc_ensemble+robust.parquet")
    base["g"] = gt[base.row.to_numpy()]
    base = base.merge(d[["g", "origin", "d_adj"]], on=["g", "origin"], how="left").fillna({"d_adj": 0.0})
    rows = []
    for k in (1.0, 0.5):
        g = base.assign(yhat=base.yhat * np.exp(np.where(base.step >= 4, k, 0.0) * base.d_adj))
        if k == 1.0:
            g[COLS].to_parquet(OUT / "fc_ensemble+robust+growth_adj.parquet")
        for window, lo in (("отчёт", REPORT_FROM), ("все точки", "2023-12")):
            a, b = g[g.origin >= lo], base[base.origin >= lo]
            for h in (4, 5, 6, 9):
                sa, sb = a[a.step == h], b[b.step == h]
                if len(sa):
                    rows.append({"сила": k, "окно": window, "шаг": h, "точек": sa.origin.nunique(),
                                 "MAE": (sa.yhat - sa.y).abs().mean(), "MAE_до": (sb.yhat - sb.y).abs().mean()})
            r = metrics.compare(a[COLS], b[COLS], 6, LAST, 2000, 42)
            rows.append({"сила": k, "окно": window, "шаг": "H=6", "MAE": r["MAE"], "MAE_до": r["MAE_ref"], "ci_low": r["boot_ci_low"], "ci_high": r["boot_ci_high"]})
    res = pd.DataFrame(rows)
    res["выигрыш_%"] = (1 - res.MAE / res.MAE_до) * 100
    res.to_csv(OUT / "factor_growth_debiased.csv", index=False)
    print(res.round(2).to_string(index=False))


def debiased_short():
    """Поправка уровня на шагах 1—3 поверх ноукаста. Ноукаст двигает прогноз
    на ускорение недельного прироста, но не на разницу его уровня с ростом панели;
    здесь добавляется тот же сдвиг со смещением по истории, что на шагах 4—12.
    Подобрать силу на окне отбора нельзя — первые ненулевые сдвиги с точки
    апреля 2024 года, — поэтому основной вариант сила 1, половина для сравнения.
    База — итог с ростом на длинных шагах (fc_ensemble+robust+growth_adj)."""
    panel = backtest.load_panel(ROOT / "data/processed")
    d, gt = shift(panel)
    d = d.sort_values(["g", "origin"])
    raw = d.d.where(d.d != 0.0)
    d["d_adj"] = (raw - raw.groupby(d.g).transform(lambda s: s.shift(1).expanding(min_periods=3).mean())).fillna(0.0)
    base = pd.read_parquet(OUT / "fc_ensemble+robust+growth_adj.parquet")
    base["g"] = gt[base.row.to_numpy()]
    base = base.merge(d[["g", "origin", "d_adj"]], on=["g", "origin"], how="left").fillna({"d_adj": 0.0})
    ens = pd.read_parquet(ROOT / "results/forecasts/ensemble.parquet")
    rows = []
    for k in (1.0, 0.5):
        g = base.assign(yhat=base.yhat * np.exp(np.where(base.step <= 3, k, 0.0) * base.d_adj))
        if k == 1.0:
            pass  # вариант не прошёл: файл итога не пишется
        for window, lo in (("отчёт", REPORT_FROM), ("все точки", "2023-12")):
            for ref_name, ref in (("до поправки", base), ("ансамбль", ens)):
                for H in (1, 3, 6):
                    r = metrics.compare(g[g.origin >= lo][COLS], ref[ref.origin >= lo][COLS], H, LAST, 2000, 42)
                    rows.append({"сила": k, "окно": window, "против": ref_name, "H": H, "MAE": r["MAE"], "MAE_ref": r["MAE_ref"],
                                 "gain_pct": r["gain_pct"], "ci_low": r["boot_ci_low"], "ci_high": r["boot_ci_high"],
                                 "share_better": r["share_series_better"]})
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "factor_growth_short.csv", index=False)
    pd.set_option("display.width", 220)
    print(res.round(2).to_string(index=False))
