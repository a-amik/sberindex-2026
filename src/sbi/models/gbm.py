"""Глобальный градиентный бустинг поверх лучшей модели на панели.

Одна модель на все ряды и отдельная — на каждый шаг h (прямой многошаговый
прогноз). Цель — лог-поправка к прогнозу базовой панельной модели, сделанному
в ту же точку: бустинг учится не всему ряду, а тому, в чём база ошибается.

Обучающие примеры для точки T — пары (ряд, точка t) с t + h ≤ T: и признаки,
и цель известны к T. Внешние ряды берутся с лагом публикации: ИПЦ за месяц
выходит в середине следующего, зарплата — через два месяца.
"""
from __future__ import annotations

import lightgbm as lgb
import numpy as np
import pandas as pd

from . import panel as panel_models

# Запасные параметры на случай вызова без конфига; рабочие — models.lgbm.params в configs/default.yaml.
# Поправки МО шумные: без сильной регуляризации бустинг их переучивает и проигрывает базе.
PARAMS = dict(objective="l1", learning_rate=0.03, num_leaves=15, min_data_in_leaf=1000,
              feature_fraction=0.6, bagging_fraction=0.8, bagging_freq=1, lambda_l2=10.0, verbose=-1,
              num_threads=8, seed=42)


def context(panel, mo, nb, regional, national, base_model, cx, groups) -> dict:
    """Всё, что не зависит от точки прогноза: базовые прогнозы во всех точках, статика МО."""
    y = panel.y
    n, total = y.shape
    base = {}
    for t in range(11, total - 1):
        steps = min(12, total - 1 - t)
        base[t] = base_model(y[:, : t + 1], t, steps, cx)

    idx = panel.index.merge(mo, on="territory_id", how="left")
    static = pd.DataFrame({
        "category": panel.index.category.astype(str).astype("category").cat.codes,
        "mo_type": idx.mo_type.astype("category").cat.codes,
        "log_pop": np.log(idx["pop"]),
        "urban_share": idx.urban_share,
        "market_access": idx.market_access,
        "mono": (idx.mono_status != "").astype(int),
        "lat": idx.lat, "lon": idx.lon,
    })
    # соседи: строки тех же категорий у соседних МО
    row_of = {(tid, c): i for i, (tid, c) in enumerate(zip(panel.index.territory_id, panel.index.category.astype(str)))}
    nbm = nb.groupby("territory_id").neighbour_id.apply(list).to_dict()
    nb_rows = [[row_of[(j, c)] for j in nbm.get(tid, []) if (j, c) in row_of]
               for tid, c in zip(panel.index.territory_id, panel.index.category.astype(str))]

    reg = idx.region_key.to_numpy()
    cpi = regional.pivot_table(index="region_key", columns="period", values="cpi_total")
    wage = regional.pivot_table(index="region_key", columns="period", values="wage")
    return dict(base=base, base_model=base_model, cx=cx, static=static, nb_rows=nb_rows, reg=reg, cpi=cpi, wage=wage,
                national=national.set_index("period"), periods=panel.periods, groups=groups)


