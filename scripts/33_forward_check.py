"""Шаг 33. Сверка прогноза вперёд с фактом 2025—2026 годов по России.

Панель МО кончается декабрём 2024, за 2025 год по МО данных нет. Зато у СберИндекса
есть ряд России до августа 2026: месячные расходы по пяти категориям и месячные
средние недельного годового прироста по 46 категориям (national.parquet). Прогноз
каждой модели (шаг 17) сворачивается в ряд России с весом по населению МО, и его
рост к тому же месяцу 2024 года сравнивается с фактическим ростом России. Это
проверка общего фактора — слоя, на который приходится до половины ошибки на длинных
шагах, — на данных, которых ни одна модель не видела.

Сравниваются темпы, а не уровни: панель покрывает не всю страну, и уровни
несопоставимы. Для 2026 года рост берётся за два года к 2024-му: факт —
произведение годовых приростов. Факт двух видов: недельный ряд по всем шести
категориям панели (сопоставление категорий — как в шаге 30) и месячный
официальный ряд по трём, где он есть. У общепита в январе 2025 ступенька методики
в месячном ряду — его два факта показаны рядом.

    python scripts/33_forward_check.py

Выход — results/forward_check/: paths.csv (помесячно), summary.csv (ошибка в п.п.
и в рублях на жителя по модели, категории и году), note.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sbi import backtest  # noqa: E402
from sbi.models.panel import groups  # noqa: E402

OUT = ROOT / "results/forward_check"
FWD = ROOT / "results/forecasts_forward"
WEEKLY = {"Все категории": ["Все категории "], "Продовольствие": ["Продовольственные товары"],
          "Общественное питание": ["Общественное питание"], "Маркетплейсы": ["Маркетплейсы"],
          "Здоровье": ["Лекарства и медицинские товары", "Медицинские услуги"],
          "Транспорт": ["Локальный транспорт", "Такси, каршеринг, аренда автомобилей", "Топливо"]}
MONTHLY = {"Все категории": "Всего", "Продовольствие": "Продовольственные товары",
           "Общественное питание": "Общественное питание"}
MODELS = {"ensemble": "ансамбль", "prophet_default": "Prophet", "snaive_growth": "сезонная наивная с ростом",
          "panel_blend_sesseas_bytype": "панельная база", "chronos2_dev": "Chronos-2", "lgbm": "LightGBM"}
LAST_FACT = "2026-08"


def growth_shift(panel, nat):
    """Сдвиг d = w(2024-12) − g3 по группе категория|тип, как в шаге 30."""
    mo = pd.read_parquet(ROOT / "data/processed/mo.parquet")
    gt = groups(panel.index, mo, "type")
    lh = np.log(panel.y)
    t = len(panel.periods) - 1
    out = {}
    for g in np.unique(gt):
        m = np.median(lh[gt == g], axis=0)
        g3 = np.mean([m[k] - m[k - 12] for k in range(t - 2, t + 1)])
        cols = [f"weekly_yoy:{x}" for x in WEEKLY[g.split("|")[0]]]
        w = np.log1p(nat.loc["2024-12", cols].mean() / 100)
        out[g] = w - g3
    return np.array([out[g] for g in gt])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    panel = backtest.load_panel(ROOT / "data/processed")
    mo = pd.read_parquet(ROOT / "data/processed/mo.parquet").set_index("territory_id")
    nat = pd.read_parquet(ROOT / "data/processed/national.parquet").set_index("period")
    idx = panel.index.copy()
    idx["pop"] = mo.pop_.reindex(idx.territory_id).to_numpy() if "pop_" in mo else mo["pop"].reindex(idx.territory_id).to_numpy()
    idx["pop"] = idx["pop"].fillna(idx["pop"].median())
    cats = list(WEEKLY)

    def agg(values: np.ndarray) -> pd.Series:
        """Взвешенное по населению среднее на жителя по категориям."""
        d = pd.DataFrame({"category": idx.category.to_numpy(), "v": values * idx["pop"].to_numpy(), "w": idx["pop"].to_numpy()})
        s = d.groupby("category", observed=True).sum()
        return s.v / s.w

    base24 = {m: agg(panel.y[:, panel.pos(f"2024-{m:02d}")]) for m in range(1, 13)}
    level24 = pd.DataFrame(base24).mean(axis=1)

    # факт: рост к тому же месяцу 2024 года
    fact = []
    for p in nat.index:
        if not ("2025-01" <= p <= LAST_FACT):
            continue
        y, m = p.split("-")
        for c in cats:
            w = nat.loc[p, [f"weekly_yoy:{x}" for x in WEEKLY[c]]].mean() / 100
            if y == "2026":
                w25 = nat.loc[f"2025-{m}", [f"weekly_yoy:{x}" for x in WEEKLY[c]]].mean() / 100
                w = (1 + w25) * (1 + w) - 1
            row = {"category": c, "target": p, "fact_weekly": w}
            if c in MONTHLY:
                col = f"spend_yoy_nominal:{MONTHLY[c]}"
                v = nat.loc[p, col] / 100
                if y == "2026":
                    v = (1 + nat.loc[f"2025-{m}", col] / 100) * (1 + v) - 1
                row["fact_monthly"] = v
            fact.append(row)
    fact = pd.DataFrame(fact)

    # разрыв темпов панели и России внутри истории: факт панели 2024 к 2023 против недельного ряда
    gap_rows = []
    for m in range(1, 13):
        a24 = base24[m]
        a23 = agg(panel.y[:, panel.pos(f"2023-{m:02d}")])
        for c in cats:
            w = nat.loc[f"2024-{m:02d}", [f"weekly_yoy:{x}" for x in WEEKLY[c]]].mean() / 100
            gap_rows.append({"category": c, "month": m, "panel_yoy": a24[c] / a23[c] - 1, "fact_weekly": w})
    gap = pd.DataFrame(gap_rows)
    gap["gap"] = gap.panel_yoy - gap.fact_weekly
    gap.to_csv(OUT / "gap_2024.csv", index=False)
    gap_mean = gap.groupby("category").gap.mean()

    # прогнозы
    paths = []
    variants = {}
    for key, name in MODELS.items():
        f = FWD / f"{key}.parquet"
        if f.exists():
            variants[name] = pd.read_parquet(f)
    if "ансамбль" in variants:
        d = growth_shift(panel, nat)
        e = variants["ансамбль"]
        step = e.target.map(lambda t: (int(t[:4]) - 2025) * 12 + int(t[5:]))
        variants["ансамбль + рост из недельного ряда (шаги 4+)"] = e.assign(yhat=e.yhat * np.exp(np.where(step >= 4, d[e.row.to_numpy()], 0.0)))
        variants["ансамбль + рост из недельного ряда (все шаги)"] = e.assign(yhat=e.yhat * np.exp(d[e.row.to_numpy()]))
    for name, f in variants.items():
        for p, g in f.groupby("target"):
            if not ("2025-01" <= p <= LAST_FACT):
                continue
            g = g.sort_values("row")
            if len(g) != len(idx):
                continue
            a = agg(g.yhat.to_numpy())
            m = int(p[5:])
            for c in cats:
                paths.append({"model": name, "category": c, "target": p, "forecast": a[c] / base24[m][c] - 1})
    paths = pd.DataFrame(paths).merge(fact, on=["category", "target"], how="left")
    paths["err_weekly"] = paths.forecast - paths.fact_weekly
    # с поправкой на разрыв 2024 года: за год — разрыв, за два — удвоенный
    years = paths.target.str[:4].map({"2025": 1, "2026": 2}).astype(float)
    paths["err_adj"] = paths.err_weekly - years * paths.category.map(gap_mean)
    paths["err_monthly"] = paths.forecast - paths.fact_monthly
    paths["year"] = paths.target.str[:4]
    paths.to_csv(OUT / "paths.csv", index=False)

    rows = []
    for (model, c, y), g in paths.groupby(["model", "category", "year"]):
        rows.append({"модель": model, "категория": c, "год": y, "месяцев": len(g),
                     "смещение_пп": g.err_weekly.mean() * 100, "MAE_пп": g.err_weekly.abs().mean() * 100,
                     "MAE_руб_на_жителя": g.err_weekly.abs().mean() * level24[c],
                     "смещение_пп_без_разрыва": g.err_adj.mean() * 100, "MAE_пп_без_разрыва": g.err_adj.abs().mean() * 100,
                     "MAE_пп_мес_ряд": g.err_monthly.abs().mean() * 100 if g.err_monthly.notna().any() else np.nan})
    summary = pd.DataFrame(rows)
    summary.to_csv(OUT / "summary.csv", index=False)

    pd.set_option("display.width", 240)
    pd.set_option("display.max_rows", 500)
    print("Факт России, рост к тому же месяцу 2024 года, %:")
    show = fact.pivot_table(index="target", columns="category", values="fact_weekly") * 100
    print(show.round(1).to_string())
    print("\nМесячный официальный ряд против недельного (общепит — ступенька методики):")
    print((fact[fact.category == "Общественное питание"].set_index("target")[["fact_weekly", "fact_monthly"]] * 100).round(1).T.to_string())
    print("\nРазрыв темпов панели и России в 2024 году, п.п. (панель минус Россия):")
    print((gap.pivot_table(index="month", columns="category", values="gap") * 100).round(1).to_string())
    print("среднее:", (gap_mean * 100).round(1).to_dict())
    print("\nОшибка роста по модели, категории и году (п.п. и рубли на жителя 2024 года):")
    print(summary.round(1).to_string(index=False))
    tot = summary[summary.категория == "Все категории"].pivot_table(index="модель", columns="год", values=["смещение_пп", "MAE_пп", "смещение_пп_без_разрыва", "MAE_пп_без_разрыва"])
    print("\n«Все категории»:")
    print(tot.round(1).to_string())
    with open(OUT / "note.md", "w") as fh:
        fh.write("# Сверка прогноза вперёд с фактом России 2025—2026\n\n")
        fh.write("Факт — месячные средние недельного годового прироста СберИндекса, прогноз — свёртка по МО с весом по населению; 2026 год — рост за два года к 2024-му.\n\n")
        fh.write(tot.round(1).to_string() + "\n\n")
        fh.write(summary.round(1).to_string(index=False) + "\n")


if __name__ == "__main__":
    main()
