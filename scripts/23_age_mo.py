"""Возрастная структура МО из базы показателей муниципальных образований Росстата.

Показатель 8112014 «Численность всего населения по полу и возрасту на 1 января»,
оба пола, 2023 год — население, известное до окна проверки. Группы собраны
под индекс потребительской активности СберИндекса по возрастам: 0—14, 15—24,
25—34, 35—64, 65+. Запрашиваются все возрастные опции: подписи в формах
субъектов расходятся, и группы суммируются по одиночным годам, а где их нет —
по пятилеткам.

База отдаёт таблицу только формой: строка запроса Qry собирается из кодов
выбранных опций (массивы p_<признак> на странице показателя), раскладка —
QryGm. ОКТМО строки берётся по имени МО из того же массива. Сырые ответы
кэшируются в data/raw/pmo/, итог — data/external/rosstat/age_mo_2023.parquet.
"""
from __future__ import annotations

import html
import re
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sbi import net  # noqa: E402

RAW = ROOT / "data/raw/pmo"
OUT = ROOT / "data/external/rosstat/age_mo_2023.parquet"
YEAR = "2023"
AGES = {"0-14": (0, 14), "15-24": (15, 24), "25-34": (25, 34), "35-64": (35, 64), "65+": (65, None)}


def norm(x: str) -> str:
    return re.sub(r"\s+", " ", x).strip()


def region_codes(s) -> list[str]:
    t = s.get("https://rosstat.gov.ru/storage/mediabank/munst.htm", timeout=60).content.decode("utf-8", "ignore")
    return sorted(set(re.findall(r"munst(\d{2})", t)))


def label(x: str) -> str:
    """Подписи возрастов в формах субъектов расходятся («65- 69», «с тарше 65»): без пробелов они совпадают."""
    return re.sub(r"\s+", "", x)


def group_sum(row: dict, lo: int, hi: int | None) -> float | None:
    """Сумма возрастов lo…hi (hi=None — и старше): по одиночным годам, иначе по пятилеткам."""
    top = 69 if hi is None else hi
    singles = [row.get(str(a)) for a in range(lo, top + 1)]
    tail = row.get("70истарше") if hi is None else 0.0
    if all(v is not None for v in singles) and tail is not None:
        return sum(singles) + tail
    fives = [row.get(f"{a}-{a + 4}") for a in range(lo, top + 1, 5)]
    if all(v is not None for v in fives) and tail is not None:
        return sum(fives) + tail
    return None


def fetch(s, reg: str) -> pd.DataFrame:
    base = f"https://rosstat.gov.ru/dbscripts/munst/munst{reg}/DBInet.cgi"
    cache = RAW / f"{reg}_{YEAR}_all.html"
    form = s.get(base + "?pl=8112014", timeout=120).content.decode("cp1251", "ignore")

    def arr(name):
        return [v for _, v in sorted((int(i), v) for i, v in re.findall(r'p_%s\[(\d+)\]="([^"]*)"' % name, form))]

    def opts(name):
        m = re.search(r'<SELECT\s+NAME="%s".*?</SELECT>' % name, form, re.S | re.I)
        return [html.unescape(x.strip()) for x in re.findall(r"<OPTION[^>]*>([^<\n]*)", m.group(0))] if m else []

    vozr = arr("vozr")
    if not arr("oktmo") or not vozr or YEAR not in arr("god"):
        return pd.DataFrame()
    oktmo = dict(zip(map(norm, opts("oktmo")), arr("oktmo")))
    if not cache.exists():
        qry = (f"Pokazateli:8112014;munr:{','.join(arr('munr'))};tippos:{','.join(arr('tippos'))};"
               f"oktmo:{','.join(arr('oktmo'))};vozr:{','.join(vozr)};grup_2:{arr('grup_2')[0]};"
               f"god:{YEAR};period:{arr('period')[0]};")
        gm = "Pokazateli_z:1;grup_2_z:2;god_z:3;period_z:4;vozr_s:1;munr_b:1;tippos_b:2;oktmo_b:3;"
        r = s.post(base, data={"Qry": qry, "QryGm": gm, "QryFootNotes": ";", "YearsList": ";".join(arr("god")) + ";",
                                "tbl": "Показать таблицу"}, timeout=900)
        cache.write_text(r.content.decode("cp1251", "ignore"))
        time.sleep(1)
    t = cache.read_text()
    trs = [[html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
           for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S | re.I)]
    # шапка — строка с подписями возрастов: в ней есть «Всего» и нет чисел-значений; пустые ячейки слева отбрасываются
    head = next((r for r in trs if len(r) > 5 and "Всего" in map(label, r)
                 and not any(re.fullmatch(r"\d{3,}( \d{3})*", c) for c in r)), None)
    if head is None:
        return pd.DataFrame()
    cols = [label(c) for c in head[[label(c) for c in head].index("Всего"):]]
    rows = []
    for cells in trs:
        name = norm(cells[0]) if cells else ""
        if len(cells) == 1 + len(cols) and name in oktmo:
            vals = {c: (float(v.replace(" ", "").replace(",", ".")) if re.fullmatch(r"[\d ]+([.,]\d+)?", v) else None)
                    for c, v in zip(cols, cells[1:])}
            rec = {"region_code": reg, "name": name, "oktmo8": oktmo[name].zfill(8), "total": vals.get("Всего")}
            for g, (lo, hi) in AGES.items():
                rec[g] = group_sum(vals, lo, hi)
            rows.append(rec)
    return pd.DataFrame(rows)


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    s = net.session()
    frames, empty = [], 0
    for reg in region_codes(s):
        try:
            d = fetch(s, reg)
        except Exception as e:  # база иногда отвечает ошибкой шлюза — субъект пропускается и виден в логе
            print(reg, "ошибка", type(e).__name__, flush=True)
            continue
        print(reg, len(d), flush=True)
        frames.append(d)
        # С октября 2026 года адрес DBInet.cgi отдаёт главную страницу Росстата вместо формы:
        # три пустых субъекта подряд в начале — база недоступна, дальше опрашивать незачем.
        empty = empty + 1 if d.empty and not any(len(f) for f in frames) else 0
        if empty >= 3:
            break
    frames = [f for f in frames if len(f)]
    if not frames:
        print(f"база показателей МО Росстата не отдаёт форму ({OUT.name} не создан). Возрастной слой "
              "сигналов будет нулевым; строгий прогноз от него не зависит. Возраст МО можно собрать из "
              "плоской выгрузки БД ПМО (scripts/41c_age_fill.py, data/external/bdmo/age_bdmo_all.parquet).")
        return
    d = pd.concat(frames, ignore_index=True).drop_duplicates("oktmo8")
    d.to_parquet(OUT, index=False)
    full = d[list(AGES)].notna().all(axis=1)
    gap = (d[list(AGES)].sum(axis=1) / d.total.where(d.total > 0) - 1).abs()
    print("МО:", len(d), "с полной структурой:", int(full.sum()), "сумма групп расходится с итогом больше 1 %:", int((gap[full] > 0.01).sum()))


if __name__ == "__main__":
    main()
