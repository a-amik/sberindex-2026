"""Профиль людей для карточек и таблиц → public/data/people.json.

Три числа на территорию: сальдо внутренней миграции 2023 года на 1 000 жителей (БД ПМО
8112023, scripts/41a), доля 65+ и доля 15—34 на 01.01.2023 (Росстат, age_mo_2023).
По МО, по субъекту (взвешено населением) и по стране. Миграция прошлого года двигает рост
следующего (dev 41, годовой срез): это опережающий индикатор на год, не месячный признак.
Запуск из web/: python scripts/export_people.py
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parents[1] / "public/data/people.json"

mo = json.loads((OUT.parent / "mo.json").read_text())
rows = pd.DataFrame(mo["rows"], columns=mo["cols"])[["id", "rk", "pop"]]
ref = pd.read_parquet(ROOT / "data/processed/mo.parquet")[["territory_id", "oktmo8"]]
rows = rows.merge(ref, left_on="id", right_on="territory_id", how="left")
rows["oktmo8"] = rows.oktmo8.astype(str).str.zfill(8)
age = pd.read_parquet(ROOT / "data/external/rosstat/age_mo_2023.parquet")
age = age[age.total > 0].drop_duplicates("oktmo8").set_index("oktmo8")
mig = pd.read_parquet(ROOT / "data/external/bdmo/migration_2023.parquet").set_index("oktmo")
a = age.reindex(rows.oktmo8); m = mig.reindex(rows.oktmo8)
rows["old"] = (a["65+"] / a.total).to_numpy()
rows["young"] = ((a["15-24"] + a["25-34"]) / a.total).to_numpy()
den = a.total.to_numpy().copy()
import numpy as np
den = np.where(np.isnan(den) | (den <= 0), rows["pop"].to_numpy(dtype=float), den)   # нет возраста — делим на население справочника
rows["mig"] = (m.migr_in_2023.to_numpy() / den * 1000)
rows["mig_abs"] = m.migr_in_2023.to_numpy()
ok = rows.dropna(subset=["old", "young", "mig"], how="all")
w = ok["pop"].clip(lower=1)
def wmean(x, w):
    m = x.notna()
    return None if not m.any() else float((x[m] * w[m]).sum() / w[m].sum())
def agg(d):
    ww = d["pop"].clip(lower=1)
    a = wmean(d.mig, ww); b = wmean(d.old, ww); c = wmean(d.young, ww)
    return [None if a is None else round(a, 2), None if b is None else round(b, 4), None if c is None else round(c, 4)]
out = {"keys": ["mig_in_per1000_2023", "share65", "share15_34"], "country": agg(ok),
       "regions": {int(rk): agg(d) for rk, d in ok.groupby("rk")},
       "mo": {int(r.id): [round(float(r.mig), 2), round(float(r.old), 4), round(float(r.young), 4)] for r in ok.itertuples()}}
import math
def clean(x):
    if isinstance(x, dict): return {k: clean(v) for k, v in x.items()}
    if isinstance(x, list): return [clean(v) for v in x]
    if isinstance(x, float) and not math.isfinite(x): return None
    return x
OUT.write_text(json.dumps(clean(out), ensure_ascii=False, separators=(",", ":"), allow_nan=False))
print(OUT, OUT.stat().st_size, "страна", out["country"], "МО", len(out["mo"]), "субъектов", len(out["regions"]))
