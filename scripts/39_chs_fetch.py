"""Акты о режиме ЧС: выгрузка с publication.pravo.gov.ru и распознавание сканов.

Нужен macOS: распознаёт встроенный Vision через пакет ocrmac, который
в окружение проекта не входит, — отдельное окружение:

    python3.12 -m venv .venv-ocr && .venv-ocr/bin/pip install ocrmac requests
    .venv-ocr/bin/python scripts/39_chs_fetch.py /tmp/chs-pages

Перечень актов — data/external/chs/pravo_all.json (запрос «чрезвычайной
ситуации», декабрь 2022 — декабрь 2024); тексты — data/external/chs/txt.
Готовая разметка лежит в results/signal_value/chs_events.json, поэтому
39_chs_markup.py проверку пересчитывает и без этого шага.
"""
import json, re, subprocess, pathlib, requests, sys, time, urllib.parse
from ocrmac import ocrmac
D=pathlib.Path(__file__).resolve().parents[1]/"data/external/chs"; (D/"txt").mkdir(parents=True,exist_ok=True); tmp=pathlib.Path(sys.argv[1])
if not (D / "pravo_all.json").exists():
    out, i = [], 1
    while True:
        u = ("http://publication.pravo.gov.ru/api/Documents?Name=" + urllib.parse.quote("чрезвычайной ситуации")
             + "&PeriodType=range&DocumentDateFrom=01.12.2022&DocumentDateTo=31.12.2024&PageSize=200&Index=%d" % i)
        it = requests.get(u, timeout=60).json().get("items", [])
        out += it
        if len(it) < 200:
            break
        i += 1; time.sleep(0.3)
    json.dump(out, open(D / "pravo_all.json", "w"), ensure_ascii=False)
a=json.load(open(D/"pravo_all.json"))
v=[x for x in a if re.search(r"о введении|об объявлении|о (?:режиме|функционировании)",x["name"].lower()) and not re.search("отмен|утратившим|изменени",x["name"].lower())]
for x in v:
    o=D/"txt"/f'{x["eoNumber"]}.txt'
    if o.exists(): continue
    pdf=tmp/"a.pdf"; pdf.write_bytes(requests.get("http://publication.pravo.gov.ru/file/pdf?eoNumber="+x["eoNumber"],timeout=120).content)
    for p in tmp.glob("pg-*.png"): p.unlink()
    subprocess.run(["pdftoppm","-r","200","-png",str(pdf),str(tmp/"pg")],check=True)
    lines=[]
    for p in sorted(tmp.glob("pg-*.png")):
        lines+=[t for t,c,b in ocrmac.OCR(str(p),language_preference=["ru-RU"]).recognize()]
    o.write_text("\n".join(lines)); print(x["eoNumber"],len(lines),flush=True)
