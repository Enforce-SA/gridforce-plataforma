"""Preços do mercado diário OMIE para Portugal (ficheiros marginalpdbcpt).

Até 30/09/2025 o mercado diário tinha resolução horária (24 períodos);
desde 01/10/2025 tem resolução de 15 minutos (96 períodos). Devolvemos
sempre uma série de 15 minutos em hora local (Europe/Lisbon), em EUR/MWh.
"""
from __future__ import annotations

import datetime as dt
import io
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests

URL = "https://www.omie.es/es/file-download?parents=marginalpdbcpt&filename=marginalpdbcpt_{d:%Y%m%d}.1"


YEAR_ZIP = "https://www.omie.es/es/file-download?parents=marginalpdbcpt&filename=marginalpdbcpt_{y}.zip"
_year_cache: dict[int, dict[str, str]] = {}
_year_lock = threading.Lock()


def _parse_day(day: dt.date, text: str) -> list[tuple[dt.date, int, float]]:
    rows = []
    for line in text.splitlines():
        parts = line.strip().split(";")
        if len(parts) < 6 or not parts[0].isdigit():
            continue
        rows.append((day, int(parts[3]), float(parts[5])))  # coluna 5 = preço PT
    return rows


def _from_year_zip(day: dt.date) -> list[tuple[dt.date, int, float]]:
    """Os anos já fechados deixam de estar disponíveis dia a dia e passam para um zip anual."""
    with _year_lock:
        if day.year not in _year_cache:
            files = {}
            try:
                r = requests.get(YEAR_ZIP.format(y=day.year), timeout=120)
                if r.content[:2] == b"PK":
                    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                        files = {n: z.read(n).decode("latin-1") for n in z.namelist()}
            except requests.RequestException:
                pass
            _year_cache[day.year] = files
        files = _year_cache[day.year]
    for n, txt in files.items():
        if f"_{day:%Y%m%d}." in n:
            return _parse_day(day, txt)
    return []


def _fetch_day(day: dt.date, retries: int = 4) -> list[tuple[dt.date, int, float]] | None:
    for attempt in range(retries):
        try:
            r = requests.get(URL.format(d=day), timeout=30)
            if r.status_code >= 500:
                r.raise_for_status()
            rows = _parse_day(day, r.text) if r.ok else []
            if rows:
                return rows
            if r.status_code == 404 or r.text.lstrip().startswith("<"):  # página HTML: o ficheiro diário já não existe
                return _from_year_zip(day) or None
        except requests.RequestException:
            pass
        time.sleep(2 ** attempt)
    return None  # o chamador preenche o dia em falta com um dia vizinho


def _day_to_15min(day: dt.date, rows: list[tuple[dt.date, int, float]]) -> pd.Series:
    start = pd.Timestamp(day, tz="Europe/Lisbon")
    idx = pd.date_range(start, start + pd.Timedelta(days=1), freq="15min", inclusive="left")
    prices = [p for _, _, p in sorted(rows, key=lambda x: x[1])]
    n = len(idx)
    if len(prices) * 4 == n:            # horário -> repete cada hora 4 vezes
        vals = [p for p in prices for _ in range(4)]
    elif len(prices) == n:              # já em 15 min
        vals = prices
    else:                               # dia de mudança de hora com formato inesperado
        per = n / len(prices)
        vals = [prices[min(int(i / per), len(prices) - 1)] for i in range(n)]
    return pd.Series(vals, index=idx, name="omie_pt_eur_mwh")


