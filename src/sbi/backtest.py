"""Скользящий бэктест.

Точка прогноза T идёт от first_origin до last_origin, окно расширяется:
модель видит ряд по T включительно и прогнозирует шаги 1…min(12, конец − T).
Горизонт H оценивается по шагам 1…H в тех точках, где окно целиком лежит
в данных: для H = 12 это одна точка, декабрь 2023 года.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Panel:
    y: np.ndarray              # ряды × месяцы
    periods: list[str]
    index: pd.DataFrame        # territory_id, category для каждой строки y

    def pos(self, period: str) -> int:
        return self.periods.index(period)


def load_panel(processed, series: str = "full") -> Panel:
    p = pd.read_parquet(processed / "panel.parquet")
    if series == "full":
        p = p[p.full]
    w = p.pivot_table(index=["territory_id", "category"], columns="period", values="value", observed=True)
    w = w.dropna() if series == "full" else w
    return Panel(y=w.to_numpy(float), periods=list(w.columns), index=w.index.to_frame(index=False))


def origins(panel: Panel, first: str, last: str) -> list[int]:
    return list(range(panel.pos(first), panel.pos(last) + 1))


def run(model, panel: Panel, first: str, last: str, ctx: dict) -> pd.DataFrame:
    """model(hist, t0, steps, ctx) -> массив ряды × steps. Возвращает длинную таблицу прогнозов."""
    n, total = panel.y.shape
    frames = []
    for t0 in origins(panel, first, last):
        steps = min(12, total - 1 - t0)
        hist = panel.y[:, : t0 + 1].copy()
        hist.setflags(write=False)
        yhat = np.asarray(model(hist, t0, steps, ctx), float)
        assert yhat.shape == (n, steps), (yhat.shape, (n, steps))
        for h in range(1, steps + 1):
            frames.append(pd.DataFrame({
                "row": np.arange(n), "origin": panel.periods[t0], "step": h,
                "target": panel.periods[t0 + h], "y": panel.y[:, t0 + h],
                "y_origin": panel.y[:, t0], "yhat": yhat[:, h - 1],
            }))
    return pd.concat(frames, ignore_index=True)
