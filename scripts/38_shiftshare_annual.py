"""Шаг 38. Прямая проверка канала «доходы отраслей → расходы МО» на годовых данных.

Месячная поправка (шаги 36—37) не помогла. Самая простая проверка гипотезы
без месячного шума: по каждому МО годовой рост расходов на жителя 2024 к 2023
(«Все категории» и продовольствие) против ожидаемого роста доходов —
Σ доля отрасли в занятости МО × годовой рост ФОТ отрасли по России за 2024.
Если связь есть, наклон положительный и значимый; заодно считается та же
связь для роста ФОТ только добычи и только сельского хозяйства, взвешенного
своей долей, — это и есть «нефтяные» и «аграрные» МО.

    python scripts/38_shiftshare_annual.py
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

OUT = ROOT / "results/forward_check"


def main():
    panel = backtest.load_panel(ROOT / "data/processed")
    shares = pd.read_parquet(ROOT / "data/processed/mo_industry_shares.parquet").set_index("territory_id")
    cols = [c for c in shares.columns if c not in ("source", "workers", "mono", "subject_matched")]
    f = pd.read_parquet(ROOT / "data/external/sberindex/izmenenie-obema-fot.parquet")
    f["year"] = pd.to_datetime(f.period).dt.year + (pd.to_datetime(f.period).dt.month == 12).astype(int) * 0
    f["period"] = (pd.to_datetime(f.period) + pd.Timedelta(days=1)).dt.strftime("%Y-%m")
    f["year"] = f.period.str[:4].astype(int)
    fy = f.groupby(["activity", "year"]).value.sum().unstack(0)
    g24 = np.log(fy.loc[2024] / fy.loc[2023])          # рост ФОТ отрасли за 2024
    g_all = g24["Все отрасли"]
    rel = (g24[cols] - g_all)
    print("рост ФОТ 2024 по отраслям относительно всех, %:", (rel * 100).round(1).sort_values().to_dict())

    P = panel.periods
    i23 = [P.index(f"2023-{m:02d}") for m in range(1, 13)]
    i24 = [P.index(f"2024-{m:02d}") for m in range(1, 13)]
    y23, y24 = panel.y[:, i23].sum(axis=1), panel.y[:, i24].sum(axis=1)
    growth = np.log(y24 / y23)
    idx = panel.index.copy()
    idx["growth"] = growth
    rows = []
    for cat in ["Все категории", "Продовольствие", "Общественное питание", "Здоровье"]:
        d = idx[idx.category.astype(str) == cat].copy()
        sh = shares.reindex(d.territory_id)
        d["exp_income"] = (sh[cols].to_numpy() @ rel.to_numpy())
        d["g"] = d.growth - np.median(d.growth)
        for name, x in (("shift-share, все отрасли", d.exp_income),
                        ("доля добычи × её рост", sh["Добыча полезных ископаемых"].to_numpy() * rel["Добыча полезных ископаемых"]),
                        ("доля сельского хозяйства × его рост", sh["Сельское хозяйство"].to_numpy() * rel["Сельское хозяйство"]),
                        ("доля обработки × её рост", sh["Обрабатывающие производства"].to_numpy() * rel["Обрабатывающие производства"]),
                        ("доля добычи (уровень)", sh["Добыча полезных ископаемых"].to_numpy()),
                        ("доля сельского хозяйства (уровень)", sh["Сельское хозяйство"].to_numpy())):
            x = np.asarray(x, float)
            ok = np.isfinite(x) & np.isfinite(d.g.to_numpy())
            r = stats.linregress(x[ok], d.g.to_numpy()[ok])
            sp = stats.spearmanr(x[ok], d.g.to_numpy()[ok])
            rows.append({"категория": cat, "признак": name, "n": int(ok.sum()), "наклон": r.slope, "se": r.stderr, "t": r.slope / r.stderr,
                         "R2": r.rvalue ** 2, "Спирмен": sp.statistic, "p": sp.pvalue, "размах_признака_п.п.": (np.nanpercentile(x, 95) - np.nanpercentile(x, 5)) * 100})
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "shiftshare_annual.csv", index=False)
    pd.set_option("display.width", 250)
    print(res.round(3).to_string(index=False))


if __name__ == "__main__":
    main()


def within():
    """Та же связь внутри субъекта и внутри типа (город/район): из роста и признака
    вычитаются средние по группе субъект × тип. Если наклон держится, канал
    не сводится к разнице городов и районов."""
    from sbi.models.panel import URBAN
    panel = backtest.load_panel(ROOT / "data/processed")
    mo = pd.read_parquet(ROOT / "data/processed/mo.parquet").set_index("territory_id")
    shares = pd.read_parquet(ROOT / "data/processed/mo_industry_shares.parquet").set_index("territory_id")
    cols = [c for c in shares.columns if c not in ("source", "workers", "mono", "subject_matched")]
    f = pd.read_parquet(ROOT / "data/external/sberindex/izmenenie-obema-fot.parquet")
    f["period"] = (pd.to_datetime(f.period) + pd.Timedelta(days=1)).dt.strftime("%Y-%m")
    f["year"] = f.period.str[:4].astype(int)
    fy = f.groupby(["activity", "year"]).value.sum().unstack(0)
    g24 = np.log(fy.loc[2024] / fy.loc[2023])
    rel = g24[cols] - g24["Все отрасли"]
    P = panel.periods
    y23 = panel.y[:, [P.index(f"2023-{m:02d}") for m in range(1, 13)]].sum(axis=1)
    y24 = panel.y[:, [P.index(f"2024-{m:02d}") for m in range(1, 13)]].sum(axis=1)
    idx = panel.index.copy()
    idx["growth"] = np.log(y24 / y23)
    idx["kind"] = np.where(mo.mo_type.reindex(idx.territory_id).isin(URBAN).to_numpy(), "город", "район")
    idx["region"] = mo.region_key.reindex(idx.territory_id).to_numpy()
    sh = shares.reindex(idx.territory_id)
    idx["x"] = sh[cols].to_numpy() @ rel.to_numpy()
    idx["x_agri"] = sh["Сельское хозяйство"].to_numpy() * rel["Сельское хозяйство"]
    idx["x_manuf"] = sh["Обрабатывающие производства"].to_numpy() * rel["Обрабатывающие производства"]
    idx["x_mining"] = sh["Добыча полезных ископаемых"].to_numpy() * rel["Добыча полезных ископаемых"]
    idx["src"] = sh.source.to_numpy()
    rows = []
    for cat in ["Все категории", "Продовольствие"]:
        d = idx[idx.category.astype(str) == cat].copy()
        for level, keys in (("сырой", []), ("внутри типа", ["kind"]), ("внутри субъекта × типа", ["region", "kind"])):
            dd = d.copy()
            for c in ["growth", "x", "x_agri", "x_manuf", "x_mining"]:
                dd[c] = dd[c] - (dd.groupby(keys)[c].transform("mean") if keys else dd[c].mean())
            for feat in ["x", "x_agri", "x_manuf", "x_mining"]:
                r = stats.linregress(dd[feat], dd.growth)
                rows.append({"категория": cat, "уровень": level, "признак": feat, "наклон": r.slope, "t": r.slope / r.stderr, "R2": r.rvalue ** 2})
            dd2 = dd[dd.src.str.startswith("МО")]
            r = stats.linregress(dd2.x, dd2.growth)
            rows.append({"категория": cat, "уровень": level, "признак": "x, только доли из БД ПМО", "наклон": r.slope, "t": r.slope / r.stderr, "R2": r.rvalue ** 2})
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "shiftshare_annual_within.csv", index=False)
    print(res.round(3).to_string(index=False))


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "--within":
    within()