def day_ahead_prices(start: dt.date, end: dt.date, cache_dir: Path | str | None = None) -> pd.Series:
    """Preços PT do mercado diário entre start e end (inclusive), 15 min."""
    cache = None
    if cache_dir:
        cache = Path(cache_dir) / f"omie_pt_{start:%Y%m%d}_{end:%Y%m%d}.csv"
        if cache.exists():
            s = pd.read_csv(cache, index_col=0).iloc[:, 0]
            s.index = pd.to_datetime(s.index, utc=True).tz_convert("Europe/Lisbon")
            return s
    days = [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(_fetch_day, days))
    missing = [d for d, r in zip(days, results) if not r]
    if len(missing) > 5:
        raise RuntimeError(f"OMIE: falhou o download de {len(missing)} dias (ex.: {missing[0]})")
    ok = [(d, r) for d, r in zip(days, results) if r]
    if not ok:
        raise RuntimeError("OMIE: sem dados para o período")
    filled = []
    for d, r in zip(days, results):
        if not r:  # usa o dia válido mais próximo (só os preços, a hora do dia mantém-se)
            r = min(ok, key=lambda x: abs((x[0] - d).days))[1]
        filled.append(_day_to_15min(d, r))
    s = pd.concat(filled)
    if cache is not None:
        s.to_csv(cache)
    return s


ID_URL = "https://www.omie.es/es/file-download?parents=precios_pibcic&filename=precios_pibcic_{d:%Y%m%d}.1"


def _num(x: str) -> float:
    return float(x.replace(".", "").replace(",", ".")) if x.strip() else 0.0


def _fetch_id_day(day: dt.date, retries: int = 4) -> pd.Series | None:
    """Preço médio ponderado do intradiário contínuo para PT num dia, em 15 min (NaN onde não houve
    negócios; sem negócios em PT usa-se o preço espanhol). Lê as colunas pelo cabeçalho, porque o
    formato mudou (colunas de Marrocos, períodos horários ou de 15 minutos)."""
    start_ts = pd.Timestamp(day, tz="Europe/Lisbon")
    idx = pd.date_range(start_ts, start_ts + pd.Timedelta(days=1), freq="15min", inclusive="left")
    for attempt in range(retries):
        try:
            r = requests.get(ID_URL.format(d=day), timeout=30)
            if r.status_code == 404:
                return pd.Series(float("nan"), index=idx)
            r.raise_for_status()
            lines = r.content.decode("latin-1").splitlines()
            hourly = "horas" in lines[0]
            head = next(l.split(";") for l in lines if l.startswith("A") and "Periodo" in l)
            col = {h.strip(): k for k, h in enumerate(head)}
            c_pt, c_es = col["MedioPT"], col["MedioES"]
            c_mx, c_mn = col["M\u00e1ximoPT"], col["M\u00ednimoPT"]
            prices = {}
            for line in lines:
                parts = line.strip().split(";")
                if len(parts) <= c_pt or not parts[0].strip().isdigit():
                    continue
                pt, es = _num(parts[c_pt]), _num(parts[c_es])
                traded_pt = not (pt == 0 and _num(parts[c_mx]) == 0 and _num(parts[c_mn]) == 0)
                prices[int(parts[3])] = pt if traded_pt else (es if es != 0 else float("nan"))
            n = len(idx)
            per = 4 if hourly else 1
            vals = [prices.get(min(t // per + 1, max(prices) if prices else 1), float("nan")) if hourly
                    else prices.get(t + 1, float("nan")) for t in range(n)]
            return pd.Series(vals, index=idx)
        except (requests.RequestException, KeyError, StopIteration):
            pass
        time.sleep(2 ** attempt)
    return pd.Series(float("nan"), index=idx)


def intraday_prices(start: dt.date, end: dt.date, cache_dir: Path | str | None = None) -> pd.Series:
    """Preço médio do intradiário contínuo (PT, ou ES quando não há negócios em PT), 15 min, EUR/MWh.
    Intervalos sem dados ficam NaN (quem usa substitui pelo preço do mercado diário)."""
    cache = None
    if cache_dir:
        cache = Path(cache_dir) / f"omie_id_pt_{start:%Y%m%d}_{end:%Y%m%d}.csv"
        if cache.exists():
            s = pd.read_csv(cache, index_col=0).iloc[:, 0]
            s.index = pd.to_datetime(s.index, utc=True).tz_convert("Europe/Lisbon")
            return s
    days = [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(_fetch_id_day, days))
    s = pd.concat(results).rename("omie_id_pt_eur_mwh")
    if cache is not None:
        s.to_csv(cache)
    return s
