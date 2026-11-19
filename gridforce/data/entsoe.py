"""Preços aFRR de Portugal a partir da ENTSO-E Transparency Platform.

Precisa de uma chave (security token) gratuita da ENTSO-E. Lida da variável
de ambiente ENTSOE_TOKEN; se não existir, assume que o ambiente injeta o
cabeçalho SECURITY_TOKEN nos pedidos a web-api.tp.entsoe.eu.

Documentos usados (área de controlo REN, 10YPT-REN------W):
  - A81 / B95 / processType A51: preço da capacidade aFRR contratada (EUR/MW/h)
  - A84 / processType A16 / businessType A96: preço da energia aFRR ativada (EUR/MWh)
"""
from __future__ import annotations

import datetime as dt
import io
import os
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd
import requests

API = "https://web-api.tp.entsoe.eu/api"
PT = "10YPT-REN------W"


def _get(params: dict) -> list[str]:
    """Devolve a lista de documentos XML (a API responde com um zip quando há vários)."""
    token = os.environ.get("ENTSOE_TOKEN")
    if not token:
        try:  # segredo do Streamlit Cloud
            import streamlit as st
            token = st.secrets.get("ENTSOE_TOKEN")
        except Exception:  # noqa: BLE001
            token = None
    if token:
        params = {**params, "securityToken": token}
    for attempt in range(4):  # o servidor da ENTSO-E falha com frequência (599, 503, tempo esgotado)
        try:
            r = requests.get(API, params=params, timeout=180)
        except (requests.ConnectionError, requests.Timeout):
            if attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code < 500 or attempt == 3:
            break
        time.sleep(5 * (attempt + 1))
    if r.status_code == 401:
        raise PermissionError("ENTSO-E: falta a chave (ENTSOE_TOKEN) ou é inválida")
    r.raise_for_status()
    if r.content[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            return [z.read(n).decode("utf-8") for n in z.namelist() if n.lower().endswith(".xml")]
    return [r.text]


def _get_split(params: dict, start: pd.Timestamp, end: pd.Timestamp) -> list[str]:
    """Pede [start, end); se a ENTSO-E recusar por excesso de documentos, divide o período ao meio."""
    fmt = "%Y%m%d%H%M"
    try:
        return _get({**params, "periodStart": start.strftime(fmt), "periodEnd": end.strftime(fmt)})
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 400 and "exceeds the allowed maximum" in e.response.text \
                and end - start > pd.Timedelta("1h"):
            mid = start + (end - start) / 2
            mid = mid.floor("h")
            return _get_split(params, start, mid) + _get_split(params, mid, end)
        if e.response is not None and e.response.status_code == 400 and "No matching data" in e.response.text:
            return []
        raise


def _weeks(start: pd.Timestamp, end: pd.Timestamp):
    m = start
    while m < end:
        m2 = min(m + pd.Timedelta(days=7), end)
        yield m, m2
        m = m2


def _parse_all(xmls: list[str]) -> pd.DataFrame:
    frames = [_parse(x) for x in xmls]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["start", "step", "direction", "price"])


def _parse(xml: str, amount_tags=("procurement_Price.amount", "activation_Price.amount", "price.amount")) -> pd.DataFrame:
    root = ET.fromstring(xml)
    if root.tag.endswith("Acknowledgement_MarketDocument"):  # sem dados para o período
        return pd.DataFrame(columns=["start", "step", "direction", "price"])
    ns = root.tag.split("}")[0] + "}" if root.tag.startswith("{") else ""
    rows = []
    for ts in root.iter(f"{ns}TimeSeries"):
        direction = ts.findtext(f"{ns}flowDirection.direction") or ""
        for period in ts.iter(f"{ns}Period"):
            start = pd.Timestamp(period.find(f"{ns}timeInterval").findtext(f"{ns}start"))
            res = period.findtext(f"{ns}resolution")
            step = pd.Timedelta(res.replace("PT", "").lower().replace("m", "min").replace("h", "h"))
            for pt in period.iter(f"{ns}Point"):
                pos = int(pt.findtext(f"{ns}position"))
                val = None
                for tag in amount_tags:
                    v = pt.findtext(f"{ns}{tag}")
                    if v is not None:
                        val = float(v)
                        break
                if val is not None:
                    rows.append((start + (pos - 1) * step, step, "up" if direction == "A01" else "down", val))
    return pd.DataFrame(rows, columns=["start", "step", "direction", "price"])


