"""Шаг 35. Детектор на реальных рядах 2025—2026 годов: Россия и отрасли.

Панели МО за 2025 год нет, поэтому раннее обнаружение проверяется на том,
что есть после конца панели: месячные расходы России по пяти категориям,
месячные средние недельного прироста по 46 категориям, ФОТ и обороты
бизнеса по 20 отраслям (СберИндекс). Это ряды одной территории, группы
для фактора нет, поэтому сигнал — годовой прирост в логарифмах, а разлом —
его сдвиг против собственной истории.

Два онлайн-детектора, тревога в месяце t только по данным до t:

* робастный z-балл приращения годового прироста к медиане и MAD за
  последние 12 месяцев, порог 3;
* односторонний CUSUM по тому же приращению с порогом 4 MAD и дрейфом 0,5.

Тревоги 2025-01…2026-08 сводятся с реестром событий
(data/external/events_2025_2026.json): событие считается пойманным, если
тревога по подходящему ряду пришла не позже чем через два месяца после
начала; задержка — месяцы от начала до первой тревоги.

    python scripts/35_detect_2025.py

Выход — results/forward_check/alarms_2025.csv, events_match.csv.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/forward_check"
EXT = ROOT / "data/external"
FROM, TO = "2025-01", "2026-08"


def monthly(df, key, lag_days=1):
    d = df.copy()
    d["period"] = (pd.to_datetime(d.period) + pd.Timedelta(days=lag_days)).dt.strftime("%Y-%m")
    return d.groupby([key, "period"]).value.mean().unstack(0)


def series_bank() -> dict[str, pd.Series]:
    nat = pd.read_parquet(ROOT / "data/processed/national.parquet").set_index("period")
    bank = {}
    for c in ["Всего", "Продовольственные товары", "Непродовольственные товары", "Общественное питание", "Услуги"]:
        s = np.log(nat[f"spend_bn:{c}"].dropna())
        bank[f"расходы РФ · {c}"] = (s - s.shift(12)).dropna()
    for c in [x for x in nat.columns if x.startswith("weekly_yoy:")]:
        bank[f"недельный · {c.split(':', 1)[1].strip()}"] = np.log1p(nat[c].dropna() / 100)
    for f, label in [("izmenenie-obema-fot.parquet", "ФОТ"), ("oboroty-biznesa.parquet", "обороты")]:
        d = pd.read_parquet(EXT / "sberindex" / f)
        d = d[d.freq.str.lower().str.startswith("мес")] if "freq" in d and d.freq.nunique() > 1 else d
        m = monthly(d, "activity")
        for a in m.columns:
            s = m[a].dropna()
            bank[f"{label} · {a}"] = np.log1p(s / 100) if s.abs().max() < 200 else (np.log(s) - np.log(s).shift(12)).dropna()
    return bank


def alarms(y: pd.Series, name: str) -> list[dict]:
    x = y.diff().dropna()
    out = []
    cus_pos = cus_neg = 0.0
    for i in range(12, len(x)):
        hist = x.iloc[i - 12:i]
        med, mad = hist.median(), (hist - hist.median()).abs().median() * 1.4826 + 1e-6
        z = (x.iloc[i] - med) / mad
        cus_pos = max(0.0, cus_pos + z - 0.5)
        cus_neg = max(0.0, cus_neg - z - 0.5)
        p = x.index[i]
        if abs(z) >= 3:
            out.append({"ряд": name, "месяц": p, "детектор": "z", "знак": int(np.sign(z)), "балл": round(float(z), 2), "прирост_гг": round(float(y.loc[p]) * 100, 1)})
        if cus_pos >= 4 or cus_neg >= 4:
            out.append({"ряд": name, "месяц": p, "детектор": "cusum", "знак": 1 if cus_pos >= 4 else -1, "балл": round(float(max(cus_pos, cus_neg)), 2), "прирост_гг": round(float(y.loc[p]) * 100, 1)})
            cus_pos = cus_neg = 0.0
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    bank = series_bank()
    rows = []
    for name, y in bank.items():
        rows += alarms(y, name)
    a = pd.DataFrame(rows)
    a = a[(a.месяц >= FROM) & (a.месяц <= TO)].sort_values(["месяц", "ряд"])
    a.to_csv(OUT / "alarms_2025.csv", index=False)
    pd.set_option("display.width", 240)
    pd.set_option("display.max_rows", 400)
    print(f"Рядов: {len(bank)}, тревог {FROM}…{TO}: {len(a)}")
    print(a.to_string(index=False))

    ev_path = EXT / "events_2025_2026.json"
    if not ev_path.exists():   # реестр собран руками; копия в репозитории
        ev_path = Path(__file__).resolve().parents[1] / "configs/events_2025_2026.json"
    if ev_path.exists():
        events = json.load(open(ev_path))
        match = []
        for e in events:
            start = e["start"][:7]
            pats = e.get("series", [])
            hit = a[a.ряд.str.contains("|".join(pats), regex=True)] if pats else a
            hit = hit[(hit.месяц >= start)]
            first = hit.месяц.min() if len(hit) else None
            delay = None if first is None else (int(first[:4]) - int(start[:4])) * 12 + int(first[5:]) - int(start[5:])
            pre = a[a.ряд.str.contains("|".join(pats), regex=True)] if pats else a
            pre = pre[(pre.месяц < start) & (pre.месяц >= pd.Period(start, "M").__sub__(2).strftime("%Y-%m"))]
            match.append({"событие": e["id"], "начало": start, "ряды": ", ".join(pats) or "все", "первая_тревога": first,
                          "задержка_мес": delay, "поймано": delay is not None and delay <= 2, "тревога_до_начала": len(pre) > 0,
                          "ряд_тревоги": hit.sort_values("месяц").ряд.iloc[0] if len(hit) else None})
        m = pd.DataFrame(match)
        m.to_csv(OUT / "events_match.csv", index=False)
        print("\nСобытия и тревоги:")
        print(m.to_string(index=False))


if __name__ == "__main__":
    main()
