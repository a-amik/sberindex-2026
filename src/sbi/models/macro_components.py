"""Разделение макросигналов без изменения общей модели поправки."""
import numpy as np

from sbi.models.regional_signals import RegionalContext, month


class MacroComponents(RegionalContext):
    def features(self, t, h):
        f = super().features(t, h)
        if "prices_cpi_total_m" in f:
            return f
        for column in list(f):
            if column.startswith("macro_cpi_"):
                f["prices_" + column.removeprefix("macro_")] = f[column]
            elif column.startswith("macro_wage_"):
                f["income_" + column.removeprefix("macro_")] = f[column]
            elif column.startswith("macro_key_rate"):
                f["rate_" + column.removeprefix("macro_")] = f[column]
        for name in ("total", "food", "nonfood", "services"):
            f[f"smooth_cpi_{name}_3"] = f[f"macro_cpi_{name}_3"]
        period = month(self.panel.periods[t], -self.settings["release_lags"]["wage"])
        growth = []
        for j in range(3):
            p = month(period, -j)
            growth.append(np.log(self._values(self.regional, "wage", p) /
                                 self._values(self.regional, "wage", month(p, -12))))
        f["smooth_wage_yoy"] = np.mean(growth, axis=0)
        f["smooth_wage_yoy_relative"] = self._relative(f.smooth_wage_yoy.to_numpy())
        f["smooth_key_rate"] = f.macro_key_rate
        f["smooth_key_rate_change3"] = f.macro_key_rate_change3
        self.feature_cache[t, h] = f
        return f
