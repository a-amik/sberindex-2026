"""Свёртка ансамбля — одна на бэктест (04_ensemble.py) и прогноз вперёд (17_forward.py).

До 07.10.2026 forward сводил модели своей веткой: geo для geo, иначе среднее, —
и выбранная в бэктесте медиана превращалась в среднее. Теперь способ свёртки
читается из ensemble_selection.csv и применяется здесь обоими скриптами.
"""
import numpy as np
import pandas as pd

HOW = ("mean", "median", "geo")


def combine_stack(stack: np.ndarray, how: str) -> np.ndarray:
    """stack — прогнозы членов по последней оси; NaN члена не рушит точку."""
    if how == "mean":
        return np.nanmean(stack, axis=-1)
    if how == "median":
        return np.nanmedian(stack, axis=-1)
    if how == "geo":
        return np.exp(np.nanmean(np.log(stack), axis=-1))
    raise ValueError(f"неизвестная свёртка: {how}")


def combine(frames: list[pd.DataFrame], how: str) -> pd.DataFrame:
    """Кадры бэктеста (row, origin, step, target, y, y_origin, yhat) → один кадр с yhat свёртки."""
    keys = ["row", "origin", "step"]
    frames = [f.sort_values(keys).reset_index(drop=True) for f in frames]
    base = frames[0][keys + ["target", "y", "y_origin"]].copy()
    base["yhat"] = combine_stack(np.column_stack([f.yhat.to_numpy() for f in frames]), how)
    return base


def selection(path) -> tuple[list[str], str]:
    """Выбранный состав и свёртка — первая строка ensemble_selection.csv."""
    sel = pd.read_csv(path).iloc[0]
    return sel.members.split("+"), str(sel.how)
