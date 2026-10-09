"""Цена жилья как признак дохода района: добавляет ли она к OSM.

Расходы в наборе — расходы жителей, поэтому уровень района должен зависеть
от дохода жителей, которого в OSM нет. Открытых цен по районам в 2024 году
не нашлось: открытые ряды СберИндекса по недвижимости разбиты по субъектам.
Есть рейтинг irn.ru — средняя цена кв. м по районам Москвы за август 2026 года
(data/external/irn/, 73 района совпали с внутригородскими территориями по
названию; Петербурга у irn.ru нет). Проверка поэтому только внутри Москвы:
пять случайных частей, раскладка известного итога, база — равномерная.

Запуск: uv run --with geopandas --with pyarrow --with scikit-learn --with scipy python scripts/15_price.py
(признаки OSM берутся из results/signal_value/transfer_features.csv, их пишет 12_transfer.py)
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.model_selection import KFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/signal_value"
spec = importlib.util.spec_from_file_location("t", ROOT / "scripts/12_transfer.py")
T = importlib.util.module_from_spec(spec)
spec.loader.exec_module(T)


def main():
    f = pd.read_csv(OUT / "transfer_features.csv")
    f = f[f.city == "Москва"].reset_index(drop=True)
    mo = pd.read_parquet(ROOT / "data/processed/mo.parquet")[["territory_id", "name_short"]]
    price = pd.read_csv(ROOT / "data/external/irn/moskva-2026-08.csv").rename(columns={"name": "name_short"})
    f = f.merge(mo, on="territory_id").merge(price[["name_short", "price"]], on="name_short")
    panel = pd.read_parquet(ROOT / "data/processed/panel.parquet")
    lvl = panel[panel.period.str.startswith("2024")].groupby(["territory_id", "category"], observed=True).value.mean().unstack()
    Xo = T.design(f)
    sets = {"OSM": Xo, "цена": pd.DataFrame({"log_price": np.log(f.price)}),
            "OSM + цена": Xo.assign(log_price=np.log(f.price))}
    rows = []
    for cat in lvl.columns:
        ok = f.territory_id.isin(lvl[cat].dropna().index).to_numpy()
        y = lvl.loc[f.territory_id[ok], cat].to_numpy(float)
        w = f["pop"][ok].to_numpy(float)
        tgt = T.rel(y, w)
        for name, X in sets.items():
            X = X[ok].reset_index(drop=True)
            pr = np.zeros(len(y))
            for tr, te in KFold(5, shuffle=True, random_state=42).split(X):
                m = make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-2, 3, 30)))
                m.fit(X.iloc[tr], tgt[tr], ridgecv__sample_weight=w[tr])
                pr[te] = m.predict(X.iloc[te])
            rows.append({"category": cat, "features": name, **T.evaluate(y, w, pr)})
        rows.append({"category": cat, "features": "корр. цены и уровня", "spearman": pd.Series(np.log(f.price[ok].to_numpy())).corr(pd.Series(y), method="spearman")})
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "price.csv", index=False)
    pd.set_option("display.width", 200)
    print(res.round(3).to_string(index=False))


if __name__ == "__main__" and __import__("sys").argv[-1] != "spb":
    main()


def transfer_spb():
    """Перенос в Петербург. Цены там есть только по административным районам
    (realtymag.ru, октябрь 2026; строка Центрального района — 124 тыс. руб.
    за самый дорогой центр — явная ошибка источника, район исключён).
    Округ получает цену своего района: привязка — центр полигона округа
    в границе района из OSM (spb_mo_raion.csv; целиком в выгрузке 9 районов).
    Наклон «цена → уровень» учится на Москве по районам irn.ru."""
    mo = pd.read_parquet(ROOT / "data/processed/mo.parquet")
    panel = pd.read_parquet(ROOT / "data/processed/panel.parquet")
    lvl = panel[panel.period.str.startswith("2024")].groupby(["territory_id", "category"], observed=True).value.mean().unstack()
    msk = mo[mo.region == "Москва"].merge(pd.read_csv(ROOT / "data/external/irn/moskva-2026-08.csv").rename(columns={"name": "name_short"}), on="name_short")
    spb = (pd.read_csv(ROOT / "data/external/irn/spb_mo_raion.csv")[["territory_id", "raion"]]
           .merge(pd.read_csv(ROOT / "data/external/irn/spb-realtymag-2026-10.csv"), on="raion")
           .merge(mo[["territory_id", "pop"]], on="territory_id"))
    rows = []
    for cat in lvl.columns:
        def prep(d):
            d = d[d.territory_id.isin(lvl[cat].dropna().index) & d["pop"].gt(0)]
            y = lvl.loc[d.territory_id, cat].to_numpy(float)
            w = d["pop"].to_numpy(float)
            x = np.log(d.price.to_numpy(float))
            return y, w, x - np.average(x, weights=w)
        ym, wm, xm = prep(msk)
        tm = T.rel(ym, wm)
        slope = np.sum(wm * xm * tm) / np.sum(wm * xm * xm)
        ys, ws, xs = prep(spb)
        rows.append({"category": cat, "slope_moscow": slope, **T.evaluate(ys, ws, slope * xs),
                     "raions": spb.raion.nunique()})
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "price_transfer_spb.csv", index=False)
    print(res.round(3).to_string(index=False))


if __name__ == "__main__" and __import__("sys").argv[-1] == "spb":
    transfer_spb()
