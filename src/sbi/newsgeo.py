"""Привязка заголовков к территориям и разметка событий.

География:
* МО — по названию центра (город, посёлок), если такое название в справочнике
  одно на страну, либо по шаблону «<Имя> район / округ»; одноимённые МО
  привязываются, только если в том же заголовке назван их субъект;
* субъект — по прилагательному перед «область», «край», «республика»
  или по прямому имени (Татарстан, Кузбасс, Москва, Петербург…).
Все слова приводятся к начальной форме (pymorphy3): «в Орске» → «орск».

События — правила по начальным формам слов. Тип ставится, если в заголовке
есть хотя бы одно слово-маркер; у заголовка может быть несколько типов.
"""
from __future__ import annotations

import re
from functools import lru_cache

import numpy as np
import pandas as pd
import pymorphy3

from .regions import key as region_key

MORPH = pymorphy3.MorphAnalyzer()

EVENTS = {
    "flood": {"паводок", "наводнение", "подтопление", "подтопить", "затопить", "затопление", "половодье",
              "дамба", "разлив", "паводковый"},
    "fire": {"пожар", "возгорание", "загореться", "сгореть", "пожарище"},
    "emergency": {"чс", "чрезвычайный", "эвакуация", "эвакуировать", "взрыв", "обрушение", "обрушиться",
                  "авария", "ураган", "землетрясение", "смерч", "буря", "непогода", "обесточить", "блэкаут"},
    "attack": {"беспилотник", "бпла", "дрон", "атака", "обстрел", "пво", "ракета"},
    "plant": {"завод", "предприятие", "комбинат", "фабрика", "нпз", "шахта", "рудник"},
    "layoff": {"сокращение", "увольнение", "банкротство", "закрытие", "простой", "задолженность"},
    "payments": {"выплата", "компенсация", "пособие", "материальный"},
    "transport": {"мост", "трасса", "перекрыть", "паром", "переправа", "аэропорт", "рейс"},
    "macro": {"ставка", "ипотека", "тариф", "ндс", "мрот", "пенсия", "инфляция", "цб", "центробанк"},
}

REGION_WORDS = {"область", "край", "республика", "округ", "ао"}
# центры МО из данных, у которых есть знаменитый тёзка вне данных (Ростов-на-Дону — Ростовская
# область в наборе отсутствует): заголовок про тёзку не должен уходить в маленький МО
STOP = {"ростов", "мирный", "советский", "заречный", "октябрьский", "первомайский", "ленинский",
        # города вне набора, чьи имена совпадают с нашими МО: «под Курском» — не станица Курская
        "курск", "курская", "белгород", "брянск", "воронеж", "краснодар", "симферополь", "севастополь",
        "волчанск", "харьков", "донецк", "луганск", "херсон", "мариуполь"}
ENDINGS = ("ами", "ями", "ах", "ях", "ов", "ев", "ом", "ем", "ой", "ей", "ам", "ям", "а", "я", "у", "ю", "е", "ы", "и")
ALIASES = {"татарстан": "татарстан", "башкирия": "башкортостан", "башкортостан": "башкортостан",
           "якутия": "саха", "кузбасс": "кемеровская", "чувашия": "чувашия", "удмуртия": "удмуртская",
           "мордовия": "мордовия", "дагестан": "дагестан", "чечня": "чеченская", "ингушетия": "ингушетия",
           "бурятия": "бурятия", "тыва": "тыва", "хакасия": "хакасия", "карелия": "карелия", "коми": "коми",
           "калмыкия": "калмыкия", "адыгея": "адыгея", "югра": "ханты", "ямал": "ямало", "москва": "москва",
           "петербург": "санкт", "подмосковье": "московская", "приморье": "приморский", "кубань": "краснодарский",
           "забайкалье": "забайкальский", "камчатка": "камчатский", "чукотка": "чукотский", "сахалин": "сахалинская"}


@lru_cache(maxsize=200_000)
def lemma(word: str) -> str:
    return MORPH.parse(word)[0].normal_form


@lru_cache(maxsize=200_000)
def is_geo(word: str) -> bool:
    return any("Geox" in p.tag for p in MORPH.parse(word)[:3])


def stems(word: str) -> list[str]:
    """Основы без падежного окончания: словарь знает не все топонимы («Ишима» → «ишим»)."""
    return [word[: -len(e)] for e in ENDINGS if word.endswith(e) and len(word) - len(e) >= 3]


def tokens(text: str) -> list[tuple[str, str, bool]]:
    """(слово, начальная форма, с заглавной ли) для каждого слова заголовка."""
    out = []
    for w in re.findall(r"[А-Яа-яЁё][А-Яа-яЁё-]*", text):
        out.append((w, lemma(w.lower().replace("ё", "е")), w[0].isupper()))
    return out


