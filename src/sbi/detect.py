"""Обнаружение точек структурных изменений.

Сигнал — отклонение МО от фактора своей группы (категория × город или
район) в логарифмах: на сыром ряде разломом читался бы каждый декабрь,
а общий для всех МО шок фактор гасит ещё до детектора.

Все детекторы онлайн: тревогу в месяце t поднимают только по данным до t
включительно. Каждый отдаёт балл; тревога — балл выше порога θ.
"""
from __future__ import annotations

import numpy as np
import ruptures as rpt
from scipy import stats

MIN_HIST = 4          # месяцев истории до первой тревоги


def signal(y: np.ndarray, groups: np.ndarray) -> np.ndarray:
    ly = np.log(y)
    m = np.zeros_like(ly)
    for g in np.unique(groups):
        s = groups == g
        m[s] = np.median(ly[s], axis=0)
    return ly - m


def _mad(x, axis=None):
    return 1.4826 * np.median(np.abs(x - np.median(x, axis=axis, keepdims=True)), axis=axis)


def group_scale(d: np.ndarray, groups: np.ndarray, t: int) -> np.ndarray:
    """Типичный месячный ход отклонения в группе по данным до t — общий масштаб для баллов."""
    t = max(t, 3)          # в первые месяцы приростов ещё мало: берём первые четыре месяца
    dd = np.diff(d[:, : t + 1], axis=1)
    sc = np.empty(d.shape[0])
    for g in np.unique(groups):
        s = groups == g
        sc[s] = max(_mad(dd[s].ravel()), 1e-3)
    return sc


def scores(d: np.ndarray, groups: np.ndarray, nb_rows: list, method: str, t: int, state: dict) -> np.ndarray:
    """Балл детектора в месяце t по d[:, :t+1]."""
    x = d[:, : t + 1]
    sc = group_scale(d, groups, t)
    if method == "zero":
        return np.zeros(len(d))
    if method == "zscore":
        past = x[:, :-1]
        mu, sd = past.mean(axis=1), np.maximum(past.std(axis=1, ddof=1), sc)
        return np.abs(x[:, -1] - mu) / sd
    if method == "panel":
        jump = x[:, -1] - x[:, -4:-1].mean(axis=1)
        nb = np.array([np.median(jump[r]) if r else 0.0 for r in nb_rows])
        rel = jump - nb
        out = np.empty(len(d))
        for g in np.unique(groups):
            s = groups == g
            out[s] = np.abs(rel[s] - np.median(rel[s])) / max(_mad(rel[s]), 1e-3)
        return out
    if method == "cusum":
        k = 0.5
        if "lvl" not in state:
            state["lvl"] = x[:, :-1].mean(axis=1)
            state["sp"] = np.zeros(len(d)); state["sn"] = np.zeros(len(d))
        e = (x[:, -1] - state["lvl"]) / sc
        state["sp"] = np.maximum(0, state["sp"] + e - k)
        state["sn"] = np.maximum(0, state["sn"] - e - k)
        state["lvl"] = 0.7 * state["lvl"] + 0.3 * x[:, -1]
        return np.maximum(state["sp"], state["sn"])
    if method == "bocpd":
        return _bocpd_step(x[:, -1] / sc, state)
    if method == "forecast":
        # выход за коридор прогноза на месяц вперёд: прогноз отклонения —
        # сглаженный уровень до t−1, коридор — разброс остатков группы до t−1
        lvl = state.get("lvl_f")
        if lvl is None:
            lvl = x[:, 0].copy()
            for j in range(1, x.shape[1] - 1):
                lvl = 0.5 * x[:, j] + 0.5 * lvl
        resid = x[:, -1] - lvl
        state["lvl_f"] = 0.5 * x[:, -1] + 0.5 * lvl
        return np.abs(resid) / sc
    raise ValueError(method)


