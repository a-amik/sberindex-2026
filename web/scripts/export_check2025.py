"""Сверка с фактом 2025—2026 и реальные события → public/data/check2025.json.

Источник — results/forward_check (шаги 33—35): помесячный рост прогноза и двух рядов
России по категориям, три правила фактора, реестр событий и тревоги детектора.
Запуск из web/: python scripts/export_check2025.py
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FC = ROOT / "results/forward_check"
OUT = Path(__file__).resolve().parents[1] / "public/data/check2025.json"

paths = pd.read_csv(FC / "paths.csv")
ens = paths[paths.model == "ансамбль"]
by_cat = {}
for c, g in ens.groupby("category"):
    g = g.sort_values("target")
    by_cat[c] = {"targets": g.target.tolist(), "fc": [round(x * 100, 2) for x in g.forecast],
                 "weekly": [round(x * 100, 2) for x in g.fact_weekly],
                 "monthly": [None if pd.isna(x) else round(x * 100, 2) for x in g.fact_monthly]}
summary = pd.read_csv(FC / "summary.csv")
models = summary[summary.категория == "Все категории"].pivot_table(index="модель", columns="год", values=["MAE_пп", "MAE_пп_мес_ряд"])
num = lambda x: None if pd.isna(x) else round(float(x), 1)
model_rows = [{"model": m, "mae25w": num(models.loc[m, ("MAE_пп", 2025)]), "mae26w": num(models.loc[m, ("MAE_пп", 2026)]),
               "mae25m": num(models.loc[m, ("MAE_пп_мес_ряд", 2025)])} for m in models.index]
rules = pd.read_csv(FC / "factor_rules_2025_summary.csv")
rule_rows = [{"cat": r.категория, "rule": r.правило, "year": int(r.год), "maeM": num(r.MAE_мес), "maeW": num(r.MAE_нед), "biasM": num(r.смещ_мес)} for r in rules.itertuples()]
# Реестр событий собран руками, с источниками; копия в репозитории — configs/events_2025_2026.json.
EV = ROOT / "data/external/events_2025_2026.json"
events = json.load(open(EV if EV.exists() else ROOT / "configs/events_2025_2026.json"))
match = pd.read_csv(FC / "events_match.csv").set_index("событие")
ev_rows = []
for e in events:
    m = match.loc[e["id"]]
    ev_rows.append({"id": e["id"], "type": e["type"], "start": e["start"][:7], "sign": e.get("sign"), "confidence": e.get("confidence"), "note": e.get("note", ""),
                    "source": e.get("source", ""), "first": None if pd.isna(m.первая_тревога) else m.первая_тревога,
                    "delay": None if pd.isna(m.задержка_мес) else int(m.задержка_мес), "caught": bool(m.поймано), "series": None if pd.isna(m.ряд_тревоги) else m.ряд_тревоги})
alarms = pd.read_csv(FC / "alarms_2025.csv")
am = alarms.drop_duplicates(["ряд", "месяц"])
out = {"byCat": by_cat, "models": model_rows, "rules": rule_rows, "events": ev_rows,
       "alarms": {"series": 91, "months": 20, "cells": int(len(am)), "share": round(len(am) / (91 * 20) * 100, 1), "byMonth": am.groupby("месяц").size().to_dict()}}
OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
print(OUT, OUT.stat().st_size, "событий", len(ev_rows), "поймано", sum(r["caught"] for r in ev_rows))
