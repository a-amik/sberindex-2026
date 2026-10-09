"""Независимая разметка реальных шоков: режимы чрезвычайной ситуации 2023—2024 годов.

Источник — официальный портал правовой информации (publication.pravo.gov.ru):
региональные акты о введении режима ЧС. Тексты — сканы; их распознаёт
встроенный Vision macOS (ocrmac, вне окружения проекта), результат лежит
в data/external/chs/txt. Разметка ни разу не использует расходы, новости
и телеграм, поэтому независима от детекторов и признаков предсказания.

Событие — акт о введении режима: месяц акта, субъект из названия акта,
МО из текста (шапка с местом подписания отрезана; ни одно МО не названо —
режим на весь субъект), причина по словам-маркерам. Причины, бьющие
по жителям, — паводок, атака, авария ЖКХ, непогода, разлив нефти, обрушение;
лесные пожары и сельское хозяйство расходов жителей почти не касаются
и идут контролем.

Проверка: (1) ведущий детектор — доля рядов МО события с тревогой в окне
[τ, τ+2] против тех же МО в другие месяцы и против остальных МО в те же месяцы;
(2) сдвиг отклонения от фактора за [τ, τ+2] против трёх месяцев до τ;
(3) ранняя тревога за месяц до τ — то, что могло бы предупредить.

    python scripts/39_chs_markup.py
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sbi import backtest, detect, newsgeo  # noqa: E402
from sbi.models import panel as panel_models  # noqa: E402

CHS = ROOT / "data/external/chs"
OUT = ROOT / "results/signal_value"
CAUSES = [  # порядок — приоритет, если маркеров несколько; ищутся в предложении с причиной
    ("атака", r"беспилот|бпла|обстрел|атак|диверс|вторжен|ракетн|террор"),
    ("паводок", r"паводк|подтоплен|половод|наводнен|затоплен|талыми вод|прорыв.{0,20}дамб"),
    ("разлив нефти", r"нефт"),
    ("авария ЖКХ", r"теплоснабж|электроснабж|водоснабж|котельн|электросет|отоплени"),
    ("сельское хозяйство", r"агрометео|заморозк|засух|сельскохозяйствен|агропромышлен|посев|урожа|дерматит|скот|животн|продовольств"),
    ("непогода", r"ураган|ветр|снегопад|циклон|ливн|гололед|метел|шторм|град |метеорологическ|осадк|природн\w* явлен|неблагоприятн\w* явлен"),
    ("обрушение", r"обрушен|взрыв"),
    ("транспорт", r"автомобильн\w* дорог|ограничени\w* движени|мост"),
    ("лесной пожар", r"лес|пожар"),
]
PEOPLE = {"атака", "паводок", "разлив нефти", "авария ЖКХ", "непогода", "обрушение", "транспорт"}


def acts() -> list[dict]:
    a = json.load(open(CHS / "pravo_all.json"))
    return [x for x in a if re.search(r"о введении|об объявлении|о (?:режиме|функционировании)", x["name"].lower())
            and not re.search("отмен|утратившим|изменени", x["name"].lower())]


def markup(mo: pd.DataFrame) -> pd.DataFrame:
    gz = newsgeo.gazetteer(mo, ROOT / "data/raw/hackathon/t_dict_municipal_districts.xlsx")
    # субъект — по основе ключа в названии акта: «Чувашской Республики» → «чуваш»
    stems = {rk: re.sub(r"(ский|ская|цкий|цкая|ия|ая|ий|ой|а)$", "", rk) for rk in mo.region_key.unique()}
    stems.update({"саха": "якут", "тыва": "тыва", "томская": "томск", "омская": "омск", "марий": "марий",
                  "алтай": "республики алтай", "алтайский": "алтайск", "москва": "города москвы"})
    stems = {rk: st for rk, st in stems.items() if len(st) >= 4}
    rows = []
    for x in acts():
        f = CHS / "txt" / f'{x["eoNumber"]}.txt'
        if not f.exists():
            continue
        text = f.read_text()
        low = text.lower()
        start = low.find("о введении")
        body = text[start:] if start >= 0 else text
        head = re.sub(r"\s+", " ", x["complexName"]).lower().replace("ё", "е")
        regs = {rk for rk, st in stems.items() if st in head}
        if not regs:
            continue
        _, mos = newsgeo.locate(x["name"].replace("\n", " ") + " " + body.replace("\n", " "), gz)
        in_reg = mo[mo.region_key.isin(regs)]
        flat = re.sub(r"«[^»]{0,300}»", " ", x["name"] + " " + body).replace("\n", " ")   # без названий законов
        low_flat = flat.lower().replace("ё", "е")
        for tid_, short in zip(in_reg.territory_id, in_reg.name_short.fillna("")):
            st = short.lower().replace("ё", "е")[:-2]
            full = short.lower().replace("ё", "е")
            if " " in full and len(full) >= 8 and full in low_flat:          # «Нижний Тагил»
                mos.add(tid_)
            if len(st) >= 5 and re.search(re.escape(st) + r"\w*(?!\s+(?:област|кра|республ))\s+(?:муниципальн|городск|район|округ)", low_flat):
                mos.add(tid_)
        named = sorted(set(in_reg.territory_id) & mos)
        t = x["name"].lower()
        if re.search(r"в лесах|лесн", t):                  # название акта главнее слов в тексте
            cause = "лесной пожар"
        elif re.search(r"агропромышлен|сельскохозяйствен", t):
            cause = "сельское хозяйство"
        else:
            m_ = re.search(r"в связи с|в результате|вследствие|возникш|по причине", low_flat)
            why = low_flat[m_.start():m_.start() + 400] if m_ else low_flat     # предложение с причиной
            if re.search(r"ландшафт|природн\w* пожар|лесн\w* пожар", why):
                cause = "лесной пожар"
            else:
                cause = next((c for c, rx in CAUSES if re.search(rx, t + " " + why)), "другое")
        rows.append({"eo": x["eoNumber"], "date": x["documentDate"][:10], "period": x["documentDate"][:7],
                     "regions": sorted(regs), "cause": cause, "people": cause in PEOPLE,
                     "scope": "МО" if named else "субъект",
                     "territory_ids": named or sorted(in_reg.territory_id), "title": x["name"].strip()})
    return pd.DataFrame(rows)


def main():
    P = ROOT / "data/processed"
    panel = backtest.load_panel(P, "full")
    mo = pd.read_parquet(P / "mo.parquet")
    saved = OUT / "chs_events.json"   # разметка в репозитории: 76 актов, собраны 39_chs_fetch.py 04.10.2026
    if (CHS / "pravo_all.json").exists() and any((CHS / "txt").glob("*.txt")):
        ev = markup(mo)
        ev.to_json(CHS / "events.json", orient="records", force_ascii=False, indent=1)
        ev.to_json(saved, orient="records", force_ascii=False, indent=1)
    else:
        # Чистый запуск без сканов pravo.gov.ru: оценка идёт по сохранённой разметке,
        # происхождение — в самой записи (eo — номер акта на портале, date — дата акта).
        ev = pd.read_json(saved)
        CHS.mkdir(parents=True, exist_ok=True)
        ev.to_json(CHS / "events.json", orient="records", force_ascii=False, indent=1)
        print(f"сканов актов нет (data/external/chs/) — взята сохранённая разметка {saved.relative_to(ROOT)}: {len(ev)} актов")
    print(f"актов с текстом: {len(ev)}")
    print(ev.groupby(["cause", "scope"]).size().to_string())
    per = panel.periods
    ev = ev[ev.period.isin(per)]
    g = panel_models.groups(panel.index, mo, "type")
    spec = importlib.util.spec_from_file_location("d05", ROOT / "scripts/05_detect.py")
    d05 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(d05)
    nb_rows = d05.neighbours(panel, pd.read_parquet(P / "neighbours.parquet"))
    ch = detect.choice(ROOT / "results/metrics/detect_choice.json")
    d = detect.signal(panel.y, g)
    a = detect.run_online(d, g, nb_rows, ch["lead"]) > ch["thresholds"][ch["lead"]]
    tid = panel.index.territory_id.to_numpy()
    T = len(per)
    res = []
    for people, part in ev.groupby("people"):
        hit = np.zeros((len(tid), T), bool)          # ряды МО события × месяц τ
        for _, e in part.iterrows():
            t = per.index(e.period)
            hit[np.isin(tid, e.territory_ids), t] = True
        rr, tt = np.where(hit)
        ok = (tt >= detect.MIN_HIST + 3) & (tt + 2 < T)
        rr, tt = rr[ok], tt[ok]
        win = lambda r, t: a[r, t:t + 3].any()
        al_ev = np.mean([win(r, t) for r, t in zip(rr, tt)])
        # те же месяцы, ряды без события в субъекте; те же ряды, другие месяцы (на 6+ мес. от события)
        rng = np.random.default_rng(42)
        ctrl_rows = np.where(~hit.any(axis=1))[0]
        al_ctrl_rows = np.mean([win(rng.choice(ctrl_rows), t) for t in tt])
        far = [(r, t2) for r, t in zip(rr, tt) for t2 in [rng.integers(detect.MIN_HIST + 3, T - 2)] if abs(t2 - t) >= 6]
        al_ctrl_time = np.mean([win(r, t) for r, t in far]) if far else np.nan
        early = np.mean([a[r, t - 1] for r, t in zip(rr, tt)])
        early_ctrl = np.mean([a[rng.choice(ctrl_rows), t - 1] for t in tt])
        shift = np.array([abs(d[r, t:t + 3].mean() - d[r, t - 3:t].mean()) for r, t in zip(rr, tt)])
        shift_c = np.array([abs(d[c, t:t + 3].mean() - d[c, t - 3:t].mean()) for t in tt for c in [rng.choice(ctrl_rows)]])
        # бутстрап по событиям: разница «окно события − те же месяцы у других МО»
        evs = []
        for _, e in part.iterrows():
            t = per.index(e.period)
            rows_e = np.where(np.isin(tid, e.territory_ids))[0]
            if t < detect.MIN_HIST + 3 or t + 2 >= T or not len(rows_e):
                continue
            c = rng.choice(ctrl_rows, size=len(rows_e))
            evs.append((np.mean([win(r, t) for r in rows_e]), np.mean([win(r, t) for r in c]), len(rows_e)))
        evs = np.array(evs)
        boot = []
        for _ in range(2000):
            k = rng.integers(0, len(evs), len(evs))
            w = evs[k, 2]
            boot.append(np.average(evs[k, 0], weights=w) - np.average(evs[k, 1], weights=w))
        lo, hi = np.quantile(boot, [0.05, 0.95])
        res.append({"причины": "бьют по жителям" if people else "контроль: лес и сельское хозяйство",
                    "разница, 90 % интервал, п. п.": f"{lo * 100:.1f}…{hi * 100:.1f}",
                    "событий": len(part), "рядов": len(rr),
                    "тревога в [τ, τ+2]": al_ev, "те же месяцы, другие МО": al_ctrl_rows,
                    "те же МО, другие месяцы": al_ctrl_time,
                    "тревога в τ−1": early, "τ−1, другие МО": early_ctrl,
                    "сдвиг отклонения, медиана %": np.median(shift) * 100, "сдвиг у контроля %": np.median(shift_c) * 100})
    tab = pd.DataFrame(res)
    tab.to_csv(OUT / "chs_markup_check.csv", index=False)
    pd.set_option("display.width", 250)
    print(tab.round(3).T.to_string())


if __name__ == "__main__":
    main()
