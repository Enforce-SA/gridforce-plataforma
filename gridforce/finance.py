"""Cashflows anuais, VAL, TIR e payback a partir dos resultados de despacho."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

DT = 0.25


@dataclass
class Costs:
    # Valores por omissão = os usados pela GridCog no caso de demonstração (relatório var-24)
    pv_capex_eur_kwp: float = 900.0
    bess_capex_eur_kwh: float = 509.05
    pv_opex_eur_kwp_yr: float = 0.0
    bess_opex_eur_kwh_yr: float = 0.0
    discount_rate: float = 0.08
    years: int = 16
    pv_degradation_yr: float = 0.005
    bess_degradation_yr: float = 0.02
    price_escalation_yr: float = 0.0


def annual_streams(df: pd.DataFrame, import_adder: float = 0.0, export_fee: float = 0.0,
                   act_up: float = 0.0, act_dn: float = 0.0, acceptance: float = 1.0) -> dict[str, float]:
    """Receitas (+) e custos (-) do ano, em EUR, por fonte de valor."""
    mwh = DT / 1000.0
    s = {
        "Mercado diário - venda (export)": float((df.exp * (df.da_price - export_fee)).sum() * mwh),
        "Venda PV a preço fixo (PPA)": float((df.xpv * (df.ppa_price - export_fee)).sum() * mwh) if "xpv" in df else 0.0,
        "Mercado diário - compra (import)": float(-(df.imp * df.da_price).sum() * mwh),
        "Tarifas de acesso - energia e potência em ponta": float(-(df.imp * df.adder).sum() * mwh) if "adder" in df else 0.0,
        "aFRR subir - capacidade": float((df.rup * acceptance * df.up_cap).sum() * mwh),
        "aFRR descer - capacidade": float((df.rdn * acceptance * df.dn_cap).sum() * mwh),
        "aFRR subir - ativação": float((df.rup * acceptance * act_up * df.up_act).sum() * mwh),
        "aFRR descer - ativação": float(-(df.rdn * acceptance * act_dn * df.dn_act).sum() * mwh),
    }
    return s


def annual_energy(df: pd.DataFrame) -> dict[str, float]:
    mwh = DT / 1000.0
    pv_to_load = np.minimum(df.pv, df.load)
    return {
        "Consumo (MWh)": float(df.load.sum() * mwh),
        "PV disponível (MWh)": float(df.pv_avail.sum() * mwh),
        "PV usado (MWh)": float(df.pv.sum() * mwh),
        "PV cortado (MWh)": float((df.pv_avail - df.pv).sum() * mwh),
        "PV direto para consumo (MWh)": float(pv_to_load.sum() * mwh),
        "Importação (MWh)": float(df.imp.sum() * mwh),
        "Exportação (MWh)": float((df.exp + (df.xpv if "xpv" in df else 0)).sum() * mwh),
        "Exportação PV a preço fixo (MWh)": float(df.xpv.sum() * mwh) if "xpv" in df else 0.0,
        "Carga bateria (MWh)": float(df.ch.sum() * mwh),
        "Descarga bateria (MWh)": float(df.dis.sum() * mwh),
        "aFRR subir médio (MW)": float(df.rup.mean() / 1000),
        "aFRR descer médio (MW)": float(df.rdn.mean() / 1000),
    }


def irr(cf: np.ndarray) -> float | None:
    lo, hi = -0.99, 1.0
    f = lambda r: np.sum(cf / (1 + r) ** np.arange(len(cf)))
    if f(lo) * f(hi) > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        if f(lo) * f(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def investment_case(yearly_net_vs_baseline: list[float], capex: float, opex_yr: float | list[float],
                    discount_rate: float, start_year: int) -> dict:
    """Cashflow do projeto face ao cenário base (sem ativos). Capex no ano 0.

    opex_yr pode ser um valor fixo ou uma lista com o opex de cada ano."""
    years = len(yearly_net_vs_baseline)
    opex = np.broadcast_to(np.asarray(opex_yr, dtype=float), (years,))
    cf = np.array([-capex] + [v - o for v, o in zip(yearly_net_vs_baseline, opex)])
    disc = cf / (1 + discount_rate) ** np.arange(years + 1)
    cum = np.cumsum(cf)
    payback = None
    for i in range(1, len(cum)):
        if cum[i] >= 0:
            prev = cum[i - 1]
            payback = i - 1 + (-prev) / (cum[i] - prev)
            break
    return {
        "cashflows": pd.Series(cf, index=[start_year - 1] + list(range(start_year, start_year + years))),
        "npv": float(disc.sum()),
        "irr": irr(cf),
        "payback_years": payback,
        "first_year_earnings": float(cf[1]),
    }
