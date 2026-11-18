"""Perfis de consumo tipo, usados quando não há diagrama de carga medido."""
from __future__ import annotations

import numpy as np
import pandas as pd


def shopping_centre(index: pd.DatetimeIndex, annual_mwh: float) -> np.ndarray:
    """Perfil tipo de centro comercial (kW), escalado para annual_mwh.

    Pressupostos (a substituir por dados medidos quando existirem):
    - aberto todos os dias 09:00 a 23:00, base noturna de 35% da ponta;
    - rampas de 1 h na abertura e fecho;
    - climatização: +25% no pico do verão (julho/agosto) e +10% no inverno.
    """
    local = index.tz_convert("Europe/Lisbon")
    h = np.asarray(local.hour + local.minute / 60.0, dtype=float)
    open_frac = np.clip(np.minimum(h - 8.0, 23.0 - h), 0.0, 1.0)  # rampa 08-09 e 22-23
    base = 0.35 + 0.65 * open_frac
    doy = np.asarray(local.dayofyear, dtype=float)
    summer = np.exp(-((doy - 210) / 35.0) ** 2) * 0.25
    winter = (np.exp(-((doy - 15) / 30.0) ** 2) + np.exp(-((doy - 380) / 30.0) ** 2)) * 0.10
    hvac_daytime = 0.5 + 0.5 * open_frac
    shape = base * (1.0 + (summer + winter) * hvac_daytime)
    kwh = shape.sum() * 0.25
    return shape * (annual_mwh * 1000.0 / kwh)