def _features(y, t, h, c):
    """Признаки на точку t для шага h: только данные по t включительно.

    В прогнозе вперёд история дописана прогнозом, и t выходит за конец известных
    месяцев. Внешние ряды (рост РФ, ставка, ИПЦ, зарплата) тогда замораживаются
    на последнем известном месяце — иначе в прогноз от декабря 2024 года попали бы
    факты 2025-го; календарь целевого месяца известен заранее и берётся настоящий."""
    known = c["periods"]
    last = len(known) - 1
    ext = lambda i: known[i] if i <= last else str(pd.Period(known[-1], "M") + (i - last))
    p = [ext(i) for i in range(max(len(known), t + h + 1))]
    pk = lambda i: known[min(i, last)]                    # месяц внешнего ряда, не позже истории
    ly = np.log(y[:, : t + 1])
    g = c["groups"]
    m = np.zeros_like(ly)
    for name in np.unique(g):
        s = g == name
        m[s] = np.median(ly[s], axis=0)
    d = ly - m
    nb_d = np.array([d[r, -1].mean() if r else np.nan for r in c["nb_rows"]])
    nb_d3 = np.array([(d[r, -1] - d[r, -4]).mean() if r else np.nan for r in c["nb_rows"]])
    f = c["static"].copy()
    f["h"] = h
    f["target_month"] = int(p[t + h][5:7])
    f["d0"], f["d1"], f["d3"], f["d12"] = d[:, -1], d[:, -2], d[:, -4], d[:, -1] - d[:, -13] if t >= 12 else np.nan
    f["d_mean6"] = d[:, -6:].mean(axis=1)
    f["d_std6"] = d[:, -6:].std(axis=1)
    f["d_lastyear_target"] = d[:, t + h - 12] - d[:, max(0, t - 11):].mean(axis=1)
    f["nb_d"], f["nb_d3"] = nb_d, nb_d3
    f["d_vs_nb"] = d[:, -1] - nb_d
    f["fac_g3"] = m[:, -1] - m[:, -4]
    f["fac_yoy"] = m[:, -1] - m[:, -13] if t >= 12 else np.nan
    f["base_g"] = np.log(c["base"][t][:, h - 1]) - ly[:, -1]
    nat = c["national"]
    f["nat_yoy"] = nat.loc[pk(t), "spend_yoy_nominal:Всего"]
    f["key_rate"] = nat.loc[pk(t), "key_rate_end"]
    tp = p[t + h]
    f["target_workdays"] = nat.loc[tp, "workdays"] if tp in nat.index else np.nan
    f["target_holidays"] = nat.loc[tp, "holidays"] if tp in nat.index else np.nan
    cpi_p, wage_p = pk(t - 1), pk(t - 2)                      # лаг публикации
    f["cpi_m"] = c["cpi"].reindex(c["reg"])[cpi_p].to_numpy() if cpi_p in c["cpi"] else np.nan
    yoy = [q for q in c["cpi"].columns if q <= cpi_p][-12:]
    f["cpi_12m"] = np.log(c["cpi"].reindex(c["reg"])[yoy] / 100).sum(axis=1).to_numpy()
    w = c["wage"].reindex(c["reg"])
    f["wage_yoy"] = np.log(w[wage_p] / w[pk(t - 14)]).to_numpy() if pk(t - 14) in w else np.nan
    return f


def make(c: dict):
    def base_at(hist, t, h, cx):
        """Прогноз базы из точки t хотя бы на h шагов. В бэктесте он всегда в кэше;
        в прогнозе вперёд история дописана прогнозом, и недостающее считается на лету."""
        have = c["base"].get(t)
        if have is None or have.shape[1] < h:
            c["base"][t] = c["base_model"](hist[:, : t + 1], t, max(h, min(12, hist.shape[1] - 1 - t)), cx)
        return c["base"][t]

    def model(hist, t0, steps, cx):
        n = hist.shape[0]
        base = base_at(hist, t0, steps, cx)[:, :steps]
        out = base.copy()
        for h in range(1, steps + 1):
            X, Y = [], []
            for t in range(11, t0 - h + 1):          # цель y[t+h] известна к t0
                base_at(hist, t, h, cx)              # признак base_g берёт тот же прогноз базы
                X.append(_features(hist, t, h, c))
                r = np.log(hist[:, t + h]) - np.log(base_at(hist, t, h, cx)[:, h - 1])
                # общая для группы ошибка месяца — шок, которого признаки МО не видят;
                # её оставляем фактору, бустинг учит только отличие МО от группы
                for name in np.unique(c["groups"]):
                    sel = c["groups"] == name
                    r[sel] -= np.median(r[sel])
                Y.append(r)
            if not X:
                continue                              # учиться не на чем: остаётся база
            Xtr, Ytr = pd.concat(X, ignore_index=True), np.concatenate(Y)
            rounds = int(np.clip(30 * len(X), 30, 200))
            booster = lgb.train(c.get("params") or PARAMS, lgb.Dataset(Xtr, Ytr), num_boost_round=rounds)
            corr = booster.predict(_features(hist, t0, h, c))
            out[:, h - 1] = base[:, h - 1] * np.exp(corr)
        return out
    return model
