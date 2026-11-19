"""Modelo de projeto e execução de uma simulação completa (todas as variantes).

É a camada que a interface web e os scripts usam: recebe a configuração do
projeto, prepara as séries (preços, PV, consumo, tarifas), corre o despacho
por variante e ano, e devolve métricas, cashflows e séries para gráficos.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

import numpy as np
import pandas as pd

from .data.load import shopping_centre
from .data.omie import day_ahead_prices
from .data.pvgis import map_to_index, pv_profile_per_kwp
from .dispatch import Battery, Markets, Site, simulate_year
from .finance import annual_energy, annual_streams, investment_case
from .tariffs import TAR_2026, contracted_power_cost, import_adder_eur_mwh

CACHE = Path(__file__).resolve().parent.parent / "cache"
ENGINE_VERSION = "GridForce 0.6 (2026-11-19)"


@dataclass
class Variant:
    name: str
    pv_kwp: float
    bess_kwh: float
    bess_kw: float
    capex_eur: float | None = None    # capex total da variante (substitui o cálculo por kWp/kWh)


@dataclass
class ProjectConfig:
    name: str = "Novo projeto"
    lat: float = 38.96
    lon: float = -9.33
    # consumo
    annual_load_mwh: float = 4666.4
    load_kw: np.ndarray | None = None         # série medida de 15 min (opcional, 1 ano)
    # ligação e tarifas
    voltage_level: str | None = "MT"          # MAT, AT, MT, BTE ou None (sem tarifas de acesso)
    import_limit_kw: float = 1e6
    export_limit_kw: float = 1e6
    extra_import_eur_mwh: float = 0.0         # margem do comercializador, CIEG, IEC...
    export_fee_eur_mwh: float = 0.0
    # venda da energia PV injetada a preço fixo (PPA); None = tudo a preço OMIE
    ppa_price_eur_mwh: float | None = None
    ppa_escalation_eur_mwh_yr: float = 0.0    # aumento linear por ano (ex.: 45,9 -> 46,8 -> ...)
    # PV
    pv_tilt: float = 10.0
    pv_azimuth: float = 180.0
    pv_loss_pct: float = 14.0
    pv_dc_ac_ratio: float = 1.2
    pv_degradation_yr: float = 0.005
    pv_capex_eur_kwp: float = 900.0
    pv_opex_eur_kwp_yr: float = 0.0
    # bateria
    bess_rte: float = 0.88
    bess_soc_min: float = 0.05
    bess_soc_max: float = 0.95
    bess_degradation_yr: float = 0.02
    bess_wear_eur_mwh: float = 5.0
    bess_max_cycles_day: float | None = None  # limite de ciclos completos por dia (média na janela)
    bess_capex_eur_kwh: float = 509.05
    bess_eta_charge: float | None = None      # eficiências separadas (ex.: 0,92/0,92); None = raiz da RTE
    bess_eta_discharge: float | None = None
    bess_availability: float = 1.0            # disponibilidade técnica (reduz potência e energia médias)
    bess_aux_kw_per_mw: float = 0.0           # consumos auxiliares (kW por MW de bateria), sempre ligados
    bess_opex_eur_kwh_yr: float = 0.0
    # custos do projeto (além dos custos por kWp/kWh)
    other_capex_eur: float = 0.0              # licenciamento, ligação à rede, etc.
    om_eur_yr: float = 0.0                    # O&M fixo no 1.º ano
    om_escalation_yr: float = 0.0             # crescimento composto anual do O&M
    insurance_eur_yr: float = 0.0             # seguro no 1.º ano
    insurance_change_yr: float = 0.0          # variação linear anual, em % do valor inicial (ex.: -0.0212)
    bsp_fee_pct: float = 0.0                  # comissão do agregador/BSP sobre receitas de serviços de sistema
    price_escalation_yr: float = 0.0          # escalada anual dos preços de mercado e tarifas (composta)
    residual_value_pct: float = 0.0           # valor residual no fim do projeto, em % do capex
    # mercados
    arbitrage: bool = True
    afrr: bool = False
    afrr_act_rate: float = 0.10
    afrr_duration_h: float = 1.0
    afrr_acceptance: float = 1.0              # fração das horas com oferta aceite (GridCog: 0,5)
    afrr_cap_scale: float = 1.0               # ajuste dos preços de capacidade aFRR (1 = ENTSO-E)
    intraday: bool = False                    # bateria também negoceia no intradiário contínuo
    intraday_capture: float = 0.25            # fração da vantagem do intradiário que se assume capturada
    mfrr: bool = False                        # reserva mFRR (só energia ativada)
    mfrr_up_act_rate: float = 0.40
    mfrr_dn_act_rate: float = 0.49
    mfrr_duration_h: float = 0.25
    prices_start: dt.date = dt.date(2025, 10, 1)
    prices_end: dt.date = dt.date(2026, 9, 30)
    # financeiro
    start_year: int = 2026
    years: int = 16
    discount_rate: float = 0.08
    fast: bool = True                         # simula 1.º e último ano e interpola os restantes
    variants: list[Variant] = field(default_factory=list)


@dataclass
class VariantResult:
    variant: Variant
    metrics: dict
    yearly_streams: pd.DataFrame          # ano x fonte de valor (EUR)
    cashflows: pd.Series                  # cashflow do projeto vs base (EUR)
    energy_y1: dict
    dispatch_y1: pd.DataFrame
    annual: pd.DataFrame | None = None    # receitas, opex, EBITDA, capex, valor residual, cashflow por ano


@dataclass
class ProjectResult:
    config: ProjectConfig
    baseline_streams: dict
    baseline_energy: dict
    variants: list[VariantResult]
    audit: dict | None = None


def _inputs(cfg: ProjectConfig):
    da = day_ahead_prices(cfg.prices_start, cfg.prices_end, cache_dir=CACHE)
    idx = da.index
    pv1 = map_to_index(pv_profile_per_kwp(cfg.lat, cfg.lon, cfg.pv_tilt, cfg.pv_azimuth,
                                          loss_pct=cfg.pv_loss_pct, cache_dir=CACHE), idx)
    if cfg.load_kw is not None:
        load = np.resize(np.asarray(cfg.load_kw, dtype=float), len(idx))
    elif cfg.annual_load_mwh <= 0:  # parque sem consumo (só produção e armazenamento)
        load = np.zeros(len(idx))
    else:
        load = shopping_centre(idx, cfg.annual_load_mwh)
    afrr = None
    if cfg.afrr:
        from .data.entsoe import afrr_prices
        afrr = afrr_prices(idx, cache_dir=CACHE)
    idp = None
    if cfg.intraday:
        from .data.omie import intraday_prices
        idp = intraday_prices(cfg.prices_start, cfg.prices_end, cache_dir=CACHE).reindex(idx).values
    mf = None
    if cfg.mfrr:
        from .data.entsoe import mfrr_prices
        mf = mfrr_prices(idx, cache_dir=CACHE)
    mkt = Markets(day_ahead=da.values,
                  intraday=idp, intraday_capture=cfg.intraday_capture,
                  mfrr_up_act_price=None if mf is None else mf.up_act.values * (1 - cfg.bsp_fee_pct),
                  mfrr_dn_act_price=None if mf is None else mf.dn_act.values,
                  mfrr_up_act_rate=cfg.mfrr_up_act_rate, mfrr_dn_act_rate=cfg.mfrr_dn_act_rate,
                  mfrr_duration_h=cfg.mfrr_duration_h, enable_mfrr=mf is not None,
                  afrr_up_cap=None if afrr is None else afrr.up_cap.values * cfg.afrr_cap_scale * (1 - cfg.bsp_fee_pct),
                  afrr_dn_cap=None if afrr is None else afrr.dn_cap.values * cfg.afrr_cap_scale * (1 - cfg.bsp_fee_pct),
                  afrr_up_act_price=None if afrr is None else afrr.up_act.values * (1 - cfg.bsp_fee_pct),
                  afrr_dn_act_price=None if afrr is None else afrr.dn_act.values,
                  afrr_up_act_rate=cfg.afrr_act_rate, afrr_dn_act_rate=cfg.afrr_act_rate,
                  afrr_acceptance=cfg.afrr_acceptance,
                  reserve_duration_h=cfg.afrr_duration_h,
                  enable_afrr=afrr is not None, enable_arbitrage=cfg.arbitrage)
    tar = TAR_2026.get(cfg.voltage_level) if cfg.voltage_level else None
    adder = (import_adder_eur_mwh(idx, tar) if tar else np.zeros(len(idx))) + cfg.extra_import_eur_mwh
    site = Site(import_limit_kw=cfg.import_limit_kw, export_limit_kw=cfg.export_limit_kw,
                import_adder_eur_mwh=adder, export_fee_eur_mwh=cfg.export_fee_eur_mwh,
                ppa_price_eur_mwh=cfg.ppa_price_eur_mwh)
    return idx, pv1, load, mkt, site, tar


def run_project(cfg: ProjectConfig, progress=None) -> ProjectResult:
    idx, pv1, load, mkt, site, tar = _inputs(cfg)

    def streams(df):
        st = annual_streams(df, export_fee=cfg.export_fee_eur_mwh,
                            act_up=mkt.afrr_up_act_rate, act_dn=mkt.afrr_dn_act_rate,
                            acceptance=mkt.afrr_acceptance)
        st["Tarifas de acesso - potência contratada"] = -contracted_power_cost(df.imp.values, tar) if tar else 0.0
        return st

    base = simulate_year(idx, load, np.zeros_like(load), mkt, None, site)
    base_st = streams(base.df)
    base_net = sum(base_st.values())

    results = []
    total_steps = len(cfg.variants) * (2 if cfg.fast else cfg.years)
    done = 0
    for v in cfg.variants:
        sim_years = [0, cfg.years - 1] if cfg.fast and cfg.years > 1 else list(range(cfg.years))
        per_year, d1 = {}, None
        for y in sim_years:
            pv = np.minimum(pv1 * v.pv_kwp * (1 - cfg.pv_degradation_yr) ** y, v.pv_kwp / cfg.pv_dc_ac_ratio)
            bat = None
            if v.bess_kwh > 0 and v.bess_kw > 0:
                av = cfg.bess_availability
                bat = Battery(v.bess_kwh * max(1 - cfg.bess_degradation_yr * y, 0.05) * av, v.bess_kw * av,
                              rte=cfg.bess_rte,  # perda de capacidade linear (como a GridCog)
                              soc_min=cfg.bess_soc_min, soc_max=cfg.bess_soc_max,
                              degradation_eur_mwh=cfg.bess_wear_eur_mwh,
                              max_cycles_per_day=cfg.bess_max_cycles_day or None,
                              eta_charge=cfg.bess_eta_charge, eta_discharge=cfg.bess_eta_discharge)
            site_y = site
            if cfg.ppa_price_eur_mwh is not None:
                site_y = replace(site, ppa_price_eur_mwh=cfg.ppa_price_eur_mwh + cfg.ppa_escalation_eur_mwh_yr * y)
            load_v = load + (cfg.bess_aux_kw_per_mw * v.bess_kw / 1000.0 if bat is not None else 0.0)
            res = simulate_year(idx, load_v, pv, mkt, bat, site_y)
            per_year[y] = streams(res.df)
            if y == 0:
                d1 = res.df
            done += 1
            if progress:
                progress(done / total_steps, f"{v.name}: ano {cfg.start_year + y}")
        ys = pd.DataFrame(per_year).T.sort_index()
        ys = ys.reindex(range(cfg.years)).interpolate(method="index")
        ys.index = [cfg.start_year + i for i in ys.index]
        esc = (1 + cfg.price_escalation_yr) ** np.arange(cfg.years)
        ppa_col = "Venda PV a preço fixo (PPA)"
        for c_ in ys.columns:
            if c_ != ppa_col:
                ys[c_] = ys[c_].values * esc
        net_vs_base = (ys.sum(axis=1).values - base_net * esc).tolist()
        capex = (v.capex_eur if v.capex_eur is not None
                 else v.pv_kwp * cfg.pv_capex_eur_kwp + v.bess_kwh * cfg.bess_capex_eur_kwh) + cfg.other_capex_eur
        yrs = np.arange(cfg.years)
        opex_y = (v.pv_kwp * cfg.pv_opex_eur_kwp_yr + v.bess_kwh * cfg.bess_opex_eur_kwh_yr
                  + cfg.om_eur_yr * (1 + cfg.om_escalation_yr) ** yrs
                  + np.maximum(cfg.insurance_eur_yr * (1 + cfg.insurance_change_yr * yrs), 0.0))
        opex = float(opex_y[0])
        residual = cfg.residual_value_pct * capex
        net_res = list(net_vs_base)
        net_res[-1] += residual
        ic = investment_case(net_res, capex, opex_y, cfg.discount_rate, cfg.start_year)
        yrs_lbl = [cfg.start_year + i for i in range(cfg.years)]
        annual = pd.DataFrame({
            "Receitas líquidas face à base": net_vs_base, "Opex": -opex_y,
            "EBITDA": np.array(net_vs_base) - opex_y, "Valor residual": [0.0] * (cfg.years - 1) + [residual],
        }, index=yrs_lbl)
        annual.loc[cfg.start_year - 1] = {"Receitas líquidas face à base": 0.0, "Opex": 0.0, "EBITDA": 0.0,
                                          "Valor residual": 0.0}
        annual = annual.sort_index()
        annual.insert(3, "Capex", [-capex] + [0.0] * cfg.years)
        annual["Cashflow"] = annual["EBITDA"] + annual["Capex"] + annual["Valor residual"]
        disc_f = 1 / (1 + cfg.discount_rate) ** np.arange(1, cfg.years + 1)
        e1 = annual_energy(d1)
        # energia descarregada (direta + ativações a subir) ao longo da vida, aproximada pelo 1.º ano
        # com a perda de capacidade linear
        fade = np.maximum(1 - cfg.bess_degradation_yr * np.arange(cfg.years), 0.05)
        dis1 = float((d1.dis + d1.rup * mkt.afrr_up_act_rate * mkt.afrr_acceptance
                      + d1.mup * mkt.mfrr_up_act_rate).sum() * 0.25 / 1000)
        pv1_mwh = e1["PV usado (MWh)"]
        pv_fade = (1 - cfg.pv_degradation_yr) ** np.arange(cfg.years)
        pv_opex_disc = float((opex_y * disc_f).sum())
        lcos = (capex + pv_opex_disc) / float((dis1 * fade * disc_f).sum()) if (v.bess_kwh and not v.pv_kwp and dis1) else None
        lcoe = (capex + pv_opex_disc) / float((pv1_mwh * pv_fade * disc_f).sum()) if (v.pv_kwp and pv1_mwh) else None
        metrics = {
            "Variante": v.name, "PV (kWp)": v.pv_kwp, "BESS (kWh)": v.bess_kwh, "BESS (kW)": v.bess_kw,
            "Capex (EUR)": capex, "Opex (EUR/ano)": opex, "VAL (EUR)": ic["npv"], "TIR": ic["irr"],
            "Payback (anos)": ic["payback_years"], "Ganho 1.º ano face à base (EUR)": net_vs_base[0],
            "Autoconsumo PV (%)": 100 * (e1["PV usado (MWh)"] - e1["Exportação (MWh)"]) / max(e1["PV disponível (MWh)"], 1e-9)
            if v.pv_kwp and e1["Consumo (MWh)"] > 0 else None,
            "Importação 1.º ano (MWh)": e1["Importação (MWh)"],
            "EBITDA 1.º ano (EUR)": float(annual.loc[cfg.start_year, "EBITDA"]),
            "Ganho 1.º ano por MW de bateria (EUR/MW)": net_vs_base[0] / (v.bess_kw / 1000) if v.bess_kw else None,
            "Ciclos por dia (1.º ano)": dis1 * 1000 / v.bess_kwh / 365 if v.bess_kwh else None,
            "LCOS (EUR/MWh descarregado)": lcos,
            "Custo nivelado do PV e bateria (EUR/MWh PV)": lcoe,
        }
        results.append(VariantResult(v, metrics, ys, ic["cashflows"], e1, d1, annual))
    return ProjectResult(cfg, base_st, annual_energy(base.df), results, audit=_audit(cfg, idx, mkt, results))


def _audit(cfg, idx, mkt, results) -> dict:
    """Informação para rastrear e validar a execução: versão, dados usados e verificações automáticas."""
    import hashlib

    def h(a):
        return hashlib.sha256(np.ascontiguousarray(np.nan_to_num(np.asarray(a, dtype=float))).tobytes()).hexdigest()[:16] \
            if a is not None else "-"
    out = {
        "Versão do motor": ENGINE_VERSION,
        "Data da execução": dt.datetime.now().isoformat(timespec="seconds"),
        "Período de preços": f"{cfg.prices_start} a {cfg.prices_end} ({len(idx)} intervalos de 15 min)",
        "Hash preços mercado diário": h(mkt.day_ahead),
        "Hash preços intradiário": h(mkt.intraday),
        "Hash preços aFRR capacidade subir": h(mkt.afrr_up_cap),
        "Hash preços mFRR ativação subir": h(mkt.mfrr_up_act_price),
        "Tarifas de acesso": f"ERSE TAR 2026, nível {cfg.voltage_level}" if cfg.voltage_level else "sem tarifas",
        "Previsão": "perfeita (limite superior económico), janelas de 7 dias",
    }
    for r in results:
        d = r.dispatch_y1
        bal = (d.pv + d.imp + d.dis - d.exp - d.xpv - d.ch - d.load).abs().max()
        out[f"Balanço de energia, maior erro (kW): {r.variant.name}"] = round(float(bal), 6)
        out[f"Limites respeitados: {r.variant.name}"] = bool(
            (d.imp <= cfg.import_limit_kw + 1e-6).all() and ((d.exp + d.xpv) <= cfg.export_limit_kw + 1e-6).all()
            and (d.pv <= d.pv_avail + 1e-6).all())
    return out


def to_excel(res: ProjectResult, path_or_buffer) -> None:
    cfg = asdict(res.config)
    cfg.pop("load_kw", None)
    cfg["variants"] = ", ".join(v.name for v in res.config.variants)
    with pd.ExcelWriter(path_or_buffer) as xw:
        pd.Series(cfg, name="Valor").to_frame().to_excel(xw, sheet_name="Pressupostos")
        pd.DataFrame([r.metrics for r in res.variants]).to_excel(xw, sheet_name="Resumo", index=False)
        rows = []
        for r in res.variants:
            for y, s in r.yearly_streams.iterrows():
                for k, val in s.items():
                    rows.append({"Variante": r.variant.name, "Ano": y, "Fonte de valor": k, "EUR": val})
        for k, val in res.baseline_streams.items():
            rows.append({"Variante": "Base (sem ativos)", "Ano": res.config.start_year, "Fonte de valor": k, "EUR": val})
        pd.DataFrame(rows).to_excel(xw, sheet_name="Cashflows por fonte", index=False)
        pd.DataFrame({r.variant.name: r.cashflows for r in res.variants}).to_excel(xw, sheet_name="Cashflows projeto")
        for r in res.variants:
            if r.annual is not None:
                r.annual.to_excel(xw, sheet_name=f"Anual {r.variant.name}"[:31])
        if res.audit:
            pd.Series(res.audit, name="Valor").to_frame().to_excel(xw, sheet_name="Auditoria")
        pd.DataFrame({"Base": res.baseline_energy, **{r.variant.name: r.energy_y1 for r in res.variants}}).to_excel(
            xw, sheet_name="Energia 1.º ano")
        for r in res.variants:
            d = r.dispatch_y1.copy()
            d.index = d.index.tz_localize(None)
            d.to_excel(xw, sheet_name=f"Despacho {r.variant.name}"[:31])
