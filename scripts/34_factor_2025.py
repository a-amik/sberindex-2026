"""Шаг 34. Общий фактор на 2025—2026 годы по России: три правила против факта.

Выбор модели фактора по 2025 году разрешён только из заранее названных
вариантов (ZADANIE 6.6, п. 4), без настройки параметров:

1. «перенос темпа» — тот же месяц год назад плюс средний годовой рост
   за три последних месяца (правило фактора панели и шага 17);
2. «темп из недельного ряда» — то же, но рост берётся из недельного
   годового прироста России за декабрь 2024 (шаг 30);
3. «макромодель» — правило 1 с поправкой, выученной на ошибке правила
   по ряду России 2018—2024 от ставки, реальной ставки, базовой инфляции
   и ускорения ФОТ (шаг 13, те же признаки и регуляризация), признаки на
   декабрь 2024.

Прогноз делается от декабря 2024 на 1…20 шагов по месячному ряду расходов
России (spend_bn) по категориям «Всего», «Продовольственные товары»,
«Общественное питание»; факт — тот же месячный ряд и недельный ряд.
Ошибка — в п.п. роста к тому же месяцу 2024 года.

    python scripts/34_factor_2025.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "results/forward_check"
T0, LAST = "2024-12", "2026-08"
WEEKLY = {"Всего": "Все категории ", "Продовольственные товары": "Продовольственные товары", "Общественное питание": "Общественное питание"}


def load13():
    spec = importlib.util.spec_from_file_location("f13", ROOT / "scripts/13_factor_model.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    f13 = load13()
    nat = pd.read_parquet(ROOT / "data/processed/national.parquet").set_index("period")
    sig = f13.signals(nat)
    feats = list(sig.columns)
    rows = []
    for k, wk in WEEKLY.items():
        col = f"spend_bn:{k}"
        s = np.log(nat[col].dropna())
        p = list(s.index)
        i = p.index(T0)
        g3 = np.mean([s.iloc[i - j] - s.iloc[i - j - 12] for j in range(3)])
        gw = np.log1p(nat.loc[T0, f"weekly_yoy:{wk}"] / 100)
        # макромодель: регрессия ошибки правила на признаки, обучение на целях ≤ T0
        e = f13.rule_errors(nat, col).merge(sig, left_on="origin", right_index=True).dropna()
        tr = e[e.target <= T0]
        X = np.c_[np.ones(len(tr)), tr[feats].to_numpy(), tr.step.to_numpy() / 12]
        mu, sd = X[:, 1:].mean(0), X[:, 1:].std(0) + 1e-9
        Z = np.c_[X[:, :1], (X[:, 1:] - mu) / sd]
        lam = 5.0 * len(tr) / 100
        beta = np.linalg.solve(Z.T @ Z + lam * np.diag([0] + [1] * (Z.shape[1] - 1)), Z.T @ tr.err.to_numpy())
        x0 = sig.loc[T0, feats].to_numpy(float)
        for h in range(1, 21):
            tgt = p[i + h] if i + h < len(p) else None
            if tgt is None or tgt > LAST:
                break
            base = s.iloc[i + h - 12] if h <= 12 else s.iloc[i + h - 24]
            yrs = 1 if h <= 12 else 2
            z = np.r_[1, (np.r_[x0, min(h, 12) / 12] - mu) / sd]
            pred_err = float(z @ beta)
            m = int(tgt[5:])
            fw = nat.loc[tgt, f"weekly_yoy:{wk}"] / 100
            fm = nat.loc[tgt, col] / nat.loc[f"2024-{m:02d}", col] - 1
            if yrs == 2:
                fw = (1 + nat.loc[f"2025-{m:02d}", f"weekly_yoy:{wk}"] / 100) * (1 + fw) - 1
            for name, lg in {"перенос темпа": g3 * yrs, "темп из недельного ряда": gw * yrs,
                             "макромодель": g3 * yrs - pred_err * yrs}.items():
                rows.append({"категория": k, "правило": name, "target": tgt, "год": tgt[:4], "шаг": h,
                             "прогноз_рост": np.exp(lg) - 1, "факт_мес": fm, "факт_нед": fw})
        print(k, "g3 =", round(g3 * 100, 1), "недельный =", round(gw * 100, 1), "коэффициенты:", dict(zip(["const"] + feats + ["h"], beta.round(3))))
    d = pd.DataFrame(rows)
    d["ош_мес"] = d.прогноз_рост - d.факт_мес
    d["ош_нед"] = d.прогноз_рост - d.факт_нед
    d.to_csv(OUT / "factor_rules_2025.csv", index=False)
    pd.set_option("display.width", 240)
    summ = d.groupby(["категория", "правило", "год"]).agg(месяцев=("шаг", "size"), смещ_мес=("ош_мес", "mean"), MAE_мес=("ош_мес", lambda x: x.abs().mean()),
                                                           смещ_нед=("ош_нед", "mean"), MAE_нед=("ош_нед", lambda x: x.abs().mean())).reset_index()
    for c in summ.columns[4:]:
        summ[c] = summ[c] * 100
    summ.to_csv(OUT / "factor_rules_2025_summary.csv", index=False)
    print(summ.round(1).to_string(index=False))
    v = d[d.категория == "Всего"].pivot_table(index="target", columns="правило", values="прогноз_рост") * 100
    v["факт_мес"] = d[(d.категория == "Всего") & (d.правило == "перенос темпа")].set_index("target").факт_мес * 100
    v["факт_нед"] = d[(d.категория == "Всего") & (d.правило == "перенос темпа")].set_index("target").факт_нед * 100
    print("\n«Всего», рост к тому же месяцу 2024, %:")
    print(v.round(1).to_string())


if __name__ == "__main__":
    main()
