"""Перенос внутригородской раскладки: обучение на Москве, проверка на Петербурге.

У Екатеринбурга, Казани и Нижнего Новгорода в данных одна точка на город.
Чтобы разложить такой итог по районам, нужна модель, которая по открытым
признакам района говорит, во сколько раз его расходы на жителя выше или ниже
среднего по городу. Проверить её можно только там, где районы в данных есть:
у Москвы (130 районов с населением; у 16 поселений Новой Москвы населения
в данных Росстата нет) и Петербурга (101).

Постановка как в настоящей задаче: итог города известен, раскладка — нет.
Модель предсказывает лог-отношение района к среднему по городу, прогноз
масштабируется так, чтобы взвешенное по населению среднее совпало с итогом.
База — равномерная раскладка: каждый район равен среднему по городу.

Признаки — объекты OpenStreetMap (выгрузки BBBike, срез сентября 2026 года) в полигоне района на жителя и на км²:
магазины, общепит, аптеки, медицина, офисы, банки, гостиницы, станции,
многоквартирные и частные дома; плюс плотность населения и доступность
рынков из набора конкурса. OSM — текущий срез (историю ни одно зеркало Overpass не отдаёт), цель — уровень 2024 года; структура городских объектов
меняется медленно, но это допущение.

Запуск: uv run --with geopandas --with pyarrow --with scikit-learn --with osmium python scripts/12_transfer.py
"""
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box
from scipy.stats import spearmanr
from sklearn.linear_model import RidgeCV
from sklearn.model_selection import KFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/signal_value"
CACHE = ROOT / "data/external/osm"
PBF = {"Москва": "Moscow", "Санкт-Петербург": "SanktPetersburg"}   # download.bbbike.org/osm/bbbike/<имя>/
CLASSES = {
    "shop": 'nwr["shop"]',
    "grocery": 'nwr["shop"~"^(supermarket|convenience|greengrocer|butcher|bakery|alcohol)$"]',
    "mall": 'nwr["shop"="mall"]',
    "food": 'nwr["amenity"~"^(cafe|restaurant|fast_food|bar|pub)$"]',
    "pharmacy": 'nwr["amenity"="pharmacy"]',
    "medical": 'nwr["amenity"~"^(clinic|doctors|dentist|hospital)$"]',
    "office": 'nwr["office"]',
    "bank": 'nwr["amenity"="bank"]',
    "hotel": 'nwr["tourism"~"^(hotel|hostel|guest_house|apartment)$"]',
    "station": 'nwr["railway"="station"]',
    "school": 'nwr["amenity"~"^(school|kindergarten)$"]',
    "apartments": 'way["building"="apartments"]',
    "houses": 'way["building"~"^(house|detached|semidetached_house)$"]',
}


RULES = {
    "shop": lambda g: "shop" in g,
    "grocery": lambda g: g.get("shop") in {"supermarket", "convenience", "greengrocer", "butcher", "bakery", "alcohol"},
    "mall": lambda g: g.get("shop") == "mall",
    "food": lambda g: g.get("amenity") in {"cafe", "restaurant", "fast_food", "bar", "pub"},
    "pharmacy": lambda g: g.get("amenity") == "pharmacy",
    "medical": lambda g: g.get("amenity") in {"clinic", "doctors", "dentist", "hospital"},
    "office": lambda g: "office" in g,
    "bank": lambda g: g.get("amenity") == "bank",
    "hotel": lambda g: g.get("tourism") in {"hotel", "hostel", "guest_house", "apartment"},
    "station": lambda g: g.get("railway") == "station",
    "school": lambda g: g.get("amenity") in {"school", "kindergarten"},
    "apartments": lambda g: g.get("building") == "apartments",
    "houses": lambda g: g.get("building") in {"house", "detached", "semidetached_house"},
}


def fetch(city: str) -> pd.DataFrame:
    """Объекты выгрузки BBBike: точка и центр контура, класс по тегам."""
    path = CACHE / f"{PBF[city]}.parquet"
    if path.exists():
        return pd.read_parquet(path)
    import osmium

    rows = []

    class H(osmium.SimpleHandler):
        def add(self, tags, lat, lon):
            g = {k: tags.get(k) for k in ("shop", "amenity", "office", "tourism", "railway", "building") if k in tags}
            for cls, rule in RULES.items():
                if g and rule(g):
                    rows.append((cls, lat, lon))

        def node(self, n):
            if n.tags:
                self.add(n.tags, n.location.lat, n.location.lon)

        def way(self, w):
            if w.tags and len(w.nodes):
                try:
                    lat = sum(nd.location.lat for nd in w.nodes) / len(w.nodes)
                    lon = sum(nd.location.lon for nd in w.nodes) / len(w.nodes)
                except osmium.InvalidLocationError:
                    return
                self.add(w.tags, lat, lon)

    H().apply_file(str(CACHE / f"{PBF[city]}.osm.pbf"), locations=True)
    df = pd.DataFrame(rows, columns=["cls", "lat", "lon"])
    df.to_parquet(path)
    return df


