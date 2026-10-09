"""Шаг 41. Соцдем и миграция против роста МО — годовой срез, как у отраслей (шаг 38).

Вопрос участника: стоит ли учитывать половозрастную структуру и миграцию. Проверка та же,
что для отраслей: рост 2024 к 2023 по МО против признаков, внутри субъекта × типа МО,
чтобы не ловить разницу городов и районов. Две цели: расходы на жителя (то, что
прогнозируем) и рынок МО целиком (расходы × население — то, что выбирает заказчик).

Признаки:
* доля 65+, доля 0—14, доля 15—34 — Росстат, возраст МО на 01.01.2023 (age_mo_2023);
* миграционный прирост 2023 года на 1 000 жителей — БД ПМО, показатель 8112023
  (все направления, все возрасты), если файл скачан; иначе пропускается;
* прирост населения 2023→2024 на жителя (как в шаге 20) — для сравнения.

    python scripts/41_socdem_annual.py

Выход — results/forward_check/socdem_annual.csv.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sbi import backtest  # noqa: E402
from sbi.models.panel import URBAN  # noqa: E402

OUT = ROOT / "results/forward_check"
MIG = ROOT / "data/external/bdmo/migration_2023.parquet"


def migration() -> pd.DataFrame | None:
    if not MIG.exists():
        return None
    return pd.read_parquet(MIG).set_index("oktmo")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    panel = backtest.load_panel(ROOT / "data/processed")
    mo = pd.read_parquet(ROOT / "data/processed/mo.parquet").set_index("territory_id")
    age = pd.read_parquet(ROOT / "data/external/rosstat/age_mo_2023.parquet")
    age = age[age.total > 0].drop_duplicates("oktmo8").set_index("oktmo8")
    key = mo.oktmo8.astype(str).str.zfill(8)
    a = age.reindex(key.to_numpy())
    feats = pd.DataFrame(index=mo.index)
    feats["доля 65+"] = (a["65+"] / a.total).to_numpy()
    feats["доля 0—14"] = (a["0-14"] / a.total).to_numpy()
    feats["доля 15—34"] = ((a["15-24"] + a["25-34"]) / a.total).to_numpy()
    pop24 = pd.read_parquet(ROOT / "data/external/rosstat/population_mo_2024.parquet") if (ROOT / "data/external/rosstat/population_mo_2024.parquet").exists() else None
    mig = migration()
    if mig is not None:
        m = mig.reindex(key.to_numpy())
        feats["миграция 2023, на 1000"] = (m.migr_2023.to_numpy() / a.total.to_numpy()) * 1000
        feats["внутренняя миграция, на 1000"] = (m.migr_in_2023.to_numpy() / a.total.to_numpy()) * 1000
        feats["международная миграция, на 1000"] = (m.migr_ext_2023.to_numpy() / a.total.to_numpy()) * 1000
    print("признаков:", list(feats.columns), "МО с возрастом:", int(feats["доля 65+"].notna().sum()), "с миграцией:", int(feats["миграция 2023, на 1000"].notna().sum()) if mig is not None else "нет файла")

    P = panel.periods
    i23 = [P.index(f"2023-{m:02d}") for m in range(1, 13)]
    i24 = [P.index(f"2024-{m:02d}") for m in range(1, 13)]
    y23, y24 = panel.y[:, i23].sum(axis=1), panel.y[:, i24].sum(axis=1)
    idx = panel.index.copy()
    idx["g_pc"] = np.log(y24 / y23)
    pop = mo["pop"].reindex(idx.territory_id).to_numpy()
    # рынок: расходы на жителя × население; население одно на оба года, где нет 2024-го
    p24 = pop
    if pop24 is not None and "pop" in pop24.columns and "territory_id" in pop24.columns:
        p24 = pop24.set_index("territory_id")["pop"].reindex(idx.territory_id).fillna(pd.Series(pop, index=idx.territory_id)).to_numpy()
    idx["g_mk"] = np.log((y24 * p24) / (y23 * pop))
    idx["kind"] = np.where(mo.mo_type.reindex(idx.territory_id).isin(URBAN).to_numpy(), "город", "район")
    idx["region"] = mo.region_key.reindex(idx.territory_id).to_numpy()
    F = feats.reindex(idx.territory_id)
    for c in feats.columns:
        idx[c] = F[c].to_numpy()

    rows = []
    for cat in ["Все категории", "Продовольствие", "Здоровье", "Общественное питание"]:
        d0 = idx[idx.category.astype(str) == cat]
        for target, tname in (("g_pc", "расходы на жителя"), ("g_mk", "рынок МО")):
            for level, keys in (("сырой", []), ("внутри субъекта × типа", ["region", "kind"])):
                d = d0.dropna(subset=list(feats.columns) + [target]).copy()
                cols = [target] + list(feats.columns)
                for c in cols:
                    d[c] = d[c] - (d.groupby(keys)[c].transform("mean") if keys else d[c].mean())
                for f in feats.columns:
                    r = stats.linregress(d[f], d[target])
                    sd_f = d[f].std()
                    rows.append({"категория": cat, "цель": tname, "уровень": level, "признак": f, "n": len(d),
                                 "наклон": r.slope, "t": r.slope / r.stderr if r.stderr else np.nan, "R2": r.rvalue ** 2,
                                 "эффект_1σ_пп": r.slope * sd_f * 100})
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "socdem_annual.csv", index=False)
    pd.set_option("display.width", 240)
    pd.set_option("display.max_rows", 200)
    print(res[res.уровень == "внутри субъекта × типа"].round(3).to_string(index=False))
    print("\nсырой срез, «Все категории»:")
    print(res[(res.уровень == "сырой") & (res.категория == "Все категории")].round(3).to_string(index=False))


def joint():
    """Совместная регрессия: возраст и миграция вместе, внутри субъекта × типа, ошибки по кластерам субъектов.
    Молодые переезжают, поэтому доля 15—34 и миграция связаны; здесь видно, что остаётся у каждого."""
    import statsmodels.api as sm
    panel = backtest.load_panel(ROOT / "data/processed")
    mo = pd.read_parquet(ROOT / "data/processed/mo.parquet").set_index("territory_id")
    age = pd.read_parquet(ROOT / "data/external/rosstat/age_mo_2023.parquet")
    age = age[age.total > 0].drop_duplicates("oktmo8").set_index("oktmo8")
    key = mo.oktmo8.astype(str).str.zfill(8)
    a = age.reindex(key.to_numpy()); m = migration().reindex(key.to_numpy())
    F = pd.DataFrame({"old": (a["65+"] / a.total).to_numpy(), "young": ((a["15-24"] + a["25-34"]) / a.total).to_numpy(),
                      "mig": (m.migr_in_2023.to_numpy() / a.total.to_numpy()) * 1000, "mig_ext": (m.migr_ext_2023.to_numpy() / a.total.to_numpy()) * 1000}, index=mo.index)
    P = panel.periods
    y23 = panel.y[:, [P.index(f"2023-{k:02d}") for k in range(1, 13)]].sum(axis=1)
    y24 = panel.y[:, [P.index(f"2024-{k:02d}") for k in range(1, 13)]].sum(axis=1)
    idx = panel.index.copy()
    idx["g"] = np.log(y24 / y23)
    idx["kind"] = np.where(mo.mo_type.reindex(idx.territory_id).isin(URBAN).to_numpy(), "город", "район")
    idx["region"] = mo.region_key.reindex(idx.territory_id).to_numpy()
    for c in F.columns:
        idx[c] = F[c].reindex(idx.territory_id).to_numpy()
    pd.set_option("display.width", 200)
    for cat in ["Все категории", "Продовольствие", "Здоровье"]:
        d = idx[idx.category.astype(str) == cat].dropna(subset=["g", *F.columns]).copy()
        for c in ["g", *F.columns]:
            d[c] = d[c] - d.groupby(["region", "kind"])[c].transform("mean")
        Z = d[list(F.columns)].copy()
        Z = (Z - Z.mean()) / Z.std()                      # в единицах σ: наклон = п. п. роста на 1 σ признака
        r = sm.OLS(d.g.to_numpy() * 100, sm.add_constant(Z.to_numpy())).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(d.region)[0]})
        print(f"\n{cat}: n = {len(d)}, R² = {r.rsquared:.3f} (внутри субъекта × типа); п. п. годового роста на 1 σ признака, ошибки по субъектам")
        print(pd.DataFrame({"признак": ["const", "доля 65+", "доля 15—34", "внутренняя миграция", "международная миграция"], "β": r.params.round(3), "t": r.tvalues.round(2)}).iloc[1:].to_string(index=False))


if __name__ == "__main__":
    joint() if (len(sys.argv) > 1 and sys.argv[1] == "--joint") else main()
