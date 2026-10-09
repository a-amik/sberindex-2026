"""Доли отраслей для сценариев «Что будет, если…» → public/data/industry.json.

Источник — data/processed/mo_industry_shares.parquet (шаг 37: БД ПМО Росстата по МО,
где не нашлось — субъект). Четыре группы: обработка, добыча, сельское хозяйство,
бюджетный сектор (образование, здравоохранение, госуправление). По МО, по субъекту
(взвешено населением) и по стране. Запуск из web/: python scripts/export_industry.py
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parents[1] / "public/data/industry.json"
GROUPS = {"manuf": ["Обрабатывающие производства"], "mining": ["Добыча полезных ископаемых"], "agri": ["Сельское хозяйство"],
          "budget": ["Образование", "Здравоохранение", "Государственное управление и военная безопасность"]}

sh = pd.read_parquet(ROOT / "data/processed/mo_industry_shares.parquet").set_index("territory_id")
mo = json.loads((OUT.parent / "mo.json").read_text())
rows = pd.DataFrame(mo["rows"], columns=mo["cols"])[["id", "rk", "pop"]]
g = pd.DataFrame({k: sh[v].sum(axis=1) for k, v in GROUPS.items()})
rows = rows.join(g, on="id").dropna()
src = sh.source.reindex(rows.id).to_numpy()
w = rows["pop"].clip(lower=1)
reg = rows.groupby("rk").apply(lambda d: pd.Series({k: (d[k] * d["pop"].clip(lower=1)).sum() / d["pop"].clip(lower=1).sum() for k in GROUPS}))
country = {k: float((rows[k] * w).sum() / w.sum()) for k in GROUPS}
out = {"groups": list(GROUPS), "country": [round(country[k], 4) for k in GROUPS],
       "regions": {int(rk): [round(float(r[k]), 4) for k in GROUPS] for rk, r in reg.iterrows()},
       "mo": {int(r.id): [round(float(r[k]), 4) for k in GROUPS] for _, r in rows.iterrows()},
       "moSource": {int(i): ("mo" if str(s).startswith("МО") else "reg") for i, s in zip(rows.id, src)}}
OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
print(OUT, OUT.stat().st_size, "страна:", out["country"], "МО:", len(out["mo"]), "субъектов:", len(out["regions"]))