def _bocpd_step(xt: np.ndarray, st: dict, hazard: float = 1 / 24) -> np.ndarray:
    """Байесовский онлайн-детектор (Adams, MacKay 2007), нормальная модель
    с неизвестными средним и дисперсией (сопряжённое нормальное-гамма),
    векторно по рядам. Балл — вероятность, что смена режима была в этом
    или прошлом месяце: P(run length ≤ 1)."""
    n = len(xt)
    if "R" not in st:
        st["R"] = np.ones((n, 1))
        st["mu"] = xt[:, None].copy(); st["k"] = np.ones((n, 1))
        st["a"] = np.ones((n, 1)); st["b"] = np.ones((n, 1)) * 1.0
        return np.zeros(n)
    mu, k, a, b, R = st["mu"], st["k"], st["a"], st["b"], st["R"]
    scale = np.sqrt(b * (k + 1) / (a * k))
    # логарифмы: на сильном скачке плотности всех длин серии уходят в машинный ноль
    logp = stats.t.logpdf(xt[:, None], 2 * a, loc=mu, scale=scale) + np.log(np.maximum(R, 1e-300))
    top = logp.max(axis=1, keepdims=True)
    w = np.exp(logp - top)
    growth = w * (1 - hazard)
    cp = (w * hazard).sum(axis=1, keepdims=True)
    R = np.hstack([cp, growth])
    R /= R.sum(axis=1, keepdims=True)
    mu1 = (k * mu + xt[:, None]) / (k + 1)
    a1 = a + 0.5
    b1 = b + k * (xt[:, None] - mu) ** 2 / (2 * (k + 1))
    st["mu"] = np.hstack([xt[:, None], mu1]); st["k"] = np.hstack([np.ones((n, 1)), k + 1])
    st["a"] = np.hstack([np.ones((n, 1)), a1]); st["b"] = np.hstack([np.ones((n, 1)), b1])
    st["R"] = R
    return R[:, :2].sum(axis=1)


CHRONOS_CACHE = __import__("pathlib").Path(__file__).resolve().parents[2] / "results/cache"   # кэш баллов Chronos-2


def chronos_online(d: np.ndarray, start: int = MIN_HIST, batch: int = 256) -> np.ndarray:
    """Детектор на интервале Chronos-2. В месяце t модель с кросс-обучением
    прогнозирует отклонение на шаг вперёд по истории до t−1; балл — расстояние
    факта от медианы в долях полуширины интервала 0,05—0,95. Баллы
    кэшируются по содержимому d: один и тот же сигнал не прогоняется дважды."""
    import hashlib
    from pathlib import Path
    key = hashlib.sha1(np.ascontiguousarray(d).tobytes() + bytes([start])).hexdigest()[:16]
    cache = Path(CHRONOS_CACHE) / f"chronos_{key}.npy" if CHRONOS_CACHE else None
    if cache is not None and cache.exists():
        return np.load(cache)
    from .models import foundation
    pipe = foundation.load()
    n, T = d.shape
    out = np.zeros((n, T))
    for t in range(start, T):
        mid, lo, hi = foundation._median(pipe, [d[i, :t] for i in range(n)], 1, True, batch)
        half = np.maximum((hi[:, 0] - lo[:, 0]) / 2, 1e-4)
        out[:, t] = np.abs(d[:, t] - mid[:, 0]) / half
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        np.save(cache, out)
    return out


def choice(path) -> dict:
    """Выбор 05_detect.py: ведущий метод, пара для согласия и пороги."""
    import json
    return json.loads(open(path).read())


def alarm_pair(d, groups, nb_rows, ch: dict, start=MIN_HIST):
    """Согласие пары, выбранной на настроечной выборке, и тревоги каждого из двух."""
    m1, m2 = ch["pair"]
    a1 = run_online(d, groups, nb_rows, m1, start) > ch["thresholds"][m1]
    a2 = run_online(d, groups, nb_rows, m2, start) > ch["thresholds"][m2]
    return agree(a1, a2), a1, a2


def run_online(d, groups, nb_rows, method, start=MIN_HIST):
    """Баллы по всем месяцам: строки × месяцы, до start — нули."""
    if method == "chronos":
        return chronos_online(d, start)
    n, T = d.shape
    out = np.zeros((n, T))
    st: dict = {}
    if method == "bocpd":
        for t in range(start - 1):
            scores(d, groups, nb_rows, method, t, st)
    for t in range(start, T):
        out[:, t] = scores(d, groups, nb_rows, method, t, st)
    return out


def confirm_pelt(d_row: np.ndarray, t: int, pen: float, scale: float) -> bool:
    """Офлайн-подтверждение: PELT по d[:t+2], нормированному на масштаб группы,
    ставит разлом в t−1…t+1."""
    x = d_row[: t + 2] / scale
    if len(x) < 6:
        return False
    bk = rpt.Pelt(model="l2", min_size=2).fit(x.reshape(-1, 1)).predict(pen=pen)
    return any(t - 1 <= b <= t + 1 for b in bk[:-1])


