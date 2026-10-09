"""Шаг 42б. Миграция как медленный признак прогноза — честная проверка.

Связь «сальдо миграции прошлого года → рост расходов МО» оценена на 2023 → 2024,
а это окно, по которому считает жюри. Чтобы не подгонять модель под проверку,
коэффициент берётся на предыдущем переходе — «сальдо 2022 → рост 2023» — по тому же
годовому срезу внутри субъекта × типа (рост 2023 к 2022 для панели недоступен:
панель начинается в январе 2023, поэтому используется рост за второе полугодие 2023
к первому — грубо, но вне окна). Затем прогноз дня (fc_ensemble+robust) получает
множитель exp(β · z · h / 12), где z — сальдо 2023 на 1 000 жителей в единицах σ
внутри субъекта × типа, h — шаг; сравнение по H = 3, 6, 12 на отчётном окне
и по всем точкам, с бутстрапом по месяцам.

Второй вариант коэффициента — «из литературы» без оценки: β = 0,3 п. п. роста на 1 σ,
то же, что получилось на 2023 → 2024, — показан для сравнения, но решением не является.

    python scripts/42b_migration_forecast.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sbi import backtest, metrics  # noqa: E402
from sbi.models.panel import URBAN  # noqa: E402

OUT = ROOT / "results/forward_check"
LAST, REPORT_FROM = "2024-12", "2024-06"
COLS = ["row", "origin", "step", "target", "y", "y_origin", "yhat"]


def main():
    panel = backtest.load_panel(ROOT / "data/processed")
    mo = pd.read_parquet(ROOT / "data/processed/mo.parquet").set_index("territory_id")
    key = mo.oktmo8.astype(str).str.zfill(8)
    mig = pd.read_parquet(ROOT / "data/external/bdmo/migration_years.parquet")
    piv = mig.pivot_table(index="oktmo", columns="year", values="migr_in")
    pop = mo["pop"].to_numpy(dtype=float)
    m22 = piv.get(2022).reindex(key).to_numpy() / pop * 1000
    m23 = piv.get(2023).reindex(key).to_numpy() / pop * 1000
    # где 2023 нет — последний доступный, как в сервисе
    last = piv.ffill(axis=1).iloc[:, -1].reindex(key).to_numpy() / pop * 1000
    m23 = np.where(np.isnan(m23), last, m23)
    idx = panel.index.copy()
    idx["kind"] = np.where(mo.mo_type.reindex(idx.territory_id).isin(URBAN).to_numpy(), "город", "район")
    idx["region"] = mo.region_key.reindex(idx.territory_id).to_numpy()
    tid = idx.territory_id.to_numpy()
    pos = {t: i for i, t in enumerate(mo.index)}
    idx["m22"] = [m22[pos[t]] for t in tid]
    idx["m23"] = [m23[pos[t]] for t in tid]
    P = panel.periods
    h1 = panel.y[:, [P.index(f"2023-{k:02d}") for k in range(1, 7)]].sum(axis=1)
    h2 = panel.y[:, [P.index(f"2023-{k:02d}") for k in range(7, 13)]].sum(axis=1)
    y23 = panel.y[:, [P.index(f"2023-{k:02d}") for k in range(1, 13)]].sum(axis=1)
    y24 = panel.y[:, [P.index(f"2024-{k:02d}") for k in range(1, 13)]].sum(axis=1)
    idx["g23h"] = np.log(h2 / h1)          # внутри 2023: второе полугодие к первому
    idx["g24"] = np.log(y24 / y23)

    def within(d, cols):
        d = d.copy()
        for c in cols:
            d[c] = d[c] - d.groupby(["region", "kind"])[c].transform("mean")
        return d

    rows = []
    for cat in ["Все категории", "Продовольствие", "Здоровье"]:
        d = idx[idx.category.astype(str) == cat].dropna(subset=["m22", "m23", "g23h", "g24"])
        w = within(d, ["m22", "m23", "g23h", "g24"])
        sd22, sd23 = w.m22.std(), w.m23.std()
        r_pre = sm.OLS(w.g23h.to_numpy() * 100, sm.add_constant((w.m22 / sd22).to_numpy())).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(w.region)[0]})
        r_post = sm.OLS(w.g24.to_numpy() * 100, sm.add_constant((w.m23 / sd23).to_numpy())).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(w.region)[0]})
        rows.append({"категория": cat, "n": len(w), "β_2022→2023 (полугодия), п.п. на 1σ": r_pre.params[1], "t": r_pre.tvalues[1], "β_2023→2024, п.п. на 1σ": r_post.params[1], "t ": r_post.tvalues[1]})
    est = pd.DataFrame(rows)
    pd.set_option("display.width", 220)
    print(est.round(3).to_string(index=False))
    beta_pre = float(est.loc[est.категория == "Все категории", "β_2022→2023 (полугодия), п.п. на 1σ"].iloc[0])
    # полугодовой коэффициент — за полгода; к году он удваивается
    beta_year = beta_pre * 2
    print(f"\nкоэффициент вне окна: {beta_pre:.3f} п.п. за полугодие на 1σ → {beta_year:.3f} п.п. в год")

    # z по всей панели: внутри субъекта × типа, по сальдо 2023 (последнему доступному)
    allw = within(idx.assign(m23=idx.m23.fillna(idx.m23.median())), ["m23"])
    z = (allw.m23 / allw.m23.std()).to_numpy()
    base = pd.read_parquet(ROOT / "results/signal_value/fc_ensemble+robust.parquet")
    res = []
    for name, b in (("β вне окна (2022→2023)", beta_year), ("β из окна (2023→2024), только для сравнения", 0.32)):
        for steps_name, lo in (("все шаги", 1), ("шаги 6—12", 6)):
            mult = np.exp((b / 100) * z[base.row.to_numpy()] * base.step.to_numpy() / 12)
            g = base.assign(yhat=np.where(base.step >= lo, base.yhat * mult, base.yhat))
            for window, from_ in (("отчёт", REPORT_FROM), ("все точки", "2023-12")):
                a, bb = g[g.origin >= from_][COLS], base[base.origin >= from_][COLS]
                for H in (3, 6, 12):
                    r = metrics.compare(a, bb, H, LAST, 1000, 42)
                    res.append({"вариант": name, "шаги": steps_name, "окно": window, "H": H, "MAE": r["MAE"], "MAE_до": r["MAE_ref"], "выигрыш_%": r["gain_pct"], "доля_рядов_лучше": r["share_series_better"], "ci_low": r["boot_ci_low"], "ci_high": r["boot_ci_high"]})
    out = pd.DataFrame(res)
    out.to_csv(OUT / "migration_forecast.csv", index=False)
    print(out.round(2).to_string(index=False))


if __name__ == "__main__":
    main()
