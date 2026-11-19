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
    sell = df["sell"] if "sell" in df else df.da_price
    buy = df["buy"] if "buy" in df else df.da_price
    id_s = sell > df.da_price + 1e-9
    id_b = buy < df.da_price - 1e-9
    s = {
        "Mercado diário - venda (export)": float((df.exp * (sell - export_fee) * ~id_s).sum() * mwh),
        "Mercado diário - compra (import)": float(-(df.imp * buy * ~id_b).sum() * mwh),
        "Mercado intradiário - venda (export)": float((df.exp * (sell - export_fee) * id_s).sum() * mwh),
        "Mercado intradiário - compra (import)": float(-(df.imp * buy * id_b).sum() * mwh),
        "Venda PV a preço fixo (PPA)": float((df.xpv * (df.ppa_price - export_fee)).sum() * mwh) if "xpv" in df else 0.0,
        "Tarifas de acesso - energia e potência em ponta": float(-(df.imp * df.adder).sum() * mwh) if "adder" in df else 0.0,
        "aFRR subir - capacidade": float((df.rup * acceptance * df.up_cap).sum() * mwh),
        "aFRR descer - capacidade": float((df.rdn * acceptance * df.dn_cap).sum() * mwh),
        "aFRR subir - ativação": float((df.rup * acceptance * act_up * df.up_act).sum() * mwh),
        "aFRR descer - ativação": float(-(df.rdn * acceptance * act_dn * df.dn_act).sum() * mwh),
        "mFRR subir - ativação": float((df.mup * df.mfrr_a_up * df.m_up).sum() * mwh) if "mup" in df else 0.0,
        "mFRR descer - ativação": float(-(df.mdn * df.mfrr_a_dn * df.m_dn).sum() * mwh) if "mdn" in df else 0.0,
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
        "mFRR subir médio (MW)": float(df.mup.mean() / 1000) if "mup" in df else 0.0,
        "mFRR descer médio (MW)": float(df.mdn.mean() / 1000) if "mdn" in df else 0.0,
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


def debt_schedule(amount: float, rate: float, tenor: int, years: int, kind: str = "anuidade"):
    """Juros e amortização por ano (listas com `years` elementos)."""
    interest, principal = np.zeros(years), np.zeros(years)
    bal = amount
    tenor = max(1, min(int(tenor), years))
    pay = amount * rate / (1 - (1 + rate) ** -tenor) if rate > 0 else amount / tenor
    for t in range(tenor):
        interest[t] = bal * rate
        principal[t] = (pay - interest[t]) if kind == "anuidade" else amount / tenor
        bal -= principal[t]
    return interest, principal


def financing(ebitda: np.ndarray, capex: float, residual: float, discount_rate: float,
              debt_pct: float = 0.0, debt_rate: float = 0.05, debt_tenor: int = 10, debt_kind: str = "anuidade",
              min_dscr: float | None = None, tax_rate: float = 0.0, dep_years: int = 15,
              loss_cap: float = 0.65, equity_rate: float | None = None) -> dict:
    """Dívida, impostos e cashflow do acionista a partir do EBITDA anual (já com augmentation e substituições).

    - Dívida: percentagem do capex, a reembolsar em anuidade ou amortização constante. Se houver DSCR mínimo,
      a dívida é reduzida até o DSCR de cada ano (com anuidade) ficar acima desse mínimo.
    - Impostos: IRC + derrama sobre EBITDA - amortizações fiscais (lineares) - juros; prejuízos reportados
      sem limite de anos, a deduzir até `loss_cap` do lucro tributável de cada ano.
    - O valor residual entra no último ano, sem imposto."""
    ebitda = np.asarray(ebitda, dtype=float)
    n = len(ebitda)
    dep = np.array([capex / dep_years if t < dep_years else 0.0 for t in range(n)])

    def taxes(interest):
        tax, losses = np.zeros(n), 0.0
        for t in range(n):
            base = ebitda[t] - dep[t] - interest[t]
            if base <= 0:
                losses += -base
                continue
            use = min(losses, loss_cap * base)
            losses -= use
            tax[t] = tax_rate * (base - use)
        return tax

    debt = debt_pct * capex
    if debt > 0 and min_dscr:
        # anuidade por euro de dívida; CFADS aproximado sem o efeito fiscal dos juros (prudente)
        tenor = max(1, min(int(debt_tenor), n))
        cfads0 = ebitda - taxes(np.zeros(n))
        unit_i, unit_p = debt_schedule(1.0, debt_rate, tenor, n, debt_kind)
        ds_unit = (unit_i + unit_p)[:tenor]
        cap = float(np.min(cfads0[:tenor] / (min_dscr * ds_unit))) if np.all(ds_unit > 0) else debt
        debt = max(0.0, min(debt, cap))
    interest, principal = debt_schedule(debt, debt_rate, debt_tenor, n, debt_kind) if debt > 0 else (np.zeros(n), np.zeros(n))
    tax = taxes(interest)
    cfads = ebitda - tax
    ds = interest + principal
    dscr = np.where(ds > 0, cfads / np.where(ds > 0, ds, 1), np.nan)
    eq_cf = np.concatenate([[-(capex - debt)], cfads - ds])
    eq_cf[-1] += residual
    tax_unlev = taxes(np.zeros(n))
    proj_cf = np.concatenate([[-capex], ebitda - tax_unlev])
    proj_cf[-1] += residual
    er = discount_rate if equity_rate is None else equity_rate
    return {
        "debt": debt, "interest": interest, "principal": principal, "tax": tax, "cfads": cfads, "dscr": dscr,
        "equity_cf": eq_cf, "equity_irr": irr(eq_cf),
        "equity_npv": float((eq_cf / (1 + er) ** np.arange(n + 1)).sum()),
        "project_irr_after_tax": irr(proj_cf),
        "project_npv_after_tax": float((proj_cf / (1 + discount_rate) ** np.arange(n + 1)).sum()),
        "min_dscr": float(np.nanmin(dscr)) if np.isfinite(dscr).any() else None,
        "avg_dscr": float(np.nanmean(dscr)) if np.isfinite(dscr).any() else None,
    }