def _to_15min(df: pd.DataFrame, index: pd.DatetimeIndex) -> dict[str, pd.Series]:
    out = {}
    for d in ("up", "down"):
        sub = df[df.direction == d]
        if sub.empty:
            out[d] = pd.Series(0.0, index=index)
            continue
        s = pd.Series(sub.price.values, index=pd.DatetimeIndex(sub.start).tz_convert("UTC"))
        s = s.groupby(level=0).mean().sort_index()
        out[d] = s.reindex(index.tz_convert("UTC"), method="ffill").fillna(0.0).set_axis(index)
    return out


def afrr_prices(index: pd.DatetimeIndex, cache_dir: Path | str | None = None) -> pd.DataFrame:
    """Devolve colunas up_cap, dn_cap (EUR/MW/h) e up_act, dn_act (EUR/MWh) no índice dado."""
    start, end = index[0].tz_convert("UTC"), index[-1].tz_convert("UTC") + pd.Timedelta("15min")
    cache = Path(cache_dir) / f"entsoe_afrr_{start:%Y%m%d}_{end:%Y%m%d}.csv" if cache_dir else None
    if cache is not None and cache.exists():
        df = pd.read_csv(cache, index_col=0)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(index.tz)
        return df
    base = {"controlArea_Domain": PT}
    cap_p = {**base, "documentType": "A81", "businessType": "B95", "processType": "A51", "Type_MarketAgreement.Type": "A01"}
    act_p = {**base, "documentType": "A84", "processType": "A16", "businessType": "A96"}
    # a API é lenta (dezenas de segundos por semana): pedimos por semana e em paralelo
    chunks = list(_weeks(start, end))
    with ThreadPoolExecutor(max_workers=8) as ex:
        caps = list(ex.map(lambda w: _parse_all(_get_split(cap_p, *w)), chunks))
        acts = list(ex.map(lambda w: _parse_all(_get_split(act_p, *w)), chunks))
    cap = _to_15min(pd.concat(caps), index)
    act = _to_15min(pd.concat(acts), index)
    df = pd.DataFrame({"up_cap": cap["up"], "dn_cap": cap["down"], "up_act": act["up"], "dn_act": act["down"]}, index=index)
    if cache is not None:
        df.to_csv(cache)
    return df


def mfrr_prices(index: pd.DatetimeIndex, cache_dir: Path | str | None = None) -> pd.DataFrame:
    """Preços de ativação mFRR (EUR/MWh), colunas up_act e dn_act. Em Portugal não há pagamento
    de capacidade mFRR publicado; usa-se a média das ativações programadas (A60) e diretas (A61)."""
    start, end = index[0].tz_convert("UTC"), index[-1].tz_convert("UTC") + pd.Timedelta("15min")
    cache = Path(cache_dir) / f"entsoe_mfrr_{start:%Y%m%d}_{end:%Y%m%d}.csv" if cache_dir else None
    if cache is not None and cache.exists():
        df = pd.read_csv(cache, index_col=0)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(index.tz)
        return df
    def one(w, pt):
        try:
            return _parse_all(_get_split({"controlArea_Domain": PT, "documentType": "A84", "processType": pt}, *w))
        except requests.HTTPError:
            return pd.DataFrame(columns=["start", "step", "direction", "price"])
    chunks = list(_weeks(start, end))
    with ThreadPoolExecutor(max_workers=8) as ex:
        acts = list(ex.map(lambda a: one(*a), [(w, pt) for w in chunks for pt in ("A60", "A61")]))
    act = _to_15min(pd.concat(acts) if acts else pd.DataFrame(columns=["start", "step", "direction", "price"]), index)
    df = pd.DataFrame({"up_act": act["up"], "dn_act": act["down"]}, index=index)
    if cache is not None:
        df.to_csv(cache)
    return df
