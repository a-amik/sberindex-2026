"""Регионы, которые Конституция РФ относит к России, но по которым нет данных СберИндекса:
Республика Крым, Севастополь, ДНР, ЛНР, Запорожская и Херсонская области.

Контуры — Natural Earth, административные единицы 1:10m (data/external/ne/admin1.geojson),
упрощены до ~1 км, кольца по часовой стрелке для d3. На карте — серым, «нет надёжных данных».
Запуск из корня: uv run --with geopandas --with pyogrio python web/scripts/extra_regions.py
"""
import json
from pathlib import Path

import geopandas as gpd
from shapely.geometry import MultiPolygon
from shapely.geometry.polygon import orient

ROOT = Path(__file__).resolve().parents[2]
NAMES = {"Crimea": "Республика Крым", "Sevastopol": "Севастополь", "Donets'k": "Донецкая Народная Республика",
         "Luhans'k": "Луганская Народная Республика", "Zaporizhzhya": "Запорожская область", "Kherson": "Херсонская область"}


def main():
    g = gpd.read_file(ROOT / "data/external/ne/admin1.geojson")
    g = g[g.name.isin(NAMES) & g.admin.isin(["Ukraine", "Russia"])].copy()
    g["geometry"] = g.geometry.simplify(0.01, preserve_topology=True)
    cw = lambda x: orient(x, sign=-1.0) if x.geom_type == "Polygon" else MultiPolygon([orient(p, sign=-1.0) for p in x.geoms])
    rnd = lambda c: [round(c[0], 3), round(c[1], 3)] if isinstance(c[0], float) else [rnd(v) for v in c]
    feats = []
    for r in g.itertuples():
        geo = cw(r.geometry).__geo_interface__
        feats.append({"type": "Feature", "properties": {"name": NAMES[r.name]}, "geometry": {"type": geo["type"], "coordinates": rnd(json.loads(json.dumps(geo["coordinates"])))}})
    dst = ROOT / "web/public/data/extra_regions.json"
    dst.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False, separators=(",", ":")))
    print(dst, len(feats), round(dst.stat().st_size / 1e3), "КБ")


if __name__ == "__main__":
    main()
