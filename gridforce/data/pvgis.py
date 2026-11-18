"""Perfil de produção PV a partir do PVGIS (JRC), em kW por kWp, 15 min."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import requests

URL = "https://re.jrc.ec.europa.eu/api/v5_2/seriescalc"


def pv_profile_per_kwp(lat: float, lon: float, tilt: float, azimuth_deg_north: float,
                       year: int = 2020, loss_pct: float = 14.0,
                       cache_dir: Path | str | None = None) -> pd.Series:
    """Produção horária de 1 kWp (kW), interpolada para 15 min.

    azimuth_deg_north: convenção da GridCog (180 = sul). O PVGIS usa 0 = sul.
    O índice devolvido é um ano genérico em hora UTC; usa-se o perfil por
    posição (dia do ano, hora) para o aplicar a qualquer ano de simulação.
    """
    aspect = azimuth_deg_north - 180.0
    cache = None
    if cache_dir:
        cache = Path(cache_dir) / f"pvgis_{lat}_{lon}_{tilt}_{aspect}_{year}_{loss_pct}.csv"
        if cache.exists():
            s = pd.read_csv(cache, index_col=0).iloc[:, 0]
            s.index = pd.to_datetime(s.index, utc=True)
            return s
    params = dict(lat=lat, lon=lon, angle=tilt, aspect=aspect, startyear=year, endyear=year,
                  pvcalculation=1, peakpower=1, loss=loss_pct, outputformat="json")
    r = requests.get(URL, params=params, timeout=120)
    r.raise_for_status()
    hourly = r.json()["outputs"]["hourly"]
    idx = pd.to_datetime([h["time"] for h in hourly], format="%Y%m%d:%H%M", utc=True)
    # PVGIS marca a hora com o minuto do ponto médio (ex. 10:10); arredondamos à hora.
    s = pd.Series([h["P"] / 1000.0 for h in hourly], index=idx.floor("h"), name="pv_kw_per_kwp")
    s = s[~s.index.duplicated()]
    s15 = s.resample("15min").interpolate("linear").clip(lower=0)
    s15 = s15.reindex(pd.date_range(s.index[0], s.index[-1] + pd.Timedelta("45min"), freq="15min")).ffill()
    if cache is not None:
        s15.to_csv(cache)
    return s15


def map_to_index(profile: pd.Series, target_index: pd.DatetimeIndex) -> np.ndarray:
    """Aplica o perfil (por dia do ano e hora UTC) a outro índice temporal."""
    utc = target_index.tz_convert("UTC")
    key = profile.copy()
    key.index = [(t.dayofyear, t.hour, t.minute) for t in profile.index]
    lut = dict(zip(key.index, key.values))
    out = np.empty(len(utc))
    for i, t in enumerate(utc):
        doy = min(t.dayofyear, 365)
        out[i] = lut.get((doy, t.hour, t.minute), 0.0)
    return out
