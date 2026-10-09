"""Контуры всех МО для карты: web/public/data/shapes.json (territory_id → геометрия).

Источник — справочник контуров из данных конкурса СберИндекса
(data/raw/hackathon/t_dict_municipal_districts_poly.gpkg, версии по годам; берётся
действующая — year_to = 9999). Упрощение до ~1 км и координаты до 0,001°: для карты
страны с зумом этого хватает, а файл весит единицы мегабайт, а не 74.
Москва и Петербург на крупном зуме рисуются подробными контурами OSM (cities_geo.py).

Запуск из корня (нужен geopandas): uv run --with geopandas --with pyogrio python web/scripts/mo_shapes.py
"""
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import MultiPolygon
from shapely.geometry.polygon import orient

ROOT = Path(__file__).resolve().parents[2]
TOL = 0.01


def rnd(c):
    return [round(c[0], 3), round(c[1], 3)] if isinstance(c[0], float) else [rnd(x) for x in c]


def main():
    g = gpd.read_file(ROOT / "data/raw/hackathon/t_dict_municipal_districts_poly.gpkg").to_crs(4326)
    g = g[g.year_to == 9999]
    ids = set(pd.read_parquet(ROOT / "data/processed/mo.parquet").territory_id.astype(int))
    g = g[g.territory_id.astype(int).isin(ids)]
    g["geometry"] = g.geometry.simplify(TOL, preserve_topology=True)
    # d3-geo читает внешнее кольцо по часовой стрелке; против — это «всё, кроме полигона».
    cw = lambda x: orient(x, sign=-1.0) if x.geom_type == "Polygon" else MultiPolygon([orient(p, sign=-1.0) for p in x.geoms]) if x.geom_type == "MultiPolygon" else x
    g["geometry"] = g.geometry.apply(cw)
    out = {}
    for r in g.itertuples():
        if r.geometry is None or r.geometry.is_empty:
            continue
        geo = r.geometry.__geo_interface__
        out[int(r.territory_id)] = {"type": geo["type"], "coordinates": rnd(json.loads(json.dumps(geo["coordinates"])))}
    dst = ROOT / "web/public/data/shapes.json"
    dst.write_text(json.dumps(out, separators=(",", ":")))
    print(dst, len(out), round(dst.stat().st_size / 1e6, 1), "МБ")


if __name__ == "__main__":
    main()
