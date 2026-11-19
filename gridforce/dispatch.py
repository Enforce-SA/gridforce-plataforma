"""Despacho ótimo PV + BESS + serviços de sistema, passo de 15 minutos.

Problema linear (LP) resolvido com HiGHS via scipy, por janelas de 7 dias
com previsão perfeita. A bateria pode co-otimizar:
  - autoconsumo do local;
  - arbitragem no mercado diário (compra/venda à rede);
  - reserva aFRR a subir e a descer (pagamento de capacidade + ativação esperada).

Convenções: potências em kW, energia em kWh, preços em EUR/MWh e EUR/MW/h.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import scipy.sparse as sp
from scipy.optimize import linprog

DT = 0.25  # h


@dataclass
class Battery:
    energy_kwh: float
    power_kw: float
    rte: float = 0.88              # eficiência round-trip
    soc_min: float = 0.05
    soc_max: float = 0.95
    soc_init: float = 0.5
    degradation_eur_mwh: float = 5.0   # custo de desgaste por MWh descarregado
    max_cycles_per_day: float | None = None

    @property
    def eta(self) -> float:
        return float(np.sqrt(self.rte))


@dataclass
class Site:
    import_limit_kw: float = 1e6
    export_limit_kw: float = 1e6
    import_adder_eur_mwh: float | np.ndarray = 0.0   # tarifas de acesso, taxas, margem (escalar ou série)
    export_fee_eur_mwh: float = 0.0     # comissão do agregador/representante
    # Preço fixo para a energia PV injetada diretamente (PPA / contrato de venda). Se definido,
    # a injeção PV direta é paga a este preço e a venda em mercado (OMIE) fica só para a bateria.
    ppa_price_eur_mwh: float | None = None


@dataclass
class Markets:
    """Séries de preço alinhadas com o índice da simulação."""
    day_ahead: np.ndarray                        # EUR/MWh
    afrr_up_cap: np.ndarray | None = None        # EUR/MW/h
    afrr_dn_cap: np.ndarray | None = None        # EUR/MW/h
    afrr_up_act_price: np.ndarray | None = None  # EUR/MWh recebidos pela energia ativada a subir
    afrr_dn_act_price: np.ndarray | None = None  # EUR/MWh pagos PELO agente pela energia ativada a descer (negativo = recebe)
    afrr_up_act_rate: float = 0.10               # fração da reserva a subir efetivamente ativada
    afrr_dn_act_rate: float = 0.10
    afrr_acceptance: float = 1.0                 # fração das horas em que a oferta de reserva é aceite
    reserve_duration_h: float = 1.0              # energia que tem de estar disponível para a reserva
    min_bid_kw: float = 0.0
    enable_afrr: bool = True
    # Mercado intradiário contínuo: a bateria compra/vende ao melhor de diário e intradiário,
    # capturando só uma fração da vantagem do intradiário (previsão perfeita sobrestima o ganho).
    intraday: np.ndarray | None = None           # EUR/MWh (NaN = sem negócio -> usa diário)
    intraday_capture: float = 0.5
    # mFRR (reserva de substituição manual): em Portugal só há pagamento da energia ativada
    mfrr_up_act_price: np.ndarray | None = None  # EUR/MWh recebidos a subir
    mfrr_dn_act_price: np.ndarray | None = None  # EUR/MWh pagos pelo agente a descer (negativo = recebe)
    mfrr_up_act_rate: float = 0.40
    mfrr_dn_act_rate: float = 0.49
    mfrr_duration_h: float = 0.25
    enable_mfrr: bool = False
    enable_arbitrage: bool = True                # permitir importar para vender (Grid -> Battery -> Grid)


@dataclass
class DispatchResult:
    df: pd.DataFrame
    objective_eur: float
    status: list[str] = field(default_factory=list)


def _solve_window(load, pv, mk: dict, bat: Battery | None, site: Site, soc0: float, mkt: Markets):
    n = len(load)
    has_bat = bat is not None and bat.energy_kwh > 0 and bat.power_kw > 0
    afrr = has_bat and mkt.enable_afrr and mkt.afrr_up_cap is not None
    mfrr = has_bat and mkt.enable_mfrr and mkt.mfrr_up_act_price is not None
    reserves = afrr or mfrr
    # variáveis: pv_used, imp, exp, ch, dis, soc, r_up, r_dn
    ppa = site.ppa_price_eur_mwh is not None
    names = (["pv", "imp", "exp"] + (["xpv"] if ppa else []) + (["ch", "dis", "soc"] if has_bat else [])
             + (["rup", "rdn"] if afrr else []) + (["mup", "mdn"] if mfrr else []))
    k = {nm: i for i, nm in enumerate(names)}
    nv = len(names) * n

    def col(nm, t):
        return k[nm] * n + t

    lb = np.zeros(nv)
    ub = np.full(nv, np.inf)
    ub[k["pv"] * n:(k["pv"] + 1) * n] = pv
    ub[k["imp"] * n:(k["imp"] + 1) * n] = site.import_limit_kw
    ub[k["exp"] * n:(k["exp"] + 1) * n] = site.export_limit_kw if (has_bat or not ppa) else 0.0
    if ppa:
        ub[k["xpv"] * n:(k["xpv"] + 1) * n] = np.minimum(pv, site.export_limit_kw)
    if has_bat:
        for nm in ("ch", "dis"):
            ub[k[nm] * n:(k[nm] + 1) * n] = bat.power_kw
        lb[k["soc"] * n:(k["soc"] + 1) * n] = bat.soc_min * bat.energy_kwh
        ub[k["soc"] * n:(k["soc"] + 1) * n] = bat.soc_max * bat.energy_kwh
    for nm in (("rup", "rdn") if afrr else ()) + (("mup", "mdn") if mfrr else ()):
        ub[k[nm] * n:(k[nm] + 1) * n] = bat.power_kw

    # custo (minimizar): kW * DT / 1000 = MWh
    c = np.zeros(nv)
    e = DT / 1000.0
    c[k["imp"] * n:(k["imp"] + 1) * n] = (mk["buy"] + mk["adder"]) * e
    c[k["exp"] * n:(k["exp"] + 1) * n] = -(mk["sell"] - site.export_fee_eur_mwh) * e
    c[k["pv"] * n:(k["pv"] + 1) * n] = -1e-6  # preferir usar PV a cortar
    if ppa:
        c[k["xpv"] * n:(k["xpv"] + 1) * n] = -(site.ppa_price_eur_mwh - site.export_fee_eur_mwh) * e
    if has_bat:
        c[k["dis"] * n:(k["dis"] + 1) * n] = bat.degradation_eur_mwh * e
    if afrr:
        acc = mkt.afrr_acceptance
        a_up, a_dn = mkt.afrr_up_act_rate * acc, mkt.afrr_dn_act_rate * acc
        c[k["rup"] * n:(k["rup"] + 1) * n] = -(acc * mk["up_cap"] * e + a_up * mk["up_act"] * e) + a_up * bat.degradation_eur_mwh * e
        c[k["rdn"] * n:(k["rdn"] + 1) * n] = -(acc * mk["dn_cap"] * e - a_dn * mk["dn_act"] * e)
    if mfrr:
        mu, md = mkt.mfrr_up_act_rate, mkt.mfrr_dn_act_rate
        c[k["mup"] * n:(k["mup"] + 1) * n] = -mu * mk["m_up"] * e + mu * bat.degradation_eur_mwh * e
        c[k["mdn"] * n:(k["mdn"] + 1) * n] = md * mk["m_dn"] * e

    rows, cols, vals = [], [], []
    b_eq = []
    r = 0
    # balanço: pv + imp + dis - exp - ch = load
    for t in range(n):
        for nm, s in (("pv", 1), ("imp", 1), ("exp", -1)) + ((("xpv", -1),) if ppa else ()) + (
                (("dis", 1), ("ch", -1)) if has_bat else ()):
            rows.append(r); cols.append(col(nm, t)); vals.append(s)
        b_eq.append(load[t]); r += 1
    if has_bat:
        eta = bat.eta
        a_up = mkt.afrr_up_act_rate * mkt.afrr_acceptance if afrr else 0
        a_dn = mkt.afrr_dn_act_rate * mkt.afrr_acceptance if afrr else 0
        for t in range(n):
            # soc_t - soc_{t-1} - eta*ch*DT + dis*DT/eta - a_dn*rdn*eta*DT + a_up*rup*DT/eta = 0
            rows += [r, r, r]; cols += [col("soc", t), col("ch", t), col("dis", t)]
            vals += [1, -eta * DT, DT / eta]
            if t > 0:
                rows.append(r); cols.append(col("soc", t - 1)); vals.append(-1); b_eq.append(0.0)
            else:
                b_eq.append(soc0)
            if afrr:
                rows += [r, r]; cols += [col("rdn", t), col("rup", t)]; vals += [-a_dn * eta * DT, a_up * DT / eta]
            if mfrr:
                rows += [r, r]; cols += [col("mdn", t), col("mup", t)]
                vals += [-mkt.mfrr_dn_act_rate * eta * DT, mkt.mfrr_up_act_rate * DT / eta]
            r += 1
        # SOC final = SOC inicial (evita esvaziar no fim da janela)
        rows.append(r); cols.append(col("soc", n - 1)); vals.append(1); b_eq.append(soc0); r += 1
    A_eq = sp.csr_matrix((vals, (rows, cols)), shape=(r, nv))

    rows, cols, vals, b_ub = [], [], [], []
    r = 0
    if ppa:
        for t in range(n):
            # injeção PV direta <= PV produzido; injeção total <= limite da ligação
            rows += [r, r]; cols += [col("xpv", t), col("pv", t)]; vals += [1, -1]; b_ub.append(0.0); r += 1
            rows += [r, r]; cols += [col("xpv", t), col("exp", t)]; vals += [1, 1]
            b_ub.append(site.export_limit_kw); r += 1
            if has_bat:
                # a venda em mercado vem só da bateria
                rows += [r, r]; cols += [col("exp", t), col("dis", t)]; vals += [1, -1]; b_ub.append(0.0); r += 1
    if has_bat:
        for t in range(n):
            # margem de potência: dis - ch + rup + mup <= P  e  ch - dis + rdn + mdn <= P
            if reserves:
                up = [n_ for n_ in ("rup", "mup") if n_ in k]
                dn = [n_ for n_ in ("rdn", "mdn") if n_ in k]
                rows += [r] * (2 + len(up)); cols += [col("dis", t), col("ch", t)] + [col(x, t) for x in up]
                vals += [1, -1] + [1] * len(up); b_ub.append(bat.power_kw); r += 1
                rows += [r] * (2 + len(dn)); cols += [col("ch", t), col("dis", t)] + [col(x, t) for x in dn]
                vals += [1, -1] + [1] * len(dn); b_ub.append(bat.power_kw); r += 1
            else:
                rows += [r, r]; cols += [col("ch", t), col("dis", t)]; vals += [1, 1]
                b_ub.append(bat.power_kw); r += 1
        if reserves:
            durs_up = ([("rup", mkt.reserve_duration_h)] if afrr else []) + ([("mup", mkt.mfrr_duration_h)] if mfrr else [])
            durs_dn = ([("rdn", mkt.reserve_duration_h)] if afrr else []) + ([("mdn", mkt.mfrr_duration_h)] if mfrr else [])
            for t in range(n):
                # energia para entregar a reserva a subir: sum(r*dur)/eta <= soc - soc_min
                rows += [r] * (len(durs_up) + 1); cols += [col(x, t) for x, _ in durs_up] + [col("soc", t)]
                vals += [d / bat.eta for _, d in durs_up] + [-1]
                b_ub.append(-bat.soc_min * bat.energy_kwh); r += 1
                # espaço para a reserva a descer: sum(r*dur)*eta <= soc_max - soc
                rows += [r] * (len(durs_dn) + 1); cols += [col(x, t) for x, _ in durs_dn] + [col("soc", t)]
                vals += [d * bat.eta for _, d in durs_dn] + [1]
                b_ub.append(bat.soc_max * bat.energy_kwh); r += 1
        if not mkt.enable_arbitrage:
            # a bateria só carrega com PV: ch <= pv_used
            for t in range(n):
                rows += [r, r]; cols += [col("ch", t), col("pv", t)]; vals += [1, -1]; b_ub.append(0.0); r += 1
        if bat.max_cycles_per_day:
            days = n * DT / 24
            for t in range(n):
                rows.append(r); cols.append(col("dis", t)); vals.append(DT)
            b_ub.append(bat.max_cycles_per_day * days * bat.energy_kwh * (bat.soc_max - bat.soc_min)); r += 1
    A_ub = sp.csr_matrix((vals, (rows, cols)), shape=(r, nv)) if r else None

    res = linprog(c, A_ub=A_ub, b_ub=np.array(b_ub) if r else None, A_eq=A_eq, b_eq=np.array(b_eq),
                  bounds=np.column_stack([lb, ub]), method="highs")
    if res.status != 0:
        raise RuntimeError(f"Otimização falhou: {res.message}")
    x = res.x
    out = {nm: x[k[nm] * n:(k[nm] + 1) * n] for nm in names}
    return out, res.fun, res.message


def simulate_year(index: pd.DatetimeIndex, load_kw: np.ndarray, pv_kw: np.ndarray, mkt: Markets,
                  bat: Battery | None, site: Site, window_days: int = 7) -> DispatchResult:
    n = len(index)
    step = window_days * 96
    zeros = np.zeros(n)
    series = dict(da=mkt.day_ahead,
                  up_cap=mkt.afrr_up_cap if mkt.afrr_up_cap is not None else zeros,
                  dn_cap=mkt.afrr_dn_cap if mkt.afrr_dn_cap is not None else zeros,
                  up_act=mkt.afrr_up_act_price if mkt.afrr_up_act_price is not None else zeros,
                  dn_act=mkt.afrr_dn_act_price if mkt.afrr_dn_act_price is not None else zeros,
                  adder=np.broadcast_to(np.asarray(site.import_adder_eur_mwh, dtype=float), (n,)).copy())
    da = np.asarray(mkt.day_ahead, dtype=float)
    if mkt.intraday is not None:
        idp = np.where(np.isnan(mkt.intraday), da, mkt.intraday)
        eff = da + mkt.intraday_capture * (idp - da)
    else:
        idp = eff = da
    series["id"] = idp
    series["sell"] = np.maximum(da, eff)
    series["buy"] = np.minimum(da, eff)
    series["m_up"] = np.clip(mkt.mfrr_up_act_price, -1000, 1000) if mkt.mfrr_up_act_price is not None else zeros
    series["m_dn"] = np.clip(mkt.mfrr_dn_act_price, -1000, 1000) if mkt.mfrr_dn_act_price is not None else zeros
    parts, total, msgs = [], 0.0, []
    soc = bat.soc_init * bat.energy_kwh if bat else 0.0
    for s in range(0, n, step):
        e = min(s + step, n)
        mk = {kk: v[s:e] for kk, v in series.items()}
        out, obj, msg = _solve_window(load_kw[s:e], pv_kw[s:e], mk, bat, site, soc, mkt)
        parts.append(pd.DataFrame(out, index=index[s:e]))
        total += obj
        msgs.append(msg)
    df = pd.concat(parts)
    df["load"] = load_kw
    df["pv_avail"] = pv_kw
    df["da_price"] = mkt.day_ahead
    for nm in ("up_cap", "dn_cap", "up_act", "dn_act", "adder", "sell", "buy", "m_up", "m_dn"):
        df[nm] = series[nm]
    df["id_price"] = series["id"]
    df["mfrr_a_up"] = mkt.mfrr_up_act_rate
    df["mfrr_a_dn"] = mkt.mfrr_dn_act_rate
    df["ppa_price"] = site.ppa_price_eur_mwh or 0.0
    for nm in ("xpv", "ch", "dis", "soc", "rup", "rdn", "mup", "mdn"):
        if nm not in df:
            df[nm] = 0.0
    return DispatchResult(df=df, objective_eur=-total, status=msgs)
