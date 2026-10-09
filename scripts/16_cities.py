"""Раскладка Казани и Нижнего Новгорода по районам ценой метра.

Рецепт проверен в 15_price.py: наклон «лог-цена района → лог-уровень расходов»
выучен на Москве и перенесён в Петербург с выигрышем 13—53 % по категориям,
зависящим от дохода. Здесь он применяется к городам, где районов в наборе нет:
итог города — средний уровень 2024 года из набора, цены — realtymag.ru,
октябрь 2026, население — Росстат на 1 января 2023 года
(data/external/irn/cities-raions-2026-10.csv). Категории без выигрыша
при переносе («Продовольствие», «Маркетплейсы») раскладываются равномерно.
Это оценка: проверить её в этих городах нечем.
Екатеринбурга нет: открытой таблицы цен по административным районам не нашлось.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/signal_value"
CITY_MO = {"Казань": "городской округ город Казань", "Нижний Новгород": "городской округ город Нижний Новгород"}
UNIFORM = {"Продовольствие", "Маркетплейсы"}


def main():
    mo = pd.read_parquet(ROOT / "data/processed/mo.parquet")
    panel = pd.read_parquet(ROOT / "data/processed/panel.parquet")
    lvl = panel[panel.period.str.startswith("2024")].groupby(["territory_id", "category"], observed=True).value.mean().unstack()
    msk = mo[mo.region == "Москва"].merge(pd.read_csv(ROOT / "data/external/irn/moskva-2026-08.csv").rename(columns={"name": "name_short"}), on="name_short")
    cities = pd.read_csv(ROOT / "data/external/irn/cities-raions-2026-10.csv")
    rows = []
    for cat in lvl.columns:
        d = msk[msk.territory_id.isin(lvl[cat].dropna().index) & msk["pop"].gt(0)]
        y, w, x = lvl.loc[d.territory_id, cat].to_numpy(float), d["pop"].to_numpy(float), np.log(d.price.to_numpy(float))
        x, t = x - np.average(x, weights=w), np.log(y) - np.log(np.average(y, weights=w))
        slope = 0.0 if cat in UNIFORM else float(np.sum(w * x * t) / np.sum(w * x * x))
        for city, mo_name in CITY_MO.items():
            total = lvl.loc[mo[mo.name == mo_name].territory_id.iloc[0], cat]
            c = cities[cities.city == city]
            xc = np.log(c.price.to_numpy(float))
            xc = xc - np.average(xc, weights=c["pop"])
            rel = np.exp(slope * xc)
            est = rel * total / np.average(rel, weights=c["pop"])
            for r, e, k in zip(c.raion, est, rel / np.average(rel, weights=c["pop"])):
                rows.append({"city": city, "raion": r, "category": cat, "slope": round(slope, 3),
                             "city_level": round(total), "estimate": round(e), "ratio": round(k, 3)})
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "cities_disagg.csv", index=False)
    piv = res[res.category.isin(["Все категории", "Общественное питание"])].pivot_table(index=["city", "raion"], columns="category", values="estimate")
    print(piv.astype(int).to_string())
    print(res.groupby(["city", "category"]).ratio.agg(["min", "max"]).round(2).to_string())


if __name__ == "__main__":
    main()
