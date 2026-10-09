"""Заголовки федеральных лент из дневных архивов.

Берутся только метаданные: время публикации, заголовок, рубрика, адрес.
Тексты статей не скачиваются. Архивы обходятся страницами дня, которые
robots.txt обеих лент разрешает; между запросами — пауза.

    Интерфакс  https://www.interfax.ru/news/ГГГГ/ММ/ДД[/page_N]
    Лента      https://lenta.ru/rubrics/{russia,economics}/ГГГГ/ММ/ДД/[page/N/]
"""
from __future__ import annotations

import html
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import pandas as pd

from .. import net

IFX_ITEM = re.compile(r'<div data-id="(\d+)">\s*<span>(\d{2}:\d{2})</span>\s*<a href="([^"]+)">\s*<h3>(.*?)</h3>', re.S)
LENTA_ITEM = re.compile(r'<a class="card-full-news[^"]*" href="(/news/[^"]+)"><h3 class="card-full-news__title">(.*?)</h3>'
                        r'.*?card-full-news__date">(\d{2}:\d{2})[^<]*</time>(?:<span[^>]*rubric">([^<]*)</span>)?', re.S)


def _day(source: str, d: date, s, pause: float, rubrics=("russia", "economics")) -> list[dict]:
    if source == "lenta":                    # у Ленты местные события — в рубриках «Россия» и «Экономика»
        out = []
        for rub in rubrics:
            out += _pages(source, d, s, pause, f"https://lenta.ru/rubrics/{rub}/{d:%Y/%m/%d}/")
    else:
        out = _pages(source, d, s, pause, f"https://www.interfax.ru/news/{d:%Y/%m/%d}")
    for x in out:
        x["title"] = html.unescape(re.sub(r"<[^>]+>", "", x["title"])).strip()
        x["date"] = d.isoformat()
        x["source"] = source
    return out


def _pages(source: str, d: date, s, pause: float, base: str) -> list[dict]:
    out, seen = [], set()
    for page in range(1, 40):
        if source == "interfax":
            url = base + (f"/page_{page}" if page > 1 else "")
        else:
            url = base + (f"page/{page}/" if page > 1 else "")
        try:
            r = s.get(url, timeout=60)
        except Exception:
            try:
                r = s.get(url, timeout=60)           # один повтор на сетевой сбой
            except Exception:
                break
        if r.status_code != 200:                     # страница за последней — конец дня, без повторов
            break
        text = r.text
        time.sleep(pause)
        if source == "interfax":
            items = [{"id": i, "time": t, "url": "https://www.interfax.ru" + u, "title": h, "rubric": u.split("/")[1]}
                     for i, t, u, h in IFX_ITEM.findall(text)]
        else:
            # страницы дня у Ленты захватывают соседние дни: берём только свой
            items = [{"id": u, "time": t, "url": "https://lenta.ru" + u, "title": h, "rubric": r}
                     for u, h, t, r in LENTA_ITEM.findall(text) if u.startswith(f"/news/{d:%Y/%m/%d}/")]
        new = [x for x in items if x["id"] not in seen]
        if not new:
            break
        seen.update(x["id"] for x in new)
        out += new
    return out


def collect(cfg) -> pd.DataFrame:
    nc = cfg["news"]
    cache = cfg.path("raw") / "news"
    cache.mkdir(parents=True, exist_ok=True)
    as_date = lambda v: v if isinstance(v, date) else date.fromisoformat(str(v))   # YAML сам читает даты
    d0, d1 = as_date(nc["start"]), as_date(nc["end"])
    days = [d0 + timedelta(i) for i in range((d1 - d0).days + 1)]

    def run(job):
        source, d = job
        f = cache / f"{source}_{d.isoformat()}.json"
        if not f.exists():
            f.write_text(json.dumps(_day(source, d, net.session(), nc["pause"]), ensure_ascii=False))

    jobs = [(src, d) for d in days for src in nc["sources"]]
    with ThreadPoolExecutor(nc["workers_per_source"] * len(nc["sources"])) as ex:
        list(ex.map(run, jobs))
    rows = [r for f in sorted(cache.glob("*.json")) for r in json.loads(f.read_text())]
    df = pd.DataFrame(rows).drop_duplicates(["source", "id"])
    df.to_parquet(cfg.path("external") / "news_headlines.parquet", index=False)
    print(f"  заголовков: {len(df):,} ({df.groupby('source').size().to_dict()})")
    return df


def download(cfg) -> None:
    collect(cfg)
