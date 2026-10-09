"""Ключевая ставка Банка России, производственный календарь, погода по центрам МО."""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from io import StringIO

import pandas as pd

from .. import net


def key_rate(cfg) -> pd.DataFrame:
    """Ставка по дням с сайта ЦБ, свёрнутая в среднюю за месяц и значение на конец месяца."""
    url = (cfg["sources"]["key_rate"] + "?UniDbQuery.Posted=True"
           "&UniDbQuery.From=01.01.2018&UniDbQuery.To=31.12.2026")
    html = net.fetch(net.session(), url).text
    tab = pd.read_html(StringIO(html), decimal=",", thousands=" ")[0]
    tab.columns = ["date", "rate"]
    tab["date"] = pd.to_datetime(tab["date"], dayfirst=True)
    tab["rate"] = pd.to_numeric(tab["rate"].astype(str).str.replace(",", "."), errors="coerce")
    tab = tab.sort_values("date")
    tab["period"] = tab.date.dt.strftime("%Y-%m")
    return tab.groupby("period").agg(key_rate_mean=("rate", "mean"), key_rate_end=("rate", "last")).reset_index()


def work_calendar(cfg) -> pd.DataFrame:
    """isdayoff.ru: строка из 0/1 по дням года (1 — выходной или праздник)."""
    s = net.session()
    rows = []
    for year in cfg["calendar_years"]:
        flags = net.fetch(s, f"{cfg['sources']['calendar']}?year={year}").text.strip()
        days = pd.date_range(f"{year}-01-01", periods=len(flags), freq="D")
        df = pd.DataFrame({"date": days, "off": [int(c) for c in flags]})
        df["period"] = df.date.dt.strftime("%Y-%m")
        df["weekend"] = df.date.dt.weekday >= 5
        g = df.groupby("period")
        rows.append(pd.DataFrame({
            "days": g.size(),
            "workdays": g.off.apply(lambda x: int((x == 0).sum())),
            "holidays": (df.assign(h=(df.off == 1) & ~df.weekend).groupby("period").h.sum()),
            "weekends": g.weekend.sum(),
        }).reset_index())
    return pd.concat(rows, ignore_index=True)


def _cell(lat: float, lon: float) -> tuple[float, float]:
    """Клетка сетки MERRA-2, на которой считает NASA POWER: 0,5° по широте, 0,625° по долготе."""
    return round(round(lat / 0.5) * 0.5, 3), round(round(lon / 0.625) * 0.625, 3)


def _parse(text: str) -> dict:
    out = {}
    for name, series in json.loads(text)["properties"]["parameter"].items():
        for k, v in series.items():
            if re.fullmatch(r"\d{6}", k) and not k.endswith("13"):   # 13 — среднее за год
                out[(f"{k[:4]}-{k[4:]}", name)] = None if v == -999 else v
    return out


def weather(cfg, points: pd.DataFrame) -> pd.DataFrame:
    """NASA POWER, месячные значения в клетке сетки, где стоит центр МО.

    Соседние МО часто попадают в одну клетку, поэтому кэш ведётся по клеткам:
    1 943 МО с координатами — 1 341 клетка. Сервис ограничивает число запросов
    с адреса; пропущенные клетки добирает повторный запуск.
    """
    w = cfg["weather"]
    cache = cfg.path("raw") / "weather"
    cache.mkdir(parents=True, exist_ok=True)
    s = net.session()
    y0, y1 = w["years"]
    points = points.assign(cell=[_cell(a, b) for a, b in zip(points.lat, points.lon)])

    # прежний кэш по МО превращаем в кэш по клеткам
    for r in points.itertuples():
        old, new = cache / f"{int(r.territory_id)}.json", cache / f"cell_{r.cell[0]}_{r.cell[1]}.json"
        if old.exists() and not new.exists():
            old.rename(new)

    def one(cell):
        f = cache / f"cell_{cell[0]}_{cell[1]}.json"
        if not f.exists():
            url = (f"{cfg['sources']['weather']}?parameters={','.join(w['parameters'])}&community=AG"
                   f"&longitude={cell[1]}&latitude={cell[0]}&start={y0}&end={y1}&format=JSON")
            try:
                f.write_text(net.fetch(s, url, timeout=120, tries=3).text)
            except Exception:   # клетку пропускаем: повторный запуск доберёт её из сети
                return cell, {}
        return cell, _parse(f.read_text())

    cells = sorted(set(points.cell))
    with ThreadPoolExecutor(w["workers"]) as ex:
        got = dict(ex.map(one, cells))
    rows = [{"territory_id": int(r.territory_id), "period": p, "param": k, "value": v}
            for r in points.itertuples() for (p, k), v in got.get(r.cell, {}).items()]
    df = pd.DataFrame(rows)
    done = sum(1 for c in cells if got.get(c))
    print(f"  погода: клеток {done} из {len(cells)}; недостающие доберёт повторный запуск")
    if df.empty:
        return df
    return df.pivot_table(index=["territory_id", "period"], columns="param", values="value").reset_index()


def download(cfg) -> None:
    out = cfg.path("external")
    out.mkdir(parents=True, exist_ok=True)
    key_rate(cfg).to_parquet(out / "key_rate.parquet", index=False)
    print("  ставка ЦБ")
    work_calendar(cfg).to_parquet(out / "calendar.parquet", index=False)
    print("  календарь")


def download_weather(cfg) -> None:
    raw = cfg.path("raw") / "hackathon"
    d = pd.read_excel(raw / "t_dict_municipal_districts.xlsx")
    ids = pd.read_parquet(raw / "consumption.parquet", columns=["territory_id"]).territory_id.unique()
    pts = (d[d.territory_id.isin(ids)]
           .rename(columns={"municipal_district_center_lat": "lat", "municipal_district_center_lon": "lon"})
           [["territory_id", "lat", "lon"]].dropna())
    df = weather(cfg, pts)
    df.to_parquet(cfg.path("external") / "weather.parquet", index=False)
    print(f"  погода: {df.territory_id.nunique()} МО")
