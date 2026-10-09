"""Слои карты: порты, аэропорты, добыча, пункты пропуска, моногорода, приграничье.

Точки — из Wikidata (SPARQL, координаты P625), к МО их привязывает контур
(t_dict_municipal_districts_poly.gpkg). Моногорода — справочник МО (mono_status
по перечню Правительства). Приграничье — МО, контур которых касается сухопутной
границы с соседями (Natural Earth 1:50m, допуск ~10 км): пунктов пропуска
в Wikidata мало, поэтому основной слой — сама граница, а пункты — дополнением.

Пишет web/public/data/layers.json. Запуск из корня:
uv run --with geopandas --with pyogrio --with pandas --with pyarrow --with topojson python web/scripts/layers.py
"""
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, shape

ROOT = Path(__file__).resolve().parents[2]
UA = {"User-Agent": "sberindex-research/0.1", "Accept": "application/sparql-results+json"}

# Слой: класс Wikidata (с подклассами), подпись, пояснение.
WD = {
    "port": ("Q44782", "Порты", "Морские и речные порты"),
    "airport": ("Q1248784", "Аэропорты", "Аэропорты с кодом IATA"),
    "mine": ("Q820477", "Добыча: рудники и шахты", "Действующие и закрытые рудники, шахты, карьеры"),
    "field": ("Q15104915", "Добыча: месторождения", "Месторождения нефти, газа и твёрдых полезных ископаемых"),
    "border_pt": ("Q55599109", "Пункты пропуска", "Пункты пропуска через границу, известные в Wikidata"),
}
EXTRA = {"airport": "?p wdt:P238 ?iata ."}


CACHE = ROOT / "data/external/wikidata"


def sparql(q, key):
    """Ответ кэшируется: Wikidata при сбоях режет до запроса в минуту."""
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{key}.json"
    if f.exists():
        return json.loads(f.read_text())
    url = "https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"query": q})
    for _ in range(6):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180) as r:
                res = json.load(r)["results"]["bindings"]
            f.write_text(json.dumps(res, ensure_ascii=False))
            time.sleep(65)
            return res
        except Exception as e:
            print("  повтор через минуту:", e); time.sleep(70)
    return []


def fetch(cls, key, extra=""):
    q = f"""SELECT DISTINCT ?p ?pLabel ?c WHERE {{
      ?p wdt:P31/wdt:P279* wd:{cls}; wdt:P625 ?c . {extra}
      {{ ?p wdt:P17 wd:Q159 }} UNION {{ ?p wdt:P131+ ?r . ?r wdt:P17 wd:Q159 }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "ru,en". }} }}"""
    out = []
    for b in sparql(q, key):
        lon, lat = map(float, b["c"]["value"].removeprefix("Point(").removesuffix(")").split())
        out.append({"qid": b["p"]["value"].rsplit("/", 1)[-1], "name": b["pLabel"]["value"], "lon": round(lon, 4), "lat": round(lat, 4)})
    return out


def main():
    mo = pd.read_parquet(ROOT / "data/processed/mo.parquet")
    poly = gpd.read_file(ROOT / "data/raw/hackathon/t_dict_municipal_districts_poly.gpkg").to_crs(4326)
    poly = poly[(poly.year_to == 9999) & poly.territory_id.astype(int).isin(set(mo.territory_id.astype(int)))]
    poly["territory_id"] = poly.territory_id.astype(int)
    sidx = poly.sindex
    layers, by_mo = [], {}

    def tag(tid, key):
        by_mo.setdefault(int(tid), [])
        if key not in by_mo[int(tid)]:
            by_mo[int(tid)].append(key)

    for key, (cls, name, note) in WD.items():
        pts = fetch(cls, key, EXTRA.get(key, ""))
        items = []
        for p in pts:
            pt = Point(p["lon"], p["lat"])
            hit = [i for i in sidx.query(pt) if poly.geometry.iloc[i].contains(pt)]
            if not hit:
                # Порт и пункт пропуска стоят у кромки — у воды или границы: берём ближайшую МО в ~15 км.
                near = sidx.nearest(pt, return_distance=True, max_distance=0.15)
                if not len(near[0][1]):
                    continue
                hit = [near[0][1][0]]
            tid = int(poly.territory_id.iloc[hit[0]])
            items.append([p["lon"], p["lat"], p["name"], tid, p["qid"]])
            tag(tid, key)
        layers.append({"key": key, "name": name, "note": note, "source": "Wikidata", "kind": "point", "items": items})
        print(f"{name}: {len(pts)} в Wikidata, {len(items)} внутри МО")

    # Моногорода — по справочнику МО
    mono = mo[mo.mono_status.fillna("").str.len() > 0]
    for r in mono.itertuples():
        tag(r.territory_id, "mono")
    layers.append({"key": "mono", "name": "Моногорода", "note": "Перечень Правительства: риски, сложное, стабильное положение", "source": "Справочник МО",
                   "kind": "area", "items": [[int(r.territory_id), r.mono_status] for r in mono.itertuples()]})
    print("Моногорода:", len(mono))

    # Приграничье — касание сухопутной границы с соседями
    from topojson import Topology  # noqa: F401  (проверка, что пакет есть)
    topo = json.loads((ROOT / "web/node_modules/world-atlas/countries-50m.json").read_text())
    nb = json.loads((ROOT / "web/public/data/neighbours.json").read_text())
    nbg = gpd.GeoSeries([shape(f["geometry"]) for f in nb["features"]], crs=4326).buffer(0).unary_union.buffer(0.1)
    border = poly[poly.intersects(nbg)]
    for t in border.territory_id:
        tag(t, "border")
    layers.append({"key": "border", "name": "Приграничье", "note": "МО у сухопутной границы с соседними странами (допуск ~10 км)", "source": "Natural Earth",
                   "kind": "area", "items": [[int(t), ""] for t in border.territory_id]})
    print("Приграничье:", len(border))
    del topo

    dst = ROOT / "web/public/data/layers.json"
    dst.write_text(json.dumps({"layers": layers, "mo": by_mo}, ensure_ascii=False, separators=(",", ":")))
    print(dst, round(dst.stat().st_size / 1e3), "КБ")


if __name__ == "__main__":
    main()
