"""Телеграм-каналы властей и МЧС всех субъектов набора — витрина t.me/s.

Витрина отдаёт по двадцать сообщений на страницу и листается назад параметром
before=<id>. Берём текст, дату и номер сообщения, идём назад до января 2023 года.
Это каналы субъектов и городов пилотных регионов плюс Оренбуржье (паводок 2024),
федеральные МЧС, Социальный фонд и Минтруд. Сырые страницы кэшируются в
data/raw/telegram/<канал>/<before>.html, итог — data/external/telegram_posts.parquet.
"""
from __future__ import annotations

import html
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/telegram"
OUT = ROOT / "data/external/telegram_posts.parquet"
SINCE = "2023-01-01"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 Chrome/130 Safari/537.36"}
CHANNELS = {
    "mos_sobyanin": ("Москва", "мэр"), "deptrans_mos": ("Москва", "транспорт"),
    "a_beglov": ("Санкт-Петербург", "губернатор"), "mchspetersburg": ("Санкт-Петербург", "МЧС"),
    "miduralofficial": ("Свердловская область", "правительство"), "orlov_ekb": ("Свердловская область", "мэр Екатеринбурга"),
    "mchs66": ("Свердловская область", "МЧС"),
    "minnihanov": ("Республика Татарстан", "глава"), "mchstatarstan": ("Республика Татарстан", "МЧС"),
    "glebnikitin_nn": ("Нижегородская область", "губернатор"), "yuriy_shalabaev": ("Нижегородская область", "мэр"),
    "admgornn": ("Нижегородская область", "мэрия"), "mchs52": ("Нижегородская область", "МЧС"),
    "solntsev_official": ("Оренбургская область", "губернатор"), "apparat_gubernatora_orb": ("Оренбургская область", "правительство"),
    "pojarnoe_depo": ("Оренбургская область", "МЧС"),
}
# С 04.10.2026 к ним добавлены каналы глав и региональных МЧС всех 77 субъектов набора —
# configs/telegram_channels.json, найдены по витрине t.me/s и проверены по og:title.
import json as _json
for _h, (_r, _k) in _json.load(open(Path(__file__).resolve().parents[1] / "configs/telegram_channels.json")).items():
    CHANNELS.setdefault(_h, (_r, _k))
# Не вошли: e1_news — около ста постов в день, архив до 2023 года качается часами, а Екатеринбург
# в наборе одна МО и покрыт каналами области; mchs_official, sfr_gov, mintrudrf — федеральные,
# пишут о стране, а не о МО; выплаты СФР ведёт отдельный опыт с анонсами.


def page(ch: str, before: int | None) -> str:
    path = RAW / ch / f"{before or 'last'}.html"
    if path.exists():
        return path.read_text()
    url = f"https://t.me/s/{ch}" + (f"?before={before}" if before else "")
    for attempt in range(4):
        r = requests.get(url, headers=UA, timeout=60)
        if r.ok:
            break
        time.sleep(10 * (attempt + 1))
    r.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(r.text)
    time.sleep(0.2)
    return r.text


def parse(t: str) -> list[dict]:
    out = []
    for block in re.findall(r'<div class="tgme_widget_message_wrap.*?(?=<div class="tgme_widget_message_wrap|$)', t, re.S):
        m = re.search(r'data-post="([^"/]+)/(\d+)"', block)
        d = re.search(r'<time datetime="([^"]+)"', block)
        if not m or not d:
            continue
        txt = re.search(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', block, re.S)
        text = html.unescape(re.sub(r"<br\s*/?>", "\n", re.sub(r"<[^>]+>", " ", txt.group(1)))) if txt else ""
        out.append({"channel": m.group(1), "msg_id": int(m.group(2)), "time": d.group(1), "text": re.sub(r"[ \t]+", " ", text).strip()})
    return out


def collect(ch: str) -> pd.DataFrame:
    rows, before, seen = [], None, set()
    while True:
        posts = parse(page(ch, before))
        posts = [p for p in posts if p["msg_id"] not in seen]
        if not posts:
            break
        seen.update(p["msg_id"] for p in posts)
        rows += posts
        oldest = min(posts, key=lambda p: p["msg_id"])
        if oldest["time"][:10] < SINCE or oldest["msg_id"] <= 1:
            break
        before = oldest["msg_id"]
    d = pd.DataFrame(rows)
    print(ch, len(d), d.time.min()[:10] if len(d) else "", flush=True)
    return d


def safe(ch: str) -> pd.DataFrame:
    try:
        return collect(ch)
    except Exception as e:
        print(ch, "ошибка", type(e).__name__, e, flush=True)
        return pd.DataFrame()


def main():
    frames = []
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(8) as pool:      # восемь каналов разом: витрина отвечает по 5—7 с на страницу
        for ch, d in zip(CHANNELS, pool.map(lambda c: safe(c), CHANNELS)):
            if len(d):
                frames.append(d.assign(region=CHANNELS[ch][0], kind=CHANNELS[ch][1]))
    d = pd.concat(frames, ignore_index=True)
    d["date"] = pd.to_datetime(d.time).dt.tz_convert("Europe/Moscow").dt.strftime("%Y-%m-%d")
    d = d[d.date >= SINCE].drop_duplicates(["channel", "msg_id"])
    d.to_parquet(OUT, index=False)
    print("всего", len(d), d.groupby("channel").size().to_dict())


if __name__ == "__main__":
    main()
