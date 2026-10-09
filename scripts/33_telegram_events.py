"""Реестр событий из телеграм-каналов: покрытие, отклик расходов, прогноз и предупреждение.

Посты каналов властей и МЧС (31_telegram.py) размечаются теми же правилами,
что заголовки СМИ (newsgeo: типы событий и привязка к МО по газетиру); к тексту
дописывается субъект канала, иначе одноимённые МО других субъектов попадают ложно.
Четыре проверки:
1. покрытие — доля постов с привязкой к МО против 3,2 % у Интерфакса и Ленты;
2. отклик — отклонение МО от фактора (лог-ошибка итогового прогноза) в месяц
   события и в следующий, по типам, против МО-месяцев без событий;
3. прогноз — поправка первого шага для МО с событием типа «бедствие» или
   «выплаты» в месяце T; сила на целях до мая 2024 года, отчёт — с июня;
4. предупреждение — есть ли у МО с постом-бедствием в месяце t тревога
   детектора в t+1 чаще, чем у остальных (отношение шансов).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sbi import backtest, metrics, newsgeo  # noqa: E402

OUT = ROOT / "results/signal_value"
LAST, REPORT_FROM = "2024-12", "2024-06"
COLS = ["row", "origin", "step", "target", "y", "y_origin", "yhat"]
TYPES = ["disaster", "flood", "attack", "emergency", "payments", "plant", "layoff", "transport"]


def main():
    posts = pd.read_parquet(ROOT / "data/external/telegram_posts.parquet")
    posts = posts[posts.text.str.len() > 20].rename(columns={"text": "title"})
    # канал субъекта свой субъект в тексте не называет, а газетир привязывает одноимённое МО
    # только при названном субъекте: дописываем регион канала как контекст привязки
    posts["title"] = posts.title + np.where(posts.region != "*", " " + posts.region, "")
    mo = pd.read_parquet(ROOT / "data/processed/mo.parquet")
    gz = newsgeo.gazetteer(mo, ROOT / "data/raw/hackathon/t_dict_municipal_districts.xlsx")
    ann = newsgeo.annotate(posts, gz)
    # канал субъекта надёжен про свою территорию; чужие МО в его постах — чаще совпадения
    # со словами («Владимир» — имя, «Приволжский» — федеральный округ), чем события
    region_of = mo.set_index("territory_id").region
    ann["mos"] = [[m for m in ms if reg == "*" or region_of.get(m) == reg] for ms, reg in zip(ann.mos, ann.region)]
    ann.to_parquet(ROOT / "data/processed/telegram_annotated.parquet", index=False)
    with_type = ann.types.map(len) > 0
    print(f"постов {len(ann)}, с типом {with_type.mean()*100:.1f} %, с МО {(ann.mos.map(len) > 0).mean()*100:.1f} %, "
          f"с МО и типом {(with_type & (ann.mos.map(len) > 0)).mean()*100:.1f} %")
    print(ann.groupby("channel").apply(lambda d: round((d.mos.map(len) > 0).mean() * 100, 1)).to_dict())
    _, mo_m = newsgeo.monthly(ann, mo)
    mo_m = mo_m.set_index(["territory_id", "period"])
    for t in TYPES:
        if t not in mo_m.columns:
            mo_m[t] = 0.0
    print("МО-месяцев с событием по типам:", {t: int((mo_m[t] > 0).sum()) for t in TYPES})

    # — отклик: лог-ошибка итогового прогноза шага 1 (прогноз − факт) в месяц события и следующий
    panel = backtest.load_panel(ROOT / "data/processed")
    tid = panel.index.territory_id.to_numpy()
    cats = panel.index.category.astype(str).to_numpy()
    f = pd.read_parquet(OUT / "fc_ensemble+robust+growth_adj.parquet")
    f1 = f[f.step == 1].assign(tid=lambda d: tid[d.row], cat=lambda d: cats[d.row], e=lambda d: np.log(d.yhat / d.y))
    f1["e"] -= f1.groupby(["origin", "cat"]).e.transform("median")        # без общей части месяца
    rows = []
    for t in TYPES:
        ev = mo_m[mo_m[t] > 0].reset_index()[["territory_id", "period"]]
        if len(ev) < 5:
            continue
        for lag, name in ((0, "месяц события"), (1, "следующий месяц")):
            k = ev.assign(target=ev.period.map(lambda p: str(pd.Period(p, "M") + lag)))
            hit = f1.merge(k[["territory_id", "target"]].rename(columns={"territory_id": "tid"}), on=["tid", "target"])
            for c in ("Все категории", "Продовольствие", "Общественное питание"):
                s = hit[hit.cat == c]
                if len(s) >= 5:
                    rows.append({"тип": t, "когда": name, "категория": c, "n": len(s), "ошибка_%": s.e.mean() * 100,
                                 "se_%": s.e.std() / np.sqrt(len(s)) * 100})
    resp = pd.DataFrame(rows)
    resp.to_csv(OUT / "telegram_response.csv", index=False)
    pd.set_option("display.width", 220)
    print(resp.round(2).to_string(index=False))

    # — прогноз: поправка шага 1 для МО с бедствием / выплатами в месяце T
    rows = []
    for t in ("disaster", "payments", "attack"):
        flag = mo_m[t] > 0
        key = flag[flag].reset_index()[["territory_id", "period"]]
        x = f.merge(key.rename(columns={"territory_id": "tid", "period": "origin"}).assign(hit=1.0),
                    left_on=[pd.Series(tid[f.row], name="tid"), "origin"], right_on=["tid", "origin"], how="left").hit.fillna(0.0).to_numpy()
        x = x * np.where(f.step == 1, 1.0, 0.0)
        sel = (f.target <= "2024-05").to_numpy()
        mae = {b: (f.yhat[sel] * np.exp(b * x[sel]) - f.y[sel]).abs().mean() for b in (-0.06, -0.03, 0.0, 0.03, 0.06)}
        beta = min(mae, key=mae.get)
        g = f.assign(yhat=f.yhat * np.exp(beta * x))
        r = metrics.compare(g[g.origin >= REPORT_FROM][COLS], f[f.origin >= REPORT_FROM][COLS], 1, LAST, 1000, 42)
        rows.append({"тип": t, "МО-месяцев": int(flag.sum()), "β": beta, "MAE": r["MAE"], "MAE_ref": r["MAE_ref"], "gain_pct": r["gain_pct"]})
    fc = pd.DataFrame(rows)
    fc.to_csv(OUT / "telegram_forecast.csv", index=False)
    print(fc.round(3).to_string(index=False))

    # — предупреждение: тревога детектора в t+1 у МО с бедствием в t
    al = pd.read_csv(ROOT / "results/metrics/detect_real_alarms.csv")
    al_key = set(zip(al.territory_id, al.period))
    months = sorted(mo_m.reset_index().period.unique())
    rows = []
    for t in ("disaster", "attack", "emergency"):
        ev = set(zip(*mo_m[mo_m[t] > 0].reset_index()[["territory_id", "period"]].to_numpy().T))
        a = b = c = d = 0
        for m in months:
            nxt = str(pd.Period(m, "M") + 1)
            for tt in mo.territory_id:
                e, al1 = (tt, m) in ev, (tt, nxt) in al_key
                a += e and al1; b += e and not al1; c += (not e) and al1; d += (not e) and not al1
        odds = (a / max(b, 1)) / (c / max(d, 1)) if c else np.nan
        rows.append({"тип": t, "событий": a + b, "с тревогой в t+1": a, "доля_%": round(100 * a / max(a + b, 1), 1),
                     "доля без события_%": round(100 * c / max(c + d, 1), 2), "отношение шансов": round(odds, 2)})
    ew = pd.DataFrame(rows)
    ew.to_csv(OUT / "telegram_warning.csv", index=False)
    print(ew.to_string(index=False))


if __name__ == "__main__":
    main()