def inject(y: np.ndarray, rng, share: float, sizes, kinds, first: int, last: int):
    """Полусинтетика: в долю рядов вносится шок в месяц τ. Возвращает новые ряды и разметку."""
    y2 = y.copy()
    n, T = y.shape
    hit = rng.random(n) < share
    tau = np.full(n, -1)
    kind = np.array([""] * n, dtype=object)
    size = np.zeros(n)
    for i in np.where(hit)[0]:
        tau[i] = rng.integers(first, last + 1)
        kind[i] = kinds[rng.integers(len(kinds))]
        size[i] = sizes[rng.integers(len(sizes))] * rng.choice([-1, 1])
        t = np.arange(T)
        if kind[i] == "step":
            eff = np.where(t >= tau[i], size[i], 0.0)
        elif kind[i] == "ramp":
            eff = size[i] * np.clip((t - tau[i] + 1) / 3, 0, 1)
        else:
            eff = np.where(t == tau[i], size[i], 0.0)
        y2[i] = y[i] * np.exp(eff)
    return y2, {"tau": tau, "kind": kind, "size": size}


def evaluate(alarm: np.ndarray, truth: dict, first: int, max_delay: int = 2) -> dict:
    """Полнота, точность, задержка и ложные тревоги на 100 ряд-месяцев.

    Шок найден, если первая тревога в окне [τ, τ + max_delay]. Ложная тревога —
    тревога в ряду без шока или в ряду с шоком вне этого окна. В «чистых» рядах
    есть свои настоящие сдвиги, поэтому точность здесь — оценка снизу.
    """
    n, T = alarm.shape
    tau = truth["tau"]
    hit = tau >= 0
    found, delays = np.zeros(n, bool), np.full(n, np.nan)
    fa = 0
    months = 0
    for i in range(n):
        a = np.where(alarm[i, first:])[0] + first
        if hit[i]:
            inwin = a[(a >= tau[i]) & (a <= tau[i] + max_delay)]
            if len(inwin):
                found[i], delays[i] = True, inwin[0] - tau[i]
            fa += ((a < tau[i]) | (a > tau[i] + max_delay)).sum()
        else:
            fa += len(a)
        months += T - first
    tp = found.sum()
    total_alarms = alarm[:, first:].sum()
    recall = tp / hit.sum() if hit.any() else np.nan
    precision = tp / max(total_alarms, 1)
    out = {"recall": recall, "precision": precision,
           "f1": 2 * precision * recall / max(precision + recall, 1e-9),
           "fa_per_100": fa / months * 100, "delay_mean": float(np.nanmean(delays)) if tp else np.nan,
           "alarms": int(total_alarms)}
    # случайная тревога с той же частотой: вероятность хотя бы одной в окне
    p = total_alarms / (n * (T - first))
    out["recall_random"] = 1 - (1 - p) ** (max_delay + 1)
    out["recall_over_random"] = recall / max(out["recall_random"], 1e-9)
    by = {}
    for k in np.unique(truth["kind"][hit]):
        s = hit & (truth["kind"] == k)
        by[k] = float(found[s].mean())
    for z in np.unique(np.abs(truth["size"][hit])):
        s = hit & (np.abs(truth["size"]) == z)
        by[f"size_{z:.1f}"] = float(found[s].mean())
    out["recall_by"] = by
    return out


def past(a: np.ndarray, k: int = 1) -> np.ndarray:
    """Тревога, бывшая k месяцев назад, датированная текущим месяцем; без заворота
    последних месяцев в начало ряда, как у np.roll."""
    out = np.zeros_like(a)
    out[:, k:] = a[:, :-k]
    return out


def agree(a1: np.ndarray, a2: np.ndarray) -> np.ndarray:
    """Онлайн-согласие двух детекторов: тревога в месяц t, если к t сработали оба —
    каждый в t или в t−1. До 04.10.2026 окно было ±1 месяц через np.roll, то есть
    подтверждение из t+1 засчитывалось в t, а декабрь заворачивался на январь."""
    return (a1 & (a2 | past(a2))) | (a2 & (a1 | past(a1)))
