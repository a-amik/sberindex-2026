"""Шаг 8. Графики и числа для колоды.

Снимает всё из results/metrics и data/processed и пишет SVG в папку колоды
вместе с deck-data.json — числами для крупных цифр на слайдах. Улучшили
модель — перезапустили этот шаг и сборку колоды.

    python scripts/08_figures.py --out <папка колоды>/assets/fig
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from sbi import backtest, config, detect, metrics  # noqa: E402
from sbi.config import ROOT  # noqa: E402
from sbi.models import panel as pm  # noqa: E402
from sbi.svg import Svg, nice, scale  # noqa: E402

M = ROOT / "results" / "metrics"
FC = ROOT / "results" / "forecasts"
CAT = {"Все категории": "--c-all", "Продовольствие": "--c-food", "Здоровье": "--c-health",
       "Общественное питание": "--c-cafe", "Транспорт": "--c-transport", "Маркетплейсы": "--c-market"}
SHORT = {"Все категории": "Все категории", "Продовольствие": "Продовольствие", "Здоровье": "Здоровье",
         "Общественное питание": "Общепит", "Транспорт": "Транспорт", "Маркетплейсы": "Маркетплейсы"}
MON = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
v = lambda name: f"var({name})"


def month_label(p):
    return f"{MON[int(p[5:7]) - 1]} {p[2:4]}"


def axis_months(s, periods, x, y0, every=3):
    for i, p in enumerate(periods):
        if i % every == 0:
            s.text(x(i), y0 + 26, month_label(p), 15, v("--text-3"), "middle")


def fig_categories(panel):
    W, H = 1440, 520
    s = Svg(W, H)
    per = sorted(panel.period.unique())
    cols, rows, gx, gy = 3, 2, 40, 54
    cw, ch = (W - gx * 2) / cols, (H - gy * 2) / rows
    for k, c in enumerate(CAT):
        cx, cy = (k % cols) * (cw + gx), (k // cols) * (ch + gy)
        med = panel[(panel.category == c) & panel.full].groupby("period").value.median().reindex(per)
        lo, hi = med.min(), med.max()
        x = scale(0, len(per) - 1, cx + 8, cx + cw - 8)
        y = scale(lo * 0.95, hi * 1.03, cy + ch - 30, cy + 46)
        s.text(cx + 8, cy + 24, SHORT[c], 20, v("--text"), weight=500)
        s.text(cx + cw - 8, cy + 24, f"{nice(med.iloc[-1])} ₽", 18, v("--text-2"), "end")
        s.line(cx + 8, cy + ch - 30, cx + cw - 8, cy + ch - 30, v("--line"))
        s.path([(x(i), y(val)) for i, val in enumerate(med)], v(CAT[c]), 3)
        for i in (11, 23):
            s.circle(x(i), y(med.iloc[i]), 4.5, v(CAT[c]))
        s.text(x(0), cy + ch - 6, "янв 23", 14, v("--text-3"))
        s.text(x(23), cy + ch - 6, "дек 24", 14, v("--text-3"), "end")
    return s.render()


def fig_common(panel):
    """Медианный МО и разброс МО вокруг неё: индекс к среднему 2023 года."""
    W, H = 1440, 520
    s = Svg(W, H)
    a = panel[(panel.category == "Все категории") & panel.full].pivot(index="territory_id", columns="period", values="value")
    idx = a.div(a.loc[:, "2023-01":"2023-12"].mean(axis=1), axis=0) * 100
    per = list(idx.columns)
    q = idx.quantile([0.1, 0.25, 0.5, 0.75, 0.9])
    x = scale(0, len(per) - 1, 80, W - 30)
    y = scale(70, 145, H - 60, 30)
    for t in (80, 100, 120, 140):
        s.line(80, y(t), W - 30, y(t), v("--line"))
        s.text(70, y(t) + 5, str(t), 15, v("--text-3"), "end")
    band = lambda a1, a2: [(x(i), y(val)) for i, val in enumerate(q.loc[a1])] + \
        [(x(i), y(val)) for i, val in reversed(list(enumerate(q.loc[a2])))]
    s.path(band(0.1, 0.9), "none", 0, fill=v("--c-all"), op=0.12)
    s.path(band(0.25, 0.75), "none", 0, fill=v("--c-all"), op=0.25)
    s.path([(x(i), y(val)) for i, val in enumerate(q.loc[0.5])], v("--c-all"), 3.5)
    axis_months(s, per, x, H - 60)
    s.text(W - 30, y(q.loc[0.5].iloc[-1]) - 14, "медианный МО", 16, v("--c-all"), "end", 500)
    s.text(W - 30, y(q.loc[0.9].iloc[-1]) - 10, "90 % МО", 15, v("--text-3"), "end")
    return s.render()


def fig_april(cases, national):
    W, H = 1100, 520
    s = Svg(W, H)
    t = cases["april"]
    cats = list(CAT)
    x0, gw = 120, (W - 160) / len(cats)
    y = scale(-26, 6, H - 70, 30)
    s.line(x0 - 20, y(0), W - 20, y(0), v("--line-2"))
    for t_ in (-20, -10):
        s.line(x0 - 20, y(t_), W - 20, y(t_), v("--line"), dash="4 6")
        s.text(x0 - 30, y(t_) + 5, f"{t_} %", 15, v("--text-3"), "end")
    for k, c in enumerate(cats):
        bx = x0 + k * gw
        for j, (grp, col, op) in enumerate((("район", CAT[c], 1.0), ("город", "--text-3", 0.55))):
            val = t[grp][c]
            top, bot = (y(0), y(val)) if val < 0 else (y(val), y(0))
            s.rect(bx + j * 46, top, 40, bot - top, v(col), 4, op)
            s.text(bx + j * 46 + 20, (y(val) + 22) if val < 0 else (y(val) - 8), nice(val), 15, v("--text-2"), "middle")
        s.text(bx + 43, H - 40, SHORT[c], 15, v("--text-2"), "middle")
    s.rect(x0 - 10, 20, 18, 18, v("--c-health"), 4)
    s.text(x0 + 16, 35, "районы и муниципальные округа", 16, v("--text-2"))
    s.rect(x0 + 300, 20, 18, 18, v("--text-3"), 4, 0.55)
    s.text(x0 + 326, 35, "города федерального значения", 16, v("--text-2"))
    return s.render()


def fig_decomp(panel_bt, mo, groups, ens):
    """Один МО: факт против прогноза ансамбля из точки июнь 2024 и факт против фактора группы."""
    W, H = 1440, 560
    s = Svg(W, H)
    idx = panel_bt.index
    row = int(np.where((idx.territory_id.to_numpy() == ens["tid"]) & (idx.category.astype(str).to_numpy() == "Все категории"))[0][0])
    y = panel_bt.y[row]
    per = panel_bt.periods
    g = groups[row]
    fac = np.exp(np.median(np.log(panel_bt.y[groups == g]), axis=0))
    fac = fac / fac[:12].mean() * y[:12].mean()
    f = pd.read_parquet(FC / "ensemble_strict.parquet")
    f = f[(f.row == row) & (f.origin == ens["origin"])].sort_values("step")
    t0 = per.index(ens["origin"])
    x = scale(0, len(per) - 1, 80, W - 40)
    lo, hi = min(y.min(), fac.min(), f.yhat.min()) * 0.92, max(y.max(), fac.max(), f.yhat.max()) * 1.04
    yy = scale(lo, hi, H - 60, 40)
    for t in np.linspace(lo, hi, 5)[1:-1]:
        s.line(80, yy(t), W - 40, yy(t), v("--line"))
        s.text(70, yy(t) + 5, nice(round(t, -2)), 14, v("--text-3"), "end")
    s.add(f'<rect x="{x(t0):.1f}" y="30" width="{x(len(per) - 1) - x(t0):.1f}" height="{H - 90}" fill="var(--blue)" fill-opacity="0.06"/>')
    s.path([(x(i), yy(val)) for i, val in enumerate(fac)], v("--text-3"), 2.5, dash="2 6")
    s.path([(x(i), yy(val)) for i, val in enumerate(y)], v("--text"), 3)
    s.path([(x(t0), yy(y[t0]))] + [(x(t0 + k), yy(val)) for k, val in zip(f.step, f.yhat)], v("--brand"), 3.5, dash="10 7")
    axis_months(s, per, x, H - 60)
    s.text(x(t0) + 10, 52, "прогноз, построенный в июне 2024", 15, v("--blue"))
    return s.render()


def fig_protocol(periods, sel, rep_from):
    W, H = 1440, 260
    s = Svg(W, H)
    x = scale(0, len(periods) - 1, 60, W - 60)
    for i, p in enumerate(periods):
        o = p >= "2023-12" and p <= "2024-11"
        col = v("--brand") if p in sel else (v("--blue") if p >= rep_from and o else (v("--text-2") if o else v("--line-2")))
        s.circle(x(i), 110, 11 if o else 6, col, 1 if o else 0.6)
        if i % 3 == 0 or p in ("2023-12", "2024-12"):
            s.text(x(i), 160, month_label(p), 15, v("--text-3"), "middle")
    s.line(x(0), 110, x(len(periods) - 1), 110, v("--line"), 2)
    s.text(x(0), 60, "история только для обучения", 17, v("--text-3"))
    s.text(x(periods.index("2023-12")), 60, "точки прогноза", 17, v("--text-2"))
    s.text(x(periods.index(sel[0])), 210, "окно отбора", 17, v("--brand"), weight=500)
    s.text(x(periods.index(rep_from)), 210, "отчётное окно", 17, v("--blue"), weight=500)
    return s.render()


def hbars(rows, W, H, xmax, label_w=420, colors=None, unit="", fmt=nice):
    s = Svg(W, H)
    n = len(rows)
    bh = min(40, (H - 20) / n - 12)
    x = scale(0, xmax, label_w, W - 90)
    for i, (name, val, col) in enumerate(rows):
        yy = 10 + i * (bh + 12)
        s.text(label_w - 16, yy + bh * 0.68, name, 17, v("--text"), "end")
        s.rect(label_w, yy, x(min(val, xmax)) - label_w, bh, v(col), 6)
        s.text(x(min(val, xmax)) + 10, yy + bh * 0.68, fmt(val) + unit + ("+" if val > xmax else ""), 17, v("--text-2"))
    return s.render()


def fig_vs_prophet(tab):
    W, H = 1440, 460
    s = Svg(W, H)
    hs = [1, 3, 6, 12]
    get = lambda m, h: float(tab[(tab.model == m) & (tab.H == h)].MAE.iloc[0])
    y = scale(0, 950, H - 60, 30)
    gw = (W - 160) / 4
    for t in (200, 400, 600, 800):
        s.line(100, y(t), W - 30, y(t), v("--line"))
        s.text(90, y(t) + 5, str(t), 15, v("--text-3"), "end")
    for k, h in enumerate(hs):
        bx = 140 + k * gw
        for j, (m, col) in enumerate((("prophet_default", "--text-3"), ("ensemble", "--brand"))):
            val = get(m, h)
            s.rect(bx + j * 110, y(val), 96, y(0) - y(val), v(col), 8, 0.6 if j == 0 else 1)
            s.text(bx + j * 110 + 48, y(val) - 10, nice(val), 17, v("--text"), "middle", 500 if j else 400)
        gain = (1 - get("ensemble", h) / get("prophet_default", h)) * 100
        s.text(bx + 103, H - 24, f"{h} мес. · −{nice(gain)} %", 17, v("--text-2"), "middle")
    return s.render()


def fig_waterfall(tab):
    W, H = 1440, 460
    s = Svg(W, H)
    get = lambda m: float(tab[(tab.model == m) & (tab.H == 1)].MAE.iloc[0])
    steps = [("Prophet", get("prophet_default")), ("динамика группы", get("factor_only")),
             ("города и районы", get("factor_only_bytype")), ("уровень МО", get("panel_blend_ses_bytype")),
             ("Chronos-2 и ансамбль", get("ensemble"))]
    y = scale(0, 650, H - 70, 30)
    gw = (W - 140) / len(steps)
    prev = None
    for k, (name, val) in enumerate(steps):
        bx = 100 + k * gw
        if prev is None:
            s.rect(bx, y(val), gw * 0.6, y(0) - y(val), v("--text-3"), 8, 0.6)
            s.text(bx + gw * 0.3, y(val) - 10, nice(val), 18, v("--text"), "middle")
        else:
            s.rect(bx, y(prev), gw * 0.6, y(val) - y(prev), v("--ok"), 6)
            s.rect(bx, y(val), gw * 0.6, y(0) - y(val), v("--brand"), 8, 0.22)
            s.text(bx + gw * 0.3, y(prev) - 10, f"−{nice(prev - val)}", 18, v("--ok"), "middle", 500)
            s.text(bx + gw * 0.3, y(val) + 26, nice(val), 17, v("--text"), "middle")
        s.text(bx + gw * 0.3, H - 34, name, 16, v("--text-2"), "middle")
        prev = val
    return s.render()


def fig_chronos(tab):
    rows = []
    names = [("chronos2_raw", "Chronos-2, исходный ряд", "--text-3"), ("chronos2_raw_cl", "исходный ряд, обучение на всех рядах", "--text-3"),
             ("prophet_default", "Prophet по умолчанию", "--warn"), ("chronos2_cov", "динамика группы как внешний признак", "--c-transport"),
             ("snaive_growth", "прошлый год с поправкой на рост", "--text-2"), ("chronos2_dev", "Chronos-2, уровень муниципалитета", "--brand")]
    for m, label, col in names:
        rows.append((label, float(tab[(tab.model == m) & (tab.H == 1)].MAE.iloc[0]), col))
    return hbars(rows, 1440, 420, 720, 470)


def fig_steps():
    W, H = 1440, 440
    s = Svg(W, H)
    x = scale(1, 12, 90, W - 40)
    y = scale(250, 1300, H - 50, 20)
    for t in (400, 600, 800, 1000, 1200):
        s.line(90, y(t), W - 40, y(t), v("--line"))
        s.text(80, y(t) + 5, str(t), 15, v("--text-3"), "end")
    for m, col, w in (("prophet_default", "--warn", 3), ("snaive_growth", "--text-3", 2.5), ("ensemble", "--brand", 4)):
        f = pd.read_parquet(FC / f"{m}.parquet")
        by = f.assign(e=(f.yhat - f.y).abs()).groupby("step").e.mean()
        s.path([(x(h), y(min(val, 1300))) for h, val in by.items()], v(col), w)
        s.text(x(12) - 4, y(min(by.iloc[-1], 1300)) - 12, {"prophet_default": "Prophet", "snaive_growth": "сезонный эталон",
                                                          "ensemble": "ансамбль"}[m], 16, v(col), "end", 500)
    for h in range(1, 13):
        s.text(x(h), H - 18, str(h), 15, v("--text-3"), "middle")
    return s.render()


def fig_shocks():
    W, H = 1440, 230
    s = Svg(W, H)
    t = np.arange(18)
    base = 100 + 4 * np.sin(t / 2.1)
    shapes = [("ступенька", np.where(t >= 9, -18, 0)), ("сдвиг за три месяца", -18 * np.clip((t - 8) / 3, 0, 1)),
              ("выброс на месяц", np.where(t == 9, -24, 0))]
    cw = (W - 80) / 3
    for k, (name, eff) in enumerate(shapes):
        cx = 20 + k * (cw + 20)
        x = scale(0, 17, cx + 10, cx + cw - 10)
        y = scale(70, 110, H - 30, 50)
        s.path([(x(i), y(val)) for i, val in enumerate(base)], v("--text-3"), 2, dash="3 6")
        s.path([(x(i), y(val)) for i, val in enumerate(base + eff)], v("--text"), 3)
        s.circle(x(9), y((base + eff)[9]), 7, v("--shift"))
        s.text(cx + 10, 28, name, 19, v("--text"), weight=500)
    return s.render()


def fig_detect(bench):
    W, H = 1100, 520
    s = Svg(W, H)
    x = scale(0, 0.6, 90, W - 40)
    y = scale(0, 0.75, H - 60, 30)
    for t in (0.2, 0.4, 0.6):
        s.line(x(t), 30, x(t), H - 60, v("--line"))
        s.text(x(t), H - 34, nice(t), 15, v("--text-3"), "middle")
        s.line(90, y(t), W - 40, y(t), v("--line"))
        s.text(80, y(t) + 5, nice(t), 15, v("--text-3"), "end")
    s.text((W + 90) / 2, H - 6, "полнота", 16, v("--text-2"), "middle")
    s.text(24, 30, "точность", 16, v("--text-2"))
    pick = {"zscore": ("z-оценка", "--c-all"), "bocpd": ("BOCPD", "--c-food"), "panel": ("панельный", "--c-transport"),
            "forecast": ("коридор прогноза", "--c-cafe"), "cusum": ("CUSUM", "--text-3"),
            "zscore&bocpd": ("оба вместе", "--brand"), "zscore|bocpd": ("любой из двух", "--ok")}
    for _, r in bench.iterrows():
        if r.method not in pick:
            continue
        name, col = pick[r.method]
        s.circle(x(r.recall), y(r.precision), 11, v(col))
        s.text(x(r.recall) + 16, y(r.precision) + 6, name, 16, v("--text"))
    return s.render()


def project(lat, lon):
    lam = np.radians(np.minimum(lon, 150) - 90)
    return lam * np.cos(np.radians(58)), -np.radians(lat)


def fig_map(mo, alarms, flood_regions, W=1100, H=700):
    s = Svg(W, H)
    m = mo.dropna(subset=["lat", "lon"])
    m = m[(m.lon > 19) & (m.lat > 41)]
    px, py = project(m.lat.to_numpy(), m.lon.to_numpy())
    sx = scale(px.min(), px.max(), 30, W - 30)
    sy = scale(py.min(), py.max(), 30, H - 30)
    flood = m.region.isin(flood_regions).to_numpy()
    hit = m.territory_id.isin(set(alarms)).to_numpy()
    for i in np.where(~flood)[0]:
        s.circle(sx(px[i]), sy(py[i]), 4, v("--text-3"), 0.45)
    for i in np.where(flood & ~hit)[0]:
        s.circle(sx(px[i]), sy(py[i]), 6, v("--blue"), 0.8)
    for i in np.where(hit)[0]:
        s.circle(sx(px[i]), sy(py[i]), 12 if flood[i] else 6, v("--shift"), 0.95 if flood[i] else 0.6)
    return s.render()


def fig_flood_share(share):
    W, H = 900, 640
    s = Svg(W, H)
    per = list(share.index)
    x = scale(0, len(per) - 1, 80, W - 40)
    y = scale(0, 2.0, H - 50, 20)
    for t in (0.5, 1.0, 1.5):
        s.line(80, y(t), W - 40, y(t), v("--line"))
        s.text(70, y(t) + 5, nice(t) + " %", 15, v("--text-3"), "end")
    s.path([(x(i), y(val)) for i, val in enumerate(share["rest"])], v("--text-3"), 2.5)
    s.path([(x(i), y(val)) for i, val in enumerate(share["flood"])], v("--shift"), 4)
    axis_months(s, per, x, H - 50, 4)
    s.text(x(per.index("2024-04")), y(share["flood"].max()) - 16, "паводковые субъекты", 16, v("--shift"), "middle", 500)
    s.text(W - 40, y(share["rest"].iloc[-1]) + 30, "остальная страна", 15, v("--text-3"), "end")
    return s.render()


def fig_news_profile(ev):
    W, H = 1440, 440
    s = Svg(W, H)
    ev = ev.head(5)
    cats = [("Здоровье", "--c-health"), ("Транспорт", "--c-transport"), ("Продовольствие", "--c-food")]
    y = scale(-6, 6, H - 70, 30)
    s.line(60, y(0), W - 20, y(0), v("--line-2"))
    for t in (-4, 4):
        s.line(60, y(t), W - 20, y(t), v("--line"), dash="4 6")
        s.text(50, y(t) + 5, f"{t:+d} %", 15, v("--text-3"), "end")
    gw = (W - 100) / len(ev)
    for k, r in enumerate(ev.itertuples()):
        bx = 90 + k * gw
        for j, (c, col) in enumerate(cats):
            val = getattr(r, {"Здоровье": "health", "Транспорт": "transport", "Продовольствие": "food"}[c])
            top, bot = (y(0), y(val)) if val < 0 else (y(val), y(0))
            s.rect(bx + j * 58, top, 50, bot - top, v(col), 4)
            s.text(bx + j * 58 + 25, (y(val) + 20) if val < 0 else (y(val) - 8), nice(val), 14, v("--text-2"), "middle")
        s.text(bx + 80, H - 40, r.label, 15, v("--text-2"), "middle")
    return s.render()


def main():
    cfg, args = config.cli(__doc__, lambda ap: ap.add_argument("--out", required=True))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    P = cfg.path("processed")
    panel = pd.read_parquet(P / "panel.parquet")
    mo = pd.read_parquet(P / "mo.parquet")
    nat = pd.read_parquet(P / "national.parquet")
    tab = pd.read_csv(M / "forecast_by_horizon.csv")
    cmp = pd.read_csv(M / "forecast_vs_prophet_default.csv")
    grid = pd.read_csv(M / "prophet_grid_by_horizon.csv")
    bench = pd.read_csv(M / "detect_benchmark.csv")
    # «Наш прогноз» на слайдах — сдаваемый строгий прогноз (37_strict.py). Таблицы
    # бэктеста от 04.10 держат первую редакцию ансамбля, поэтому его строки
    # пересчитываются здесь из прогноза тем же модулем метрик.
    bt = cfg["backtest"]
    last = "2024-12"
    st = pd.read_parquet(FC / "ensemble_strict.parquet")
    pr = pd.read_parquet(FC / "prophet_default.parquet")
    tab = pd.concat([tab[tab.model != "ensemble"], metrics.table({"ensemble": st}, (1, 3, 6, 12), last)], ignore_index=True)
    cmp = pd.concat([cmp[cmp.model != "ensemble"], pd.DataFrame(
        [{"model": "ensemble", **metrics.compare(st, pr, h, last, bt["bootstrap"], bt["seed"])} for h in (1, 3, 6, 12)])], ignore_index=True)
    rc = json.load(open(M / "real_cases.json"))
    news = json.load(open(M / "news_report.json"))
    pbt = backtest.load_panel(P, "full")
    groups = pm.groups(pbt.index, mo, "type")

    # апрель 2023: изменение к марту по типам поселения
    w = panel[panel.period.isin(["2023-03", "2023-04"])].pivot_table(index=["territory_id", "category"], columns="period",
                                                                     values="value", observed=True).dropna()
    w["chg"] = (np.log(w["2023-04"]) - np.log(w["2023-03"])) * 100
    w = w.reset_index().merge(mo[["territory_id", "mo_type"]], on="territory_id")
    w["grp"] = np.where(w.mo_type.isin(pm.URBAN), "город", "район")
    w.loc[w.mo_type == "городской округ", "grp"] = "ГО"
    april = {g: w[w.grp == ("район" if g == "район" else "город")].groupby("category", observed=True).chg.median().round(1).to_dict()
             for g in ("район", "город")}
    w_city = w[w.mo_type == "внутригородская территория города федерального значения"].groupby("category", observed=True).chg.median()
    april["город"] = w_city.round(1).to_dict()
    nat_i = nat.set_index("period")["spend_bn:Всего"]
    nat_chg = float(np.log(nat_i["2023-04"] / nat_i["2023-03"]) * 100)

    # МО для разложения: район со средним уровнем
    allc = panel[(panel.category == "Все категории") & panel.full].groupby("territory_id").value.mean()
    cand = mo[mo.mo_type == "муниципальный район"].territory_id
    tid = int((allc[allc.index.isin(cand)] - allc.median()).abs().idxmin())

    # паводки: доля рядов с тревогой по месяцам
    al = pd.read_csv(M / "detect_real_alarms.csv")            # субъект в файле тревог уже есть
    fr = cfg["cases"]["floods_2024"]["regions"]
    nser = panel[panel.full].merge(mo[["territory_id", "region"]], on="territory_id")
    nser["flood"] = nser.region.isin(fr)
    denom = nser[nser.period >= "2023-05"].groupby(["period", "flood"]).size().unstack()
    al["flood"] = al.region.isin(fr)
    num = al.groupby(["period", "flood"]).size().unstack().reindex(denom.index).fillna(0)
    share = (num / denom * 100).rename(columns={True: "flood", False: "rest"})[["flood", "rest"]]
    share = share.rolling(2, min_periods=1).mean()
    flood_alarms = al[al.flood & al.period.between("2024-04", "2024-06")].territory_id.unique()

    ev = pd.DataFrame(news["major_events"])
    names = {"оренбургская": "Оренбургская", "курганская": "Курганская", "тюменская": "Тюменская", "приморский": "Приморье",
             "челябинская": "Челябинская", "карелия": "Карелия", "омская": "Омская"}
    ev["label"] = [f"{names.get(r, r)}, {month_label(p)}" for r, p in zip(ev.region_key, ev.period)]
    ev = ev.rename(columns={"Здоровье": "health", "Транспорт": "transport", "Продовольствие": "food"})

    figs = {
        "categories": fig_categories(panel),
        "common": fig_common(panel),
        "april": fig_april({"april": april}, nat),
        "decomp": fig_decomp(pbt, mo, groups, {"tid": tid, "origin": "2024-06"}),
        "protocol": fig_protocol(pbt.periods, [p for p in pbt.periods if "2023-12" <= p < cfg["ensemble"]["report_from"] and p < cfg["ensemble"]["select_last_target"]], cfg["ensemble"]["report_from"]),
        "prophet_grid": hbars([(lbl, float(grid[(grid.model == m) & (grid.H == 1)].MAE.iloc[0]), col) for m, lbl, col in (
            ("default", "по умолчанию: без сезонности", "--brand"), ("yearly5_mult", "5 гармоник, сезонность множителем", "--text-3"),
            ("yearly3_add", "3 гармоники, сезонность слагаемым", "--text-3"), ("yearly3_mult", "3 гармоники, сезонность множителем", "--text-3"),
            ("yearly3_mult_cp001", "то же, слабый тренд", "--text-3"), ("yearly3_mult_prior1", "то же, сдержанная сезонность", "--text-3"), ("yearly3_log", "3 гармоники, по логарифму трат", "--text-3"),
            ("yearly3_mult_flat", "3 гармоники, без тренда", "--text-3"))], 1440, 470, 1200, 470),
        "vs_prophet": fig_vs_prophet(tab),
        "waterfall": fig_waterfall(tab),
        "chronos": fig_chronos(tab),
        "steps": fig_steps(),
        "shocks": fig_shocks(),
        "detect": fig_detect(bench),
        "map_floods": fig_map(mo, flood_alarms, fr),
        "flood_share": fig_flood_share(share),
        "news_profile": fig_news_profile(ev),
    }
    for k, svgtxt in figs.items():
        (out / f"{k}.svg").write_text(svgtxt, encoding="utf-8")

    get = lambda m, h, col="MAE": float(tab[(tab.model == m) & (tab.H == h)][col].iloc[0])
    c = cmp[cmp.model == "ensemble"].set_index("H")
    cat = pd.read_csv(M / "forecast_by_category.csv")
    cats = pbt.index.category.astype(str).to_numpy()
    rows = []
    for h in (1, 3, 6, 12):
        d = metrics.horizon_rows(st, h, last)
        rows += [{"model": "ensemble", "H": h, "category": ct, **metrics.scores(g)} for ct, g in d.groupby(cats[d.row.to_numpy()])]
    cat = pd.concat([cat[cat.model != "ensemble"], pd.DataFrame(rows)], ignore_index=True)
    heat = {}
    for ct in CAT:
        heat[SHORT[ct]] = {h: round((1 - float(cat[(cat.model == "ensemble") & (cat.H == h) & (cat.category == ct)].MAE.iloc[0]) /
                                     float(cat[(cat.model == "prophet_default") & (cat.H == h) & (cat.category == ct)].MAE.iloc[0])) * 100, 1)
                           for h in (1, 3, 6, 12)}
    data = {
        "mae": {m: {h: round(get(m, h), 1) for h in (1, 3, 6, 12)} for m in tab.model.unique()},
        "r2g": {m: {h: round(get(m, h, "R2_growth"), 2) for h in (1, 3, 6, 12)} for m in ("ensemble", "prophet_default")},
        "wape": {h: round(get("ensemble", h, "WAPE"), 1) for h in (1, 3, 6, 12)},
        "gain": {h: round(float(c.loc[h, "gain_pct"]), 1) for h in (1, 3, 6, 12)},
        "share_better": {h: round(float(c.loc[h, "share_series_better"]) * 100) for h in (1, 3, 6, 12)},
        "ci": {h: [round(float(c.loc[h, "boot_ci_low"])), round(float(c.loc[h, "boot_ci_high"]))] for h in (1, 3, 6, 12)},
        "heat": heat,
        "april": april, "april_rf_pct": round(nat_chg, 1),
        "decomp_mo": mo.set_index("territory_id").loc[tid, ["name", "region"]].to_dict(),
        "bench": bench.set_index("method")[["recall", "precision", "f1", "fa_per_100", "delay_mean", "recall_over_random"]].round(3).to_dict("index"),
        "cases": rc, "news": {k: news[k] for k in ("headlines", "by_source", "typed_pct", "with_region_pct", "with_mo_pct",
                                                   "event_study", "alarm_explained", "early_warning_auc")},
        "events": ev.drop(columns=["label"]).to_dict("records"),
    }
    (out / "deck-data.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"графиков: {len(figs)}, данные: deck-data.json → {out}")


if __name__ == "__main__":
    main()