def gazetteer(mo: pd.DataFrame, dict_path) -> dict:
    """Названия центров МО и имена субъектов в начальной форме."""
    d = pd.read_excel(dict_path)
    d = d.sort_values(["territory_id", "year_to", "year_from"]).groupby("territory_id").tail(1)
    centers = d.set_index("territory_id").municipal_district_center.reindex(mo.territory_id)
    city, district = {}, {}
    for tid, c, short, rk in zip(mo.territory_id, centers, mo.name_short, mo.region_key):
        if isinstance(c, str):
            name = re.sub(r"^(г|пгт|рп|п|с|ст-ца|аул|д|х|сл|кп|дп)\.?\s+", "", c.strip())
            if len(name) >= 4 and " " not in name:
                city.setdefault(lemma(name.lower().replace("ё", "е")), []).append((tid, rk))
        if isinstance(short, str) and short.endswith(("ский", "цкий", "ной", "ный")):
            district.setdefault(lemma(short.lower().replace("ё", "е")), []).append((tid, rk))
    regions = {}
    for rk in mo.region_key.unique():
        regions[lemma(rk)] = rk
    is_city = dict(zip(mo.territory_id, mo.mo_type.isin(["городской округ"])))
    return {"city": city, "district": district, "regions": regions, "is_city": is_city}


def locate(text: str, gz: dict) -> tuple[set, set]:
    """Субъекты и МО, названные в заголовке."""
    tk = tokens(text)
    regs, mos = set(), set()
    for i, (w, lm, cap) in enumerate(tk):
        nxt = tk[i + 1][1] if i + 1 < len(tk) else ""
        if lm in ALIASES and cap:
            regs.add(ALIASES[lm])
        if lm in gz["regions"] and nxt in REGION_WORDS:
            regs.add(gz["regions"][lm])
    for i, (w, lm, cap) in enumerate(tk):
        nxt = tk[i + 1][1] if i + 1 < len(tk) else ""
        cands = []
        low = w.lower().replace("ё", "е")
        key = lm if lm in gz["city"] else next((x for x in stems(low) if x in gz["city"]), None)
        first_word_ok = i > 0 or is_geo(low)        # «Мирный протест…» в начале — не город Мирный
        # «Курской области» — субъект, а не станица Курская: перед «область, край» город не ищем
        if cap and key and key not in STOP and first_word_ok and nxt not in REGION_WORDS:
            cands = gz["city"][key]
        elif lm in gz["district"] and nxt in {"район", "округ"}:
            cands = gz["district"][lm]
        if len(cands) == 1 and not (lm in gz["regions"] and nxt in REGION_WORDS):
            mos.add(cands[0][0]); regs.add(cands[0][1])
        elif len(cands) > 1:
            pick = [t for t, r in cands if r in regs] or (
                [t for t, _ in cands] if len({r for _, r in cands}) == 1 else [])
            if len(pick) > 1:                  # город — центр и своего округа, и соседнего района
                pick = [t for t in pick if gz["is_city"].get(t)] or pick
            if len(pick) == 1:
                mos.add(pick[0])
                regs.update(r for t, r in cands if t == pick[0])
    return regs, mos


def classify(text: str) -> list[str]:
    lms = {lm for _, lm, _ in tokens(text)}
    out = [k for k, words in EVENTS.items() if lms & words]
    # крупное стихийное событие: паводок или объявленный режим ЧС; эвакуация сама по себе —
    # не признак (эвакуированные из-за рубежа прилетают в Москву)
    if lms & EVENTS["flood"] or ("чс" in lms and "режим" in lms):
        out.append("disaster")
    return out


def annotate(news: pd.DataFrame, gz: dict) -> pd.DataFrame:
    rows = []
    for r in news.itertuples():
        regs, mos = locate(r.title, gz)
        rows.append({"types": classify(r.title), "regions": sorted(regs), "mos": sorted(mos)})
    return pd.concat([news.reset_index(drop=True), pd.DataFrame(rows)], axis=1)


def monthly(ann: pd.DataFrame, mo: pd.DataFrame, lag_days: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Счётчики событий по (МО, месяц) и (субъект, месяц).

    Новость датируется публикацией по МСК: месяц — тот, в котором она вышла.
    Счётчики МО включают и новости, где назван только субъект МО, с весом 1/(число МО субъекта),
    чтобы региональная новость не весила для каждого района как местная.
    """
    a = ann[ann.types.map(len) > 0].copy()
    a["period"] = pd.to_datetime(a.date).dt.strftime("%Y-%m")
    reg_rows, mo_rows = [], []
    n_in_region = mo.groupby("region_key").size()
    for r in a.itertuples():
        for t in r.types:
            for rk in r.regions:
                reg_rows.append((rk, r.period, t, 1.0))
            for tid in r.mos:
                mo_rows.append((tid, r.period, t, 1.0))
    reg = pd.DataFrame(reg_rows, columns=["region_key", "period", "type", "n"])
    mos = pd.DataFrame(mo_rows, columns=["territory_id", "period", "type", "n"])
    reg_m = reg.pivot_table(index=["region_key", "period"], columns="type", values="n", aggfunc="sum", fill_value=0)
    mo_m = mos.pivot_table(index=["territory_id", "period"], columns="type", values="n", aggfunc="sum", fill_value=0)
    return reg_m.reset_index(), mo_m.reset_index()
