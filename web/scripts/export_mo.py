"""Справочник МО для экрана: id, имя, субъект, тип, координаты, население.

Это единственные настоящие данные макета: ряды и модели в нём синтетические.
Запуск из корня репозитория: .venv/bin/python web/scripts/export_mo.py
"""
import json
from pathlib import Path

import pandas as pd

root = Path(__file__).resolve().parents[2]
mo = pd.read_parquet(root / "data/processed/mo.parquet")
mo = mo.dropna(subset=["lat", "lon"])
rows = [
    [int(r.territory_id), r.name_short or r.name, r.region, r.region_key, r.mo_type,
     round(float(r.lat), 3), round(float(r.lon), 3), int(r.pop) if pd.notna(r.pop) else 0,
     round(float(r.urban_share), 2) if pd.notna(r.urban_share) else 0]
    for r in mo.itertuples()
]
out = root / "web/public/data/mo.json"
out.write_text(json.dumps({"cols": ["id", "name", "region", "rkey", "type", "lat", "lon", "pop", "urban"], "rows": rows}, ensure_ascii=False, separators=(",", ":")))
print(out, len(rows))
