"""Москва и Петербург для карты: внутригородские МО — контурами, а где контура нет — точкой.

geo/moscow-districts.geojson — районы Москвы из OpenStreetMap (© OpenStreetMap
contributors, ODbL), та же выгрузка, что у карты «Маршрута дня».
geo/new-moscow.json — центры 19 поселений Новой Москвы: их прежних границ
в OSM нет, после реформы 2024 года там новые районы с другими названиями.
geo/spb-okrugs.geojson — муниципальные округа, города и посёлки Петербурга
(admin_level 8 внутри границы города, выгрузка Geofabrik по Северо-Западу),
контуры упрощены до ~30 м.

Пишет web/public/data/cities.json: territory_id → имя, точка подписи, контур или null.
Запуск из корня: .venv/bin/python web/scripts/cities_geo.py
"""
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
GEO = Path(__file__).parent / "geo"
PREFIX = r"^.*?(муниципальный округ|муниципальное образование|поселение|городской округ|поселок|посёлок|город)\s+"


def key(name: str) -> str:
    text = name.lower().replace("ё", "е")
    text = re.sub(r"\b(район|поселение|городской округ|gpon|округ|муниципальный|поселок|город)\b", " ", text)
    return re.sub(r"[^a-zа-я0-9]", "", text)


def short(name: str) -> str:
    return re.sub(PREFIX, "", name).strip('" ')


# В справочнике у трёх округов Петербурга прежние номера, в OSM — новые имена (old_name в OSM).
RENAMED = {"№ 15": "Суздальское", "№ 72": "Николаевский", "№ 75": "Александровский"}


def place(rows, shapes, centers):
    by_key = {key(f["properties"]["name"]): f for f in shapes}
    out, miss = {}, []
    for r in rows.itertuples():
        name = short(r.name)
        k = key(RENAMED.get(name, name))
        # Сначала точное совпадение: «Сокол» иначе уходит в «Соколиную Гору».
        f = by_key.get(k) or next((v for kk, v in by_key.items() if len(k) >= 5 and (kk.startswith(k) or k.startswith(kk))), None)
        if f:
            p = f["properties"]
            out[int(r.territory_id)] = {"name": name, "lx": p["lx"], "ly": p["ly"], "geometry": f["geometry"]}
        elif k in {key(c) for c in centers}:
            c = next(v for c, v in centers.items() if key(c) == k)
            out[int(r.territory_id)] = {"name": name, "lx": c[0], "ly": c[1], "geometry": None}
        else:
            miss.append(name)
    return out, miss


def main():
    mo = pd.read_parquet(ROOT / "data/processed/mo.parquet")
    msk = [f for f in json.loads((GEO / "moscow-districts.geojson").read_text())["features"] if f["properties"]["kind"] == "district"]
    spb = json.loads((GEO / "spb-okrugs.geojson").read_text())["features"]
    out = {}
    for region, shapes, centers in (("Москва", msk, json.loads((GEO / "new-moscow.json").read_text())), ("Санкт-Петербург", spb, {})):
        got, miss = place(mo[mo.region == region], shapes, centers)
        out.update(got)
        print(f"{region}: {len(got)} мест, контуров {sum(1 for v in got.values() if v['geometry'])}; без места — {miss}")
    dst = ROOT / "web/public/data/cities.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    (ROOT / "web/public/data/moscow.json").unlink(missing_ok=True)
    print(dst, dst.stat().st_size)


if __name__ == "__main__":
    main()
