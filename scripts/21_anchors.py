"""Шаг 21. Гипотеза: якорные объекты — АЗС, офисные и торговые центры — стягивают спрос.

Данные — выгрузка OpenStreetMap по России (Geofabrik, data/external/osm/russia-latest.osm.pbf).
Из неё osmium вынимает три вида якорей и все точки сервиса (amenity, shop) для поправки
на то, насколько подробно МО нанесено на карту:
  АЗС              amenity=fuel
  офисный центр    building=office, или office=*/building=commercial с «бизнес-центр», «БЦ», «офис» в имени
  торговый центр   shop=mall
Объект привязывается к МО по контуру (у площадных — центр).

Проверка на прошлом, тот же сигнал и те же поправки, что у жилья (шаг 20):
  1) Срез. Прирост отклонения МО от своей группы за 2024 год к 2023 году против плотности
     якорей на 10 тыс. жителей; поправки — размер МО, доля горожан, сданное в 2023 году жильё,
     подробность карты, всё внутри субъекта.
  2) Новые якоря. Даты открытия в OSM нет. Замена — дата появления на карте: номера
     объектов в OSM растут со временем, и границы 2023 года по номеру снимаются с самих
     данных — по объектам версии 1, у которых время правки и есть время создания.
     Правки этот признак не сбивают. Подробность карты учитывается тем же счётом
     по всем новым точкам сервиса.
Итог — results/metrics/anchors.json.
    uv run --with geopandas --with pyogrio --with pandas --with pyarrow --with statsmodels python scripts/21_anchors.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
O = ROOT / "data/external/osm"
import os
PBF = Path(os.environ.get("OSM_PBF", O / "russia-latest.osm.pbf"))
OFFICE_NAME = re.compile(r"бизнес[- ]?центр|\bбц\b|business ?(center|centre)|офисн", re.I)


def extract():
    """Якоря и точки сервиса — в geojsonseq с версией и временем правки; кэш рядом с выгрузкой."""
    out = O / f"anchors-{PBF.stem.split('.')[0]}.geojsonseq"
    if out.exists() and out.stat().st_mtime > PBF.stat().st_mtime:
        return out
    flt = O / f"anchors-{PBF.stem.split('.')[0]}.osm.pbf"
    subprocess.run(["osmium", "tags-filter", str(PBF), "nwr/amenity", "nwr/shop", "nwr/office", "nwr/building=office,commercial",
                    "-o", str(flt), "--overwrite"], check=True)
    subprocess.run(["osmium", "export", str(flt), "-f", "geojsonseq", "-a", "type,id,version,timestamp", "-o", str(out), "--overwrite"], check=True)
    return out


def load(path):
    rows = []
    with open(path) as f:
        for line in f:
            o = json.loads(line.lstrip("\x1e"))
            p, g = o["properties"], o["geometry"]
            amen, shop, bld, off, name = p.get("amenity"), p.get("shop"), p.get("building"), p.get("office"), p.get("name") or ""
            kind = ("fuel" if amen == "fuel" else "mall" if shop == "mall"
                    else "office" if bld == "office" or ((off or bld == "commercial") and OFFICE_NAME.search(name)) else None)
            poi = bool(amen or shop)
            if not kind and not poi:
                continue
            if g["type"] == "Point":
                lon, lat = g["coordinates"]
            else:                                   # площадь или линия — центр рамки, для привязки к МО хватает
                xs, ys = zip(*_coords(g["coordinates"]))
                lon, lat = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
            rows.append((kind, poi, lon, lat, p.get("@type", "")[:1], int(p.get("@id", 0)), p.get("@version", 0), p.get("@timestamp", ""), name))
    df = pd.DataFrame(rows, columns=["kind", "poi", "lon", "lat", "t", "oid", "ver", "ts", "name"])
    if pd.api.types.is_numeric_dtype(df.ts):              # osmium отдаёт время секундами эпохи
        df["ts"] = pd.to_datetime(df.ts, unit="s").dt.strftime("%Y-%m-%dT%H:%M:%S")
    return df


def born(df):
    """Год появления объекта на карте по номеру: границы годов — медианный номер версий 1,
    созданных в первую неделю года (у них время правки равно времени создания)."""
    out = pd.Series(np.nan, index=df.index)
    for t, gg in df.groupby("t"):
        v1 = gg[gg.ver == 1]
        cuts = {y: v1[v1.ts.str.startswith(f"{y}-01-0")].oid.median() for y in range(2019, 2027)}
        cuts = {y: c for y, c in cuts.items() if np.isfinite(c)}
        print(f"  границы годов, {t}:", {y: int(c) for y, c in cuts.items()})
        yrs = sorted(cuts)
        out[gg.index] = np.searchsorted([cuts[y] for y in yrs], gg.oid.to_numpy(), side="right")
        out[gg.index] = [yrs[int(i) - 1] if i > 0 else yrs[0] - 1 for i in out[gg.index]]
    return out


def _coords(c):
    if isinstance(c[0], (int, float)):
        yield c
    else:
        for x in c:
            yield from _coords(x)


def main():
    from sbi import backtest, detect
    from sbi.models import panel as panel_models
    P = ROOT / "data/processed"
    mo = pd.read_parquet(P / "mo.parquet")
    poly = gpd.read_file(ROOT / "data/raw/hackathon/t_dict_municipal_districts_poly.gpkg").to_crs(4326)
    poly = poly[poly.year_to == 9999][["territory_id", "geometry"]]
    poly["territory_id"] = poly.territory_id.astype(int)

    df = load(extract())
    df["born"] = born(df)
    df["new23"] = df.born == 2023
    g = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat), crs=4326)
    g = gpd.sjoin(g, poly, predicate="within", how="inner").drop(columns="index_right")
    print("Объектов к МО:", len(g), g.kind.value_counts().to_dict())

    cnt = lambda m: g[m].groupby("territory_id").size()
    feats = pd.DataFrame({
        "fuel": cnt(g.kind == "fuel"), "office": cnt(g.kind == "office"), "mall": cnt(g.kind == "mall"),
        "poi": cnt(g.poi), "fuel_new": cnt((g.kind == "fuel") & g.new23), "office_new": cnt((g.kind == "office") & g.new23),
        "mall_new": cnt((g.kind == "mall") & g.new23), "poi_new": cnt(g.poi & g.new23),
    }).fillna(0)

    # Сданное в 2023 году жильё — та же доза, что в шаге 20: якорь не должен забрать себе эффект стройки.
    dom = json.loads((ROOT / "data/external/domrf/done.json").read_text())
    dd = pd.DataFrame([(o.get("longitude"), o.get("latitude"), o.get("objReady100PercDt"), o.get("objSquareLiving") or 0) for o in dom],
                      columns=["lon", "lat", "ready", "area"]).dropna(subset=["lon", "lat"])
    dd = dd[pd.to_datetime(dd.ready, errors="coerce").dt.year == 2023]
    dh = gpd.sjoin(gpd.GeoDataFrame(dd, geometry=gpd.points_from_xy(dd.lon, dd.lat), crs=4326), poly, predicate="within")
    a23 = dh.groupby("territory_id").area.sum()

    bp = backtest.load_panel(P, "full")
    groups = panel_models.groups(bp.index, mo, "type")
    d = detect.signal(bp.y, groups)
    idx = bp.index.assign(row=np.arange(len(bp.index)))
    res = {"objects": {k: int(v) for k, v in g.kind.value_counts().items()}, "poi": int(g.poi.sum()),
           "new23": {k: int(feats[f"{k}_new"].sum()) for k in ("fuel", "office", "mall", "poi")}, "cross": [], "new": []}
    for cat in ("Все категории", "Транспорт", "Общественное питание", "Продовольствие", "Маркетплейсы", "Здоровье"):
        sel = idx[idx.category.astype(str) == cat]
        dv = d[sel.row.to_numpy()]
        x = pd.DataFrame({"tid": sel.territory_id.astype(int).to_numpy(), "delta": (dv[:, 12:].mean(axis=1) - dv[:, :12].mean(axis=1)) * 100})
        x = x.merge(mo[["territory_id", "region_key", "pop", "urban_share"]], left_on="tid", right_on="territory_id")
        x = x.join(feats, on="tid").fillna({c: 0 for c in feats.columns})
        per = lambda c: x[c] / x["pop"] * 1e4
        for k in ("fuel", "office", "mall", "poi"):
            x[f"{k}_d"] = np.log1p(per(k))
            x[f"{k}_nd"] = np.log1p(per(f"{k}_new"))
        x["dose23"] = x.tid.map(a23).fillna(0) / x["pop"]
        x["lpop"] = np.log(x["pop"].clip(lower=500))
        x = x.replace([np.inf, -np.inf], np.nan).dropna(subset=["delta", "lpop", "urban_share"])
        x = x[x.dose23 < x.dose23.quantile(0.995)]
        cl = {"groups": x.region_key.astype("category").cat.codes}
        base = "lpop + urban_share + dose23 + C(region_key)"
        for k in ("fuel", "office", "mall"):
            # срез: плотность якоря при поправке на подробность карты
            m = smf.ols(f"delta ~ {k}_d + poi_d + {base}", data=x).fit(cov_type="cluster", cov_kwds=cl)
            res["cross"].append({"cat": cat, "kind": k, "coef": float(m.params[f"{k}_d"]), "se": float(m.bse[f"{k}_d"]),
                                 "p": float(m.pvalues[f"{k}_d"]), "n": int(m.nobs)})
            # новые якоря 2023 года при поправке на все новые точки и на плотность якоря
            m2 = smf.ols(f"delta ~ {k}_nd + {k}_d + poi_nd + poi_d + {base}", data=x).fit(cov_type="cluster", cov_kwds=cl)
            res["new"].append({"cat": cat, "kind": k, "coef": float(m2.params[f"{k}_nd"]), "se": float(m2.bse[f"{k}_nd"]),
                               "p": float(m2.pvalues[f"{k}_nd"]), "n": int(m2.nobs), "with": int((x[f"{k}_new"] > 0).sum())})
            print(f"{cat:22s} {k:6s} срез {m.params[f'{k}_d']:+.2f}±{m.bse[f'{k}_d']:.2f} p={m.pvalues[f'{k}_d']:.3f}"
                  f"   новые {m2.params[f'{k}_nd']:+.2f}±{m2.bse[f'{k}_nd']:.2f} p={m2.pvalues[f'{k}_nd']:.3f} (МО с новыми: {(x[f'{k}_new'] > 0).sum()})")
        if cat == "Все категории":
            m = smf.ols(f"delta ~ dose23 + lpop + urban_share + C(region_key)", data=x).fit(cov_type="cluster", cov_kwds=cl)
            res["housing_check"] = {"coef": float(m.params.dose23), "se": float(m.bse.dose23), "p": float(m.pvalues.dose23)}
    (ROOT / "results/metrics/anchors.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    (ROOT / "web/public/data/anchors.json").write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
