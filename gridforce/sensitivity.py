"""Sensibilidades e cenários de preços (Fase C).

As sensibilidades reaproveitam o cashflow já calculado: cada fonte de valor é escalada
sem voltar a otimizar o despacho. Com o despacho fixo, uma descida de preços fica um pouco
pior do que seria na realidade (a bateria adaptar-se-ia) e uma subida fica um pouco melhor
do que o calculado, por isso os resultados são ligeiramente conservadores nos dois sentidos.

Os cenários de preços históricos voltam a simular o 1.º ano com os preços de energia (OMIE diário
e intradiário) de cada ano histórico; os serviços de sistema mantêm os preços do caso base, porque a
ENTSO-E não tem séries completas e coerentes de Portugal para os anos antigos e sorteiam, para cada ano do projeto, um desses anos (Monte Carlo) para obter
P90 / P50 / P10 do VAL e da TIR (P90 = valor excedido em 90% dos casos).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import replace

import numpy as np
import pandas as pd

from .finance import irr

GROUPS = {
    "Preços de energia (diário e intradiário)": lambda c: c.startswith("Mercado"),
    "Preço do PPA": lambda c: c.startswith("Venda PV"),
    "Capacidade aFRR (saturação do mercado)": lambda c: c.startswith("aFRR") and "capacidade" in c,
    "Ativações aFRR e mFRR": lambda c: "ativação" in c,
}


def group_of(col: str) -> str | None:
    for g, f in GROUPS.items():
        if f(col):
            return g
    return None


def cashflow(parts: dict, factors: dict | None = None, capex_f: float = 1.0, opex_f: float = 1.0,
             delta: pd.DataFrame | None = None) -> np.ndarray:
    """Cashflow do projeto (ano 0 = capex) com as fontes de valor multiplicadas pelos fatores."""
    factors = factors or {}
    d = parts["delta"] if delta is None else delta
    mult = np.array([factors.get(group_of(c), 1.0) for c in d.columns])
    net = (d.values * mult).sum(axis=1)
    net[-1] += parts["residual"] * capex_f
    capex = parts["capex"] * capex_f
    cf = np.concatenate([[-capex], net - parts["opex_y"] * opex_f - parts["repl"]])
    return cf


def npv(cf: np.ndarray, rate: float) -> float:
    return float((cf / (1 + rate) ** np.arange(len(cf))).sum())


def tornado(parts: dict, pct: float = 0.2, capex_pct: float = 0.1) -> pd.DataFrame:
    """VAL e TIR com cada fator a descer e a subir, ordenado pelo impacto no VAL."""
    r = parts["discount_rate"]
    base_cf = cashflow(parts)
    base = npv(base_cf, r)
    d = parts["delta"]
    present = {group_of(c) for c in d.columns if abs(d[c].sum()) > 1}
    cases = [(f"Capex ±{capex_pct:.0%}", dict(capex_f=1 - capex_pct), dict(capex_f=1 + capex_pct)),
             (f"Opex ±{pct:.0%}", dict(opex_f=1 - pct), dict(opex_f=1 + pct))]
    for g in GROUPS:
        if g in present:
            cases.append((f"{g} ±{pct:.0%}", dict(factors={g: 1 - pct}), dict(factors={g: 1 + pct})))
    rows = []
    for name, lo, hi in cases:
        cf_lo, cf_hi = cashflow(parts, **lo), cashflow(parts, **hi)
        rows.append({"Fator": name,
                     "VAL com fator a descer (EUR)": npv(cf_lo, r), "VAL com fator a subir (EUR)": npv(cf_hi, r),
                     "TIR com fator a descer": irr(cf_lo), "TIR com fator a subir": irr(cf_hi)})
    t = pd.DataFrame(rows)
    t["Amplitude (EUR)"] = (t["VAL com fator a subir (EUR)"] - t["VAL com fator a descer (EUR)"]).abs()
    t = t.sort_values("Amplitude (EUR)", ascending=False).reset_index(drop=True)
    t.attrs["base_npv"] = base
    t.attrs["base_irr"] = irr(base_cf)
    return t


# ---------------------------------------------------------------- cenários de preços históricos

def historical_windows(cfg, n_years: int = 4) -> list[tuple[dt.date, dt.date]]:
    """Janelas de 12 meses que acabam no fim da janela de preços do projeto, recuando um ano de cada vez."""
    out = []
    s, e = cfg.prices_start, cfg.prices_end
    for k in range(n_years):
        try:
            out.append((s.replace(year=s.year - k), e.replace(year=e.year - k)))
        except ValueError:  # 29 de fevereiro
            out.append((s.replace(year=s.year - k, day=28), e.replace(year=e.year - k, day=28)))
    return out


def run_price_years(cfg, n_years: int = 4, progress=None) -> dict:
    """Simula o 1.º ano de cada variante com os preços de cada janela histórica.

    Devolve {janela: {variante: série das fontes de valor face à base (EUR, 1.º ano)}}
    e as mensagens de janelas que falharam (por exemplo, sem dados de serviços de sistema)."""
    from .project import run_project
    out, fails = {}, []
    wins = historical_windows(cfg, n_years)
    for i, (s, e) in enumerate(wins):
        label = f"{s:%m/%Y} a {e:%m/%Y}"
        if progress:
            progress(i / len(wins), f"Preços de {label}")
        c = replace(cfg, prices_start=s, prices_end=e, years=1, fast=True, bess_deg_mode="linear",
                    tax_rate=0.0, debt_pct=0.0, ancillary_window=(cfg.prices_start, cfg.prices_end))
        try:
            res = run_project(c)
        except Exception as ex:  # noqa: BLE001
            fails.append(f"{label}: {ex}")
            continue
        out[label] = {vr.variant.name: vr.parts["delta"].iloc[0] for vr in res.variants}
    if progress:
        progress(1.0, "Cenários concluídos")
    return {"years": out, "failed": fails}


def monte_carlo(parts: dict, variant: str, price_years: dict, n: int = 2000, seed: int = 1) -> dict:
    """Para cada ano do projeto sorteia um ano histórico de preços e aplica a sua relação com o 1.º ano
    do caso base (por fonte de valor), mantendo a degradação, escalada e custos do caso base."""
    d = parts["delta"]
    y1 = d.iloc[0]
    hist = [yrs[variant] for yrs in price_years["years"].values() if variant in yrs]
    if not hist:
        return {}
    # razão de cada ano histórico face ao 1.º ano do caso base, por fonte de valor
    ratios = []
    for h in hist:
        h = h.reindex(d.columns).fillna(0.0)
        ratios.append(np.where(np.abs(y1.values) > 1, h.values / np.where(np.abs(y1.values) > 1, y1.values, 1), 1.0))
    ratios = np.array(ratios)                                      # anos históricos x fontes
    # o PPA tem preço fixo: não muda com o ano de preços
    fixed = np.array([c.startswith("Venda PV") for c in d.columns])
    ratios[:, fixed] = 1.0
    rng = np.random.default_rng(seed)
    r = parts["discount_rate"]
    npvs, irrs = [], []
    for _ in range(n):
        pick = rng.integers(0, len(hist), size=len(d))
        dd = d.copy()
        dd.loc[:, :] = d.values * ratios[pick]
        cf = cashflow(parts, delta=dd)
        npvs.append(npv(cf, r))
        irrs.append(irr(cf))
    npvs = np.array(npvs)
    irrs = np.array([x if x is not None else np.nan for x in irrs])
    det = []
    for k, lbl in enumerate([l for l, yrs in price_years["years"].items() if variant in yrs]):
        dd = d.copy()
        dd.loc[:, :] = d.values * ratios[k]
        cf = cashflow(parts, delta=dd)
        det.append({"Preços": lbl, "Ganho 1.º ano face à base (EUR)": float((d.iloc[0].values * ratios[k]).sum()),
                    "VAL se todos os anos fossem assim (EUR)": npv(cf, r), "TIR": irr(cf)})
    # convenção do setor: P90 = valor excedido em 90% dos casos (percentil 10, o mais prudente)
    fin = np.isfinite(irrs).any()
    return {
        "P90 VAL (EUR)": float(np.percentile(npvs, 10)), "P50 VAL (EUR)": float(np.percentile(npvs, 50)),
        "P10 VAL (EUR)": float(np.percentile(npvs, 90)),
        "P90 TIR": float(np.nanpercentile(irrs, 10)) if fin else None,
        "P50 TIR": float(np.nanpercentile(irrs, 50)) if fin else None,
        "P10 TIR": float(np.nanpercentile(irrs, 90)) if fin else None,
        "por_ano": pd.DataFrame(det), "npvs": npvs,
    }
