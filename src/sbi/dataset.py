"""Сборка данных для моделей.

panel.parquet        МО × категория × месяц: значение, признак полного ряда
mo.parquet           характеристики МО: субъект, тип, статус, координаты,
                     население, доля городского, доступность рынков, моногород
neighbours.parquet   k ближайших МО по автодороге
regions.parquet      МО, свёрнутые в субъект с весом по населению
national.parquet     общероссийские месячные ряды: расходы СберИндекса,
                     ставка, календарь, недельные индексы в месяц
regional.parquet     субъект × месяц: ИПЦ по группам, зарплата, туристы
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .regions import key as region_key

CATEGORIES = ["Все категории", "Продовольствие", "Здоровье", "Общественное питание", "Транспорт", "Маркетплейсы"]


def _period(s: pd.Series) -> pd.Series:
    """Метка периода API — конец месяца в UTC (21:00 последнего дня), переводим в ГГГГ-ММ по МСК."""
    t = pd.to_datetime(s, utc=True) + pd.Timedelta(hours=3)
    return t.dt.strftime("%Y-%m")


def build_panel(raw) -> pd.DataFrame:
    df = pd.read_parquet(raw / "consumption.parquet").rename(columns={"date": "period"})
    df["category"] = pd.Categorical(df.category, CATEGORIES)
    n = df.groupby(["territory_id", "category"], observed=True).period.transform("size")
    df["full"] = n == df.period.nunique()
    return df.sort_values(["territory_id", "category", "period"]).reset_index(drop=True)


def _core(name: str) -> str:
    n = str(name).lower().replace("ё", "е")
    n = re.sub(r"\(.*?\)|городской округ|муниципальный район|муниципальный округ|город |г\.? |"
               r"внутригородская территория|муниципальное образование|поселение", " ", n)
    words = [w for w in re.findall(r"[а-я]+(?:-[а-я]+)?", n) if len(w) > 2]
    return words[0] if words else n.strip()


def build_mo(raw, ext, ids) -> pd.DataFrame:
    d = pd.read_excel(raw / "t_dict_municipal_districts.xlsx")
    # у одного МО в постоянных границах несколько версий ОКТМО: берём последнюю
    d = (d[d.territory_id.isin(ids)].sort_values(["territory_id", "year_to", "year_from"])
         .groupby("territory_id").tail(1))
    mo = pd.DataFrame({
        "territory_id": d.territory_id.astype(int),
        "name": d.municipal_district_name,
        "name_short": d.municipal_district_name_short,
        "oktmo": d.oktmo.astype(str),
        "mo_type": d.municipal_district_type,
        "mo_status": d.municipal_district_status.fillna(""),
        "region_code": d.region_code.astype(int),
        "region": d.region_name,
        "lat": d.municipal_district_center_lat,
        "lon": d.municipal_district_center_lon,
    })
    mo["region_key"] = mo.region.map(region_key)
    mo["oktmo8"] = mo.oktmo.str.replace("-", "").str[:8]

    pop = pd.read_parquet(ext / "rosstat" / "population_mo.parquet")
    by_code = pop.drop_duplicates("oktmo8").set_index("oktmo8")
    mo["pop"] = mo.oktmo8.map(by_code["pop"])
    mo["pop_urban"] = mo.oktmo8.map(by_code["pop_urban"])
    mo["pop_source"] = np.where(mo["pop"].notna(), "oktmo", "")

    # запасной путь: то же ядро названия в том же субъекте, единственное совпадение
    rk, cur = [], None
    for code, name in zip(pop.terson, pop.name):
        if code.endswith("00000000"):
            cur = region_key(name)
        rk.append(cur)
    pop = pop.assign(region_key=rk, core=pop.name.map(_core))
    pop = pop[pop.terson.str[2].isin(list("3567"))]   # 3 — внутригородские, 5/6 — округа и районы, 7 — городские округа
    uniq = pop.groupby(["region_key", "core"]).filter(lambda g: len(g) == 1).set_index(["region_key", "core"])
    miss = mo["pop"].isna()
    keys = list(zip(mo.loc[miss, "region_key"], mo.loc[miss, "name"].map(_core)))
    mo.loc[miss, "pop"] = [uniq["pop"].get(k, np.nan) for k in keys]
    mo.loc[miss, "pop_urban"] = [uniq["pop_urban"].get(k, np.nan) for k in keys]
    mo.loc[miss & mo["pop"].notna(), "pop_source"] = "name"
    mo["urban_share"] = mo.pop_urban / mo["pop"]

    ma = pd.read_parquet(raw / "market_access.parquet")
    mo = mo.merge(ma, on="territory_id", how="left")

    mono = pd.read_parquet(ext / "rosstat" / "monotowns.parquet")
    mono = mono.assign(core=mono.mo_name.map(_core)).drop_duplicates(["region_key", "core"])
    mo = mo.assign(core=mo.name.map(_core)).merge(
        mono[["region_key", "core", "mono_status"]], on=["region_key", "core"], how="left").drop(columns="core")
    mo["mono_status"] = mo.mono_status.fillna("")
    return mo.sort_values("territory_id").reset_index(drop=True)


def build_neighbours(raw, ids, k: int) -> pd.DataFrame:
    c = pd.read_parquet(raw / "connection.parquet")
    c = c[(c.type == "highway") & c.territory_id_x.isin(ids) & c.territory_id_y.isin(ids)
          & (c.territory_id_x != c.territory_id_y)]
    # пары в файле записаны в одну сторону: дополняем обратными
    both = pd.concat([c[["territory_id_x", "territory_id_y", "distance"]],
                      c.rename(columns={"territory_id_x": "territory_id_y", "territory_id_y": "territory_id_x"})
                      [["territory_id_x", "territory_id_y", "distance"]]])
    both = both.drop_duplicates(["territory_id_x", "territory_id_y"]).sort_values(["territory_id_x", "distance"])
    both["rank"] = both.groupby("territory_id_x").cumcount() + 1
    nb = both[both["rank"] <= k].rename(columns={"territory_id_x": "territory_id", "territory_id_y": "neighbour_id"})
    nb["kind"] = "highway"
    return nb.reset_index(drop=True)


def add_geo_neighbours(nb: pd.DataFrame, mo: pd.DataFrame, k: int) -> pd.DataFrame:
    """МО без автодорожной связи (Чукотка, север Якутии и Камчатки) получают
    соседей по расстоянию между центрами по дуге большого круга."""
    lonely = mo[~mo.territory_id.isin(nb.territory_id) & mo.lat.notna()]
    if lonely.empty:
        return nb
    pts = mo.dropna(subset=["lat", "lon"])
    lat, lon = np.radians(pts.lat.to_numpy()), np.radians(pts.lon.to_numpy())
    rows = []
    for r in lonely.itertuples():
        a, b = np.radians(r.lat), np.radians(r.lon)
        d = 6371 * 2 * np.arcsin(np.sqrt(np.sin((lat - a) / 2) ** 2 + np.cos(a) * np.cos(lat) * np.sin((lon - b) / 2) ** 2))
        order = [i for i in np.argsort(d) if pts.territory_id.iloc[i] != r.territory_id][:k]
        rows += [{"territory_id": r.territory_id, "neighbour_id": int(pts.territory_id.iloc[i]),
                  "distance": round(float(d[i]), 1), "rank": n + 1, "kind": "geo"} for n, i in enumerate(order)]
    return pd.concat([nb, pd.DataFrame(rows)], ignore_index=True)


def build_regions(panel: pd.DataFrame, mo: pd.DataFrame) -> pd.DataFrame:
    """Расходы на жителя по субъекту: среднее по МО набора с весом по населению.

    Это не официальный ряд субъекта: в набор входят только МО выше порога
    качества, поэтому рядом пишется доля населения субъекта, которую они покрывают.
    """
    m = panel.merge(mo[["territory_id", "region_key", "region", "pop"]], on="territory_id")
    m = m[m["pop"].notna()]
    m["w"] = m["pop"] * m["value"]
    g = m.groupby(["region_key", "region", "category", "period"], observed=True)
    out = g.agg(w=("w", "sum"), pop=("pop", "sum"), n_mo=("territory_id", "nunique")).reset_index()
    out["value"] = out.w / out["pop"]
    return out.drop(columns="w")


def build_national(ext, cfg) -> pd.DataFrame:
    sb = ext / "sberindex"
    parts = []
    for name, col in (("consumer-spending", "spend_bn"), ("consumper-spending-index-sa", "spend_index_sa"),
                      ("consumer-spending-growth", "spend_yoy")):
        d = pd.read_parquet(sb / f"{name}.parquet")
        d["period"] = _period(d.period)
        if name == "consumer-spending-growth":   # в наборе два ряда на тип: номинальный и реальный
            p = d.pivot_table(index="period", columns=["value_type", "type"], values="value", aggfunc="first")
            p.columns = [f"{col}_{'real' if vt == 'Реальное' else 'nominal'}:{t}" for vt, t in p.columns]
        else:
            p = d.pivot_table(index="period", columns="type", values="value", aggfunc="first")
            p.columns = [f"{col}:{c}" for c in p.columns]
        parts.append(p)
    rate = pd.read_parquet(sb / "real-key-interest-rate.parquet")
    rate["period"] = _period(rate.period)
    names = {"Ключевая ставка в реальном выражении": "real_key_rate", "Ключевая ставка": "key_rate_cmi",
             "Базовая инфляция по трем месяцам": "core_inflation_3m"}
    parts.append(rate.assign(k=rate.key_rate_categories.map(names))
                 .pivot_table(index="period", columns="k", values="value", aggfunc="first"))
    weekly = pd.read_parquet(sb / "ver-izmenenie-trat-po-kategoriyam.parquet")
    weekly["period"] = _period(weekly.period)
    parts.append(weekly.pivot_table(index="period", columns="category", values="value", aggfunc="mean")
                 .add_prefix("weekly_yoy:"))
    shops = pd.read_parquet(sb / "izmenenie-kolichestva-aktivnikh-torgovo-servisnikh-tochek-po-kategoriyam.parquet")
    shops["period"] = _period(shops.period)
    parts.append(shops.pivot_table(index="period", columns="category", values="value", aggfunc="mean")
                 .add_prefix("active_shops:"))
    nat = pd.concat(parts, axis=1)
    nat = nat.join(pd.read_parquet(ext / "key_rate.parquet").set_index("period"))
    nat = nat.join(pd.read_parquet(ext / "calendar.parquet").set_index("period"))
    return nat.sort_index().reset_index().rename(columns={"index": "period"})


def build_regional(ext) -> pd.DataFrame:
    cpi = pd.read_parquet(ext / "rosstat" / "cpi_regions.parquet")
    cpi = cpi[cpi.kind == "region"].drop(columns=["okato", "kind", "region"])
    w = pd.read_parquet(ext / "rosstat" / "wages_regions.parquet")
    w = w.drop_duplicates(["region_key", "period"])[["region_key", "period", "wage"]]
    t = pd.read_parquet(ext / "sberindex" / "kolichestvo-vnutrennikh-turistov.parquet")
    t["period"] = _period(t.period)
    t["region_key"] = t.ref_area.map(region_key)
    t = t.groupby(["region_key", "period"]).value.mean().rename("tourists_yoy").reset_index()
    out = cpi.merge(w, on=["region_key", "period"], how="outer").merge(t, on=["region_key", "period"], how="outer")
    return out.sort_values(["region_key", "period"]).reset_index(drop=True)
