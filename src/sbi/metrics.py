"""Метрики и сравнение с базовой моделью.

MAE в рублях на жителя — главная метрика конкурса. R² по уровням приводится
по условию, но близок к единице у любой разумной модели: уровни расходов
различаются между МО в разы. Содержательный R² — по приросту: доля дисперсии
лог-изменения от точки прогноза, которую модель объясняет.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def horizon_rows(f: pd.DataFrame, H: int, last: str) -> pd.DataFrame:
    """Шаги 1…H в тех точках, где окно T+H целиком в данных."""
    ok_origins = sorted(o for o in f.origin.unique() if pd.Period(o, "M") + H <= pd.Period(last, "M"))
    return f[f.origin.isin(ok_origins) & (f.step <= H)]


def scores(d: pd.DataFrame) -> dict:
    e = d.yhat - d.y
    g_true = np.log(d.y / d.y_origin)
    g_pred = np.log(np.clip(d.yhat, 1e-9, None) / d.y_origin)
    r2 = lambda t, p: 1 - ((t - p) ** 2).sum() / ((t - t.mean()) ** 2).sum()
    return {
        "MAE": e.abs().mean(),
        "RMSE": np.sqrt((e ** 2).mean()),
        "WAPE": e.abs().sum() / d.y.abs().sum() * 100,
        "R2": r2(d.y, d.yhat),
        "R2_growth": r2(g_true, g_pred),
        "n": len(d),
    }


def table(forecasts: dict[str, pd.DataFrame], horizons, last: str) -> pd.DataFrame:
    rows = []
    for name, f in forecasts.items():
        for H in horizons:
            d = horizon_rows(f, H, last)
            rows.append({"model": name, "H": H, "origins": d.origin.nunique(), **scores(d)})
    return pd.DataFrame(rows)


def compare(f: pd.DataFrame, ref: pd.DataFrame, H: int, last: str, n_boot: int, seed: int) -> dict:
    """Модель против базовой на одних и тех же парах.

    * Уилкоксон по рядам: ошибка усредняется внутри ряда, и зависимость между
      точками прогноза одного ряда снимается;
    * доля рядов, где модель точнее;
    * блочный бутстрап по целевым месяцам: месяц — единица ресэмплинга,
      потому что ошибки в одном месяце связаны общим шоком у всех МО.
    """
    a = horizon_rows(f, H, last).set_index(["row", "origin", "step"])
    b = horizon_rows(ref, H, last).set_index(["row", "origin", "step"])
    j = a[["target", "y", "yhat"]].join(b[["yhat"]], rsuffix="_ref", how="inner")
    j["d"] = (j.yhat - j.y).abs() - (j.yhat_ref - j.y).abs()
    per_series = j.groupby(level="row").d.mean()
    w = stats.wilcoxon(per_series) if (per_series != 0).any() else None
    by_month = j.groupby("target").d.agg(["sum", "size"])
    rng = np.random.default_rng(seed)
    months = by_month.index.to_numpy()
    boots = []
    for _ in range(n_boot):
        pick = by_month.loc[rng.choice(months, len(months))]
        boots.append(pick["sum"].sum() / pick["size"].sum())
    mae_m, mae_r = (j.yhat - j.y).abs().mean(), (j.yhat_ref - j.y).abs().mean()
    return {
        "H": H, "MAE": mae_m, "MAE_ref": mae_r, "gain_pct": (1 - mae_m / mae_r) * 100,
        "share_series_better": float((per_series < 0).mean()),
        "wilcoxon_p": float(w.pvalue) if w else 1.0,
        "boot_ci_low": float(np.percentile(boots, 2.5)), "boot_ci_high": float(np.percentile(boots, 97.5)),
        "target_months": len(months),
    }
