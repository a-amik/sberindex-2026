"""Chronos-2 в четырёх режимах.

На 12—23 точках истории фундаментальная модель не видит полного сезонного
цикла ряда, поэтому сырой ряд — проверка, а не ставка. Режимы:

* raw     — сырой ряд, каждый сам по себе;
* raw_cl  — сырой ряд с кросс-обучением: в пачке около сотни однородных рядов
            (одна категория, один тип поселения), модель делит информацию
            между ними — по отчёту Chronos-2 это помогает при короткой истории;
* dev     — отклонение МО от фактора группы с кросс-обучением; фактор берёт
            панельная модель;
* cov     — логарифм ряда с ковариатами: фактор группы (история и прогноз
            панельной модели вперёд как известное будущее) и число рабочих
            дней в месяце.

Прогноз — медиана; квантили 0,05 и 0,95 сохраняются для детектора шоков.
"""
from __future__ import annotations

import numpy as np

# torch импортируется внутри функций: импортированный раньше LightGBM, он приносит
# свою копию OpenMP, и на macOS LightGBM падает при сборке набора данных.

QUANTILES = [0.05, 0.5, 0.95]


def load(name: str = "amazon/chronos-2", device: str | None = None):
    """Chronos-2 по умолчанию; «amazon/chronos-bolt-base» — вторая фундаментальная модель:
    другая архитектура (прямой многошаговый прогноз квантилей, без кросс-обучения)."""
    import torch
    from chronos import BaseChronosPipeline, Chronos2Pipeline
    device = device or ("mps" if torch.backends.mps.is_available() else "cpu")
    if "bolt" in name:
        return BaseChronosPipeline.from_pretrained(name, device_map=device, torch_dtype=torch.float32)
    return Chronos2Pipeline.from_pretrained(name, device_map=device)


def _median(pipe, inputs, steps, cross, batch):
    if not hasattr(pipe, "predict_df") or "Bolt" in type(pipe).__name__:      # Chronos-Bolt
        import torch
        mids, los, his = [], [], []
        for i in range(0, len(inputs), batch):
            ctx = [torch.tensor(np.asarray(x, dtype=np.float32)) for x in inputs[i:i + batch]]
            q, _ = pipe.predict_quantiles(ctx, prediction_length=steps, quantile_levels=[0.1, 0.5, 0.9])  # Bolt обучен на 0,1…0,9
            q = q.detach().float().cpu().numpy()                      # ряды × шаги × квантили
            los.append(q[:, :, 0]); mids.append(q[:, :, 1]); his.append(q[:, :, 2])
        return np.concatenate(mids), np.concatenate(los), np.concatenate(his)
    out = pipe.predict(inputs, prediction_length=steps, batch_size=batch, cross_learning=cross)
    qs = getattr(pipe, "quantiles", None)
    qs = list(qs) if qs is not None else None
    res = []
    for t in out:
        a = t.detach().float().cpu().numpy()[0]            # первый таргет: квантили × шаги
        if qs:
            lo, mid, hi = (a[qs.index(q)] if q in qs else a[np.argmin(np.abs(np.array(qs) - q))] for q in QUANTILES)
        else:
            mid = lo = hi = a[a.shape[0] // 2]
        res.append((lo, mid, hi))
    return np.array([r[1] for r in res]), np.array([r[0] for r in res]), np.array([r[2] for r in res])


def make(pipe, mode: str, base, groups: np.ndarray, workdays: dict, periods: list[str], batch: int = 100,
         store: dict | None = None):
    order = np.argsort(groups, kind="stable")                # однородные ряды подряд — в одну пачку

    def model(hist, t0, steps, cx):
        n = hist.shape[0]
        fac, dd, m, d = base.parts(hist, t0, steps, cx)
        lh = np.log(hist)
        if mode in ("raw", "raw_cl"):
            inputs = [hist[i] for i in order]
        elif mode == "dev":
            inputs = [d[i] for i in order]
        else:
            wd_past = np.array([workdays[p] for p in periods[: t0 + 1]], float)
            wd_fut = np.array([workdays[periods[t0 + h]] for h in range(1, steps + 1)], float)
            inputs = [{"target": lh[i],
                       "past_covariates": {"factor": m[i], "workdays": wd_past},
                       "future_covariates": {"factor": fac[i], "workdays": wd_fut}} for i in order]
        cross = mode != "raw"
        mid, lo, hi = _median(pipe, inputs, steps, cross, batch)
        inv = np.empty(n, int)
        inv[order] = np.arange(n)
        mid, lo, hi = mid[inv], lo[inv], hi[inv]
        if mode == "dev":
            mid, lo, hi = np.exp(fac + mid), np.exp(fac + lo), np.exp(fac + hi)
        elif mode == "cov":
            mid, lo, hi = np.exp(mid), np.exp(lo), np.exp(hi)
        if store is not None:
            store[periods[t0]] = (lo, hi)
        return mid
    return model
