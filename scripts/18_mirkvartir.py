"""Медианная цена метра по объявлениям МирКвартир — для городов без таблицы цен.

У Екатеринбурга открытой таблицы цен по административным районам нет.
Страница вторичного жилья района на mirkvartir.ru показывает объявления
с ценой за м²; берётся медиана первых двух страниц. Академического района
у сайта нет: он входит в Верх-Исетский. Выборка грубая и зависит
от порядка выдачи, поэтому метод сперва сверяется с таблицей realtymag.ru
по Петербургу и Нижнему Новгороду (у Казани адрес на сайте не подобрался): совпадает порядок районов — метод годится.
Страницы кэшируются в data/external/mirkvartir/.
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from urllib.parse import quote

import numpy as np
import pandas as pd
import requests
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data/external/mirkvartir"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 Chrome/130 Safari/537.36"}
CITIES = {
    "Санкт-Петербург": (None, ["Адмиралтейский", "Василеостровский", "Выборгский", "Калининский", "Кировский", "Колпинский", "Красногвардейский", "Красносельский", "Курортный", "Московский", "Невский", "Петроградский", "Петродворцовый", "Приморский", "Пушкинский", "Фрунзенский"]),
    "Нижний Новгород": ("Нижегородская+область", ["Автозаводский", "Канавинский", "Ленинский", "Московский", "Нижегородский", "Приокский", "Советский", "Сормовский"]),
    "Екатеринбург": ("Свердловская+область", ["Верх-Исетский", "Железнодорожный", "Кировский", "Ленинский", "Октябрьский", "Орджоникидзевский", "Чкаловский"]),
}


def page(region: str, city: str, raion: str, p: int) -> str:
    path = CACHE / f"{city}_{raion}_{p}.html"
    if path.exists():
        return path.read_text()
    head = f"{region}/" if region else ""     # Петербург в адресе без региона
    url = f"https://www.mirkvartir.ru/{head}{quote(city.replace(' ', '+'), safe='+')}/{quote(raion)}/{quote('Вторичное+жилье', safe='+')}/"
    if p > 1:
        url += f"?p={p}"
    r = requests.get(url, headers=UA, timeout=60)
    r.raise_for_status()
    path.write_text(r.text)
    time.sleep(2)
    return r.text


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    rows = []
    for city, (region, raions) in CITIES.items():
        for raion in raions:
            vals = []
            for p in (1, 2):
                t = page(region, city, raion, p)
                vals += [int(x.replace("\xa0", "").replace(" ", "")) for x in re.findall(r"<small>([\d\xa0 ]{5,9})<!-- --> ₽/м²", t)]
            v = np.array([x for x in vals if 30_000 < x < 1_500_000])
            rows.append({"city": city, "raion": raion, "median": int(np.median(v)) if len(v) else None, "n": len(v)})
            print(city, raion, rows[-1]["median"], len(v))
    d = pd.DataFrame(rows)
    d.to_csv(CACHE / "medians-2026-10.csv", index=False)
    ref = pd.concat([pd.read_csv(ROOT / "data/external/irn/cities-raions-2026-10.csv"),
                     pd.read_csv(ROOT / "data/external/irn/spb-realtymag-2026-10.csv").assign(
                         city="Санкт-Петербург", raion=lambda d: d.raion.str.replace(" район", ""))])
    j = d.merge(ref, on=["city", "raion"])
    for c, s in j.groupby("city"):
        print(c, "ранговая связь с realtymag:", round(spearmanr(s["median"], s.price).statistic, 2),
              "лог-корреляция:", round(np.corrcoef(np.log(s["median"]), np.log(s.price))[0, 1], 2))


if __name__ == "__main__":
    main()