def features() -> pd.DataFrame:
    mo = pd.read_parquet(ROOT / "data/processed/mo.parquet")
    poly = gpd.read_file(ROOT / "data/raw/hackathon/t_dict_municipal_districts_poly.gpkg")
    tid = "territory_id"
    poly[tid] = poly[tid].astype(int)
    poly = poly.sort_values([c for c in ("year_to", "year_from") if c in poly.columns]).drop_duplicates(tid, keep="last")
    rows = []
    for city in PBF:
        m = mo[mo.region == city][["territory_id", "pop", "market_access"]]
        p = poly[poly[tid].isin(m.territory_id)][[tid, "geometry"]].rename(columns={tid: "territory_id"})
        allpts = fetch(city)
        # район берётся, только если целиком лежит в рамке выгрузки (у Москвы она без Зеленограда и Новой Москвы)
        frame = box(allpts.lon.min(), allpts.lat.min(), allpts.lon.max(), allpts.lat.max())
        p = p[p.within(frame)].to_crs(32637)
        p["area_km2"] = p.area / 1e6
        f = p.merge(m, on="territory_id")
        for cls in CLASSES:
            pts = allpts[allpts.cls == cls]
            g = gpd.GeoDataFrame(geometry=gpd.points_from_xy(pts.lon, pts.lat), crs=4326).to_crs(32637)
            j = gpd.sjoin(g, p[["territory_id", "geometry"]], predicate="within")
            f[cls] = f.territory_id.map(j.territory_id.value_counts()).fillna(0)
            print(city, cls, len(pts), int(f[cls].sum()))
        f["city"] = city
        rows.append(pd.DataFrame(f.drop(columns="geometry")))
    return pd.concat(rows, ignore_index=True)


def design(f: pd.DataFrame) -> pd.DataFrame:
    X = pd.DataFrame(index=f.index)
    X["log_density"] = np.log(f["pop"] / f.area_km2)
    X["log_market_access"] = np.log(f.market_access)
    for cls in CLASSES:
        X[f"{cls}_per_1k"] = np.log1p(f[cls] / f["pop"] * 1000)
        X[f"{cls}_per_km2"] = np.log1p(f[cls] / f.area_km2)
    return X


def rel(y: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Лог-отношение к взвешенному по населению среднему города."""
    return np.log(y) - np.log(np.average(y, weights=w))


def scale(pred_rel: np.ndarray, y: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Раскладка известного итога города по предсказанным отношениям."""
    lvl = np.exp(pred_rel)
    return lvl * np.average(y, weights=w) / np.average(lvl, weights=w)


def evaluate(y, w, pred_rel):
    pred = scale(pred_rel, y, w)
    uni = np.full_like(y, np.average(y, weights=w))
    return {"MAE": np.abs(pred - y).mean(), "MAE_uniform": np.abs(uni - y).mean(),
            "gain_pct": (1 - np.abs(pred - y).mean() / np.abs(uni - y).mean()) * 100,
            "spearman": spearmanr(pred, y).statistic, "n": len(y)}


def main():
    f = features()
    f = f[f["pop"].notna() & (f["pop"] > 0)].reset_index(drop=True)
    f.to_csv(OUT / "transfer_features.csv", index=False)
    panel = pd.read_parquet(ROOT / "data/processed/panel.parquet")
    lvl = panel[panel.period.str.startswith("2024")].groupby(["territory_id", "category"], observed=True).value.mean().unstack()
    X = design(f)
    rows, coefs = [], {}
    for cat in lvl.columns:
        ok = f.territory_id.isin(lvl[cat].dropna().index)
        d, Xc = f[ok].reset_index(drop=True), X[ok].reset_index(drop=True)
        y = lvl.loc[d.territory_id, cat].to_numpy(float)
        w = d["pop"].to_numpy(float)
        city = d.city.to_numpy()
        target = np.zeros_like(y)
        for c in PBF:
            s = city == c
            target[s] = rel(y[s], w[s])
        for train, test in (("Москва", "Санкт-Петербург"), ("Санкт-Петербург", "Москва")):
            a, b = city == train, city == test
            model = make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-2, 3, 30)))
            model.fit(Xc[a], target[a], ridgecv__sample_weight=w[a])
            rows.append({"category": cat, "train": train, "test": test, **evaluate(y[b], w[b], model.predict(Xc[b]))})
            if cat == "Все категории" and train == "Москва":
                coefs = dict(zip(Xc.columns, model[-1].coef_.round(3)))
        for c in PBF:  # внутри города: пять пространственно случайных частей
            s = np.flatnonzero(city == c)
            pr = np.zeros(len(s))
            for tr, te in KFold(5, shuffle=True, random_state=42).split(s):
                model = make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-2, 3, 30)))
                model.fit(Xc.iloc[s[tr]], target[s[tr]], ridgecv__sample_weight=w[s[tr]])
                pr[te] = model.predict(Xc.iloc[s[te]])
            rows.append({"category": cat, "train": c + " (5 частей)", "test": c, **evaluate(y[s], w[s], pr)})
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "transfer.csv", index=False)
    json.dump(coefs, open(OUT / "transfer_coefs.json", "w"), ensure_ascii=False, indent=1)
    pd.set_option("display.width", 200)
    print(res.round(3).to_string(index=False))
    print(sorted(coefs.items(), key=lambda kv: -abs(kv[1]))[:10])


if __name__ == "__main__":
    main()
