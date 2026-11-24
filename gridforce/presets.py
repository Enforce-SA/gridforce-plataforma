"""Ficheiros de projeto (.json) da interface: conversão para ProjectConfig.

As chaves são os rótulos dos campos da aplicação, para que o mesmo ficheiro sirva para
preencher o formulário e para correr vários projetos de uma vez.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from .data.pvgis import MOUNTING_DEFAULT, MOUNTINGS
from .project import ProjectConfig, Variant


def _f(d, k, default):
    v = d.get(k, default)
    try:
        return default if v is None or (isinstance(v, float) and pd.isna(v)) else float(v)
    except (TypeError, ValueError):
        return default


CAPEX_MODES = ["Calculado por EUR/kWp e EUR/kWh", "Valor fixo por variante"]


def capex_mode(d: dict) -> str:
    """Como se calcula o capex do equipamento. Projetos antigos não têm este campo: se tiverem EUR/kWp ou EUR/kWh
    preenchidos usa-se o cálculo por EUR/kWp e EUR/kWh (o valor fixo antigo deixa de mandar sem se ver), exceto se o
    cálculo der mais de 10 vezes o valor fixo (sinal de que o preço unitário foi mal preenchido)."""
    m = d.get("Modo do capex")
    if m in CAPEX_MODES:
        return m
    rows = [r for r in d.get("Variantes", []) if r.get("Variante")]
    fixed = [r for r in rows if r.get("Capex total (EUR)") not in (None, "")]
    if not fixed:
        return CAPEX_MODES[0]
    pv, bt = _f(d, "Capex PV (EUR/kWp)", 0.0), _f(d, "Capex bateria (EUR/kWh)", 0.0)
    if pv <= 0 and bt <= 0:
        return CAPEX_MODES[1]
    for r in fixed:
        calc = _f(r, "PV (kWp)", 0.0) * pv + _f(r, "BESS (kWh)", 0.0) * bt
        if calc > 10 * max(_f(r, "Capex total (EUR)", 0.0), 1.0):
            return CAPEX_MODES[1]
    return CAPEX_MODES[0]


def config_from_dict(d: dict) -> ProjectConfig:
    p_end = dt.date.fromisoformat(d.get("Preços OMIE: últimos 12 meses até", "2026-09-30"))
    soc = d.get("Janela de SOC (%)", [5, 95])
    lvl = d.get("Nível de tensão", "MT")
    load_mode = d.get("Consumo do local", "Perfil tipo de centro comercial")
    variants = []
    fixed_mode = capex_mode(d) == CAPEX_MODES[1]
    for r in d.get("Variantes", []):
        if not r.get("Variante"):
            continue
        cap = r.get("Capex total (EUR)")
        variants.append(Variant(str(r["Variante"]), _f(r, "PV (kWp)", 0.0), _f(r, "BESS (kWh)", 0.0),
                                _f(r, "BESS (kW)", 0.0), capex_eur=None if (cap in (None, "") or not fixed_mode) else float(cap)))
    return ProjectConfig(
        name=d.get("Nome do projeto", "Projeto"), scenario=str(d.get("Cenário", "") or ""), lat=_f(d, "Latitude", 38.96), lon=_f(d, "Longitude", -9.33),
        load_kw=d.get("Diagrama de carga (kW)") if str(load_mode).startswith("Carregar") else None,
        annual_load_mwh=0.0 if load_mode.startswith("Sem consumo") else _f(d, "Consumo anual (MWh)", 4666.4),
        voltage_level=None if str(lvl).startswith("Sem") else lvl,
        import_limit_kw=_f(d, "Limite de importação (kW, 0 = sem limite)", 0.0) or 1e6,
        export_limit_kw=_f(d, "Limite de injeção na rede (kW, 0 = sem limite)", 0.0) or 1e6,
        extra_import_eur_mwh=_f(d, "Outros custos na compra (EUR/MWh)", 0.0),
        export_fee_eur_mwh=_f(d, "Comissão na venda (EUR/MWh)", 0.0),
        ppa_price_eur_mwh=_f(d, "Preço fixo no 1.º ano (EUR/MWh)", 45.9)
        if d.get("Venda da energia PV injetada") == "Preço fixo (PPA)" else None,
        ppa_escalation_eur_mwh_yr=_f(d, "Aumento anual do preço fixo (EUR/MWh por ano)", 0.0),
        other_capex_eur=_f(d, "Capex adicional (EUR)", 0.0),
        licensing_capex_eur=_f(d, "Licenciamento e ligação à rede (EUR)", 0.0),
        emission_factor_g_kwh=_f(d, "Fator de emissões da rede (g CO2/kWh)", 470.0), om_eur_yr=_f(d, "O&M no 1.º ano (EUR/ano)", 0.0),
        om_escalation_yr=_f(d, "Crescimento anual do O&M (%)", 2.0) / 100,
        insurance_eur_yr=_f(d, "Seguro no 1.º ano (EUR/ano)", 0.0),
        insurance_change_yr=_f(d, "Variação anual do seguro (% do valor inicial)", 0.0) / 100,
        pv_tilt=_f(d, "Inclinação (°)", 10.0), pv_azimuth=_f(d, "Azimute (°, 180 = sul)", 180.0),
        pv_mounting=d.get("Montagem PV") if d.get("Montagem PV") in MOUNTINGS else MOUNTING_DEFAULT,
        pv_loss_pct=_f(d, "Perdas do sistema (%)", 14.0), pv_dc_ac_ratio=_f(d, "Rácio DC/AC do inversor", 1.2),
        pv_degradation_yr=_f(d, "Degradação anual (%)", 0.5) / 100,
        pv_capex_eur_kwp=_f(d, "Capex PV (EUR/kWp)", 900.0), pv_opex_eur_kwp_yr=_f(d, "Opex PV (EUR/kWp/ano)", 0.0),
        bess_rte=_f(d, "Eficiência round-trip (%)", 88.0) / 100, bess_soc_min=soc[0] / 100, bess_soc_max=soc[1] / 100,
        bess_degradation_yr=_f(d, "Perda de capacidade anual (%)", 2.0) / 100,
        bess_wear_eur_mwh=_f(d, "Custo de desgaste (EUR/MWh descarregado)", 5.0),
        bess_max_cycles_day=_f(d, "Máximo de ciclos por dia (0 = sem limite)", 2.0) or None,
        bess_eta_charge=_f(d, "Eficiência de carga (%)", 0.0) / 100 or None,
        bess_eta_discharge=_f(d, "Eficiência de descarga (%)", 0.0) / 100 or None,
        bess_availability=_f(d, "Disponibilidade técnica (%)", 100.0) / 100,
        bess_aux_kw_per_mw=_f(d, "Consumos auxiliares (kW por MW)", 0.0),
        bess_deg_mode="ciclos" if str(d.get("Modelo de degradação", "")).startswith("Por ciclos") else "linear",
        bess_cal_fade_yr=_f(d, "Perda por calendário (%/ano)", 1.0) / 100,
        bess_cycle_fade_per_efc=_f(d, "Perda por ciclo equivalente (%)", 0.0033) / 100,
        bess_eol_pct=_f(d, "Fim de vida (%)", 70.0) / 100, bess_augment=bool(d.get("Augmentation", False)),
        bess_augment_eur_kwh=_f(d, "Custo da reposição (EUR/kWh)", 150.0),
        pcs_replace_year=int(_f(d, "Ano de substituição do PCS", 0)),
        pcs_replace_eur_kw=_f(d, "Custo da substituição do PCS (EUR/kW)", 0.0),
        bsp_fee_pct=_f(d, "Comissão do agregador/BSP (%)", 0.0) / 100,
        price_escalation_yr=_f(d, "Escalada anual dos preços (%)", 0.0) / 100,
        residual_value_pct=_f(d, "Valor residual (% do capex)", 0.0) / 100,
        bess_capex_eur_kwh=_f(d, "Capex bateria (EUR/kWh)", 509.05),
        bess_opex_eur_kwh_yr=_f(d, "Opex bateria (EUR/kWh/ano)", 0.0),
        arbitrage=bool(d.get("Arbitragem", True)), afrr=bool(d.get("aFRR", False)),
        afrr_act_rate=_f(d, "Taxa de ativação aFRR (%)", 10.0) / 100,
        afrr_duration_h=_f(d, "Duração mínima da reserva (h)", 1.0),
        afrr_acceptance=_f(d, "Ofertas aceites (%)", 100.0) / 100,
        afrr_cap_scale=_f(d, "Ajuste dos preços de capacidade aFRR (%)", 100.0) / 100,
        intraday=bool(d.get("Intradiário", False)),
        intraday_capture=_f(d, "Vantagem do intradiário capturada (%)", 25.0) / 100,
        mfrr=bool(d.get("mFRR", False)), mfrr_up_act_rate=_f(d, "Ativação mFRR a subir (%)", 40.0) / 100,
        mfrr_dn_act_rate=_f(d, "Ativação mFRR a descer (%)", 49.0) / 100,
        prices_start=(pd.Timestamp(p_end) - pd.DateOffset(years=1) + pd.Timedelta(days=1)).date(), prices_end=p_end,
        start_year=int(_f(d, "Ano de início", 2026)), years=int(_f(d, "Duração (anos)", 16)),
        discount_rate=_f(d, "Taxa de desconto (%)", 8.0) / 100, fast=bool(d.get("Modo rápido", True)),
        tax_rate=_f(d, "Imposto sobre lucros (%)", 0.0) / 100, dep_years=int(_f(d, "Amortização fiscal (anos)", 15)),
        debt_pct=_f(d, "Dívida (% do capex)", 0.0) / 100, debt_rate=_f(d, "Taxa de juro da dívida (%)", 5.0) / 100,
        debt_tenor=int(_f(d, "Prazo da dívida (anos)", 10)),
        debt_kind="constante" if str(d.get("Reembolso", "")).startswith("Amort") else "anuidade",
        min_dscr=_f(d, "DSCR mínimo", 0.0) or None, equity_rate=_f(d, "Custo do capital próprio (%)", 10.0) / 100,
        horizon_days=1 if str(d.get("Horizonte do despacho", "Semana")).startswith("Dia") else 7,
        variants=variants)


def park_and_scenario(d_or_name, scenario: str | None = None) -> tuple[str, str]:
    """Parque e cenário de um projeto. Usa o campo "Cenário" se existir; senão o texto entre parênteses
    no fim do nome (ex.: "Lousal (Investment Grade)" -> "Lousal", "Investment Grade")."""
    name = d_or_name.get("Nome do projeto", "Projeto") if isinstance(d_or_name, dict) else str(d_or_name)
    if scenario is None and isinstance(d_or_name, dict):
        scenario = d_or_name.get("Cenário")
    scenario = (scenario or "").strip()
    park = name.strip()
    if park.endswith(")") and "(" in park:
        i = park.rfind("(")
        inner = park[i + 1:-1].strip()
        if not scenario or inner == scenario:
            park, scenario = park[:i].strip(), scenario or inner
    elif scenario and park.endswith(scenario):
        park = park[: -len(scenario)].strip(" -–_|")
    return park or name, scenario or "Base"


def portfolio_table(results: list) -> pd.DataFrame:
    rows = []
    for res in results:
        park, scen = park_and_scenario(res.config.name, getattr(res.config, "scenario", None))
        for r in res.variants:
            m = dict(r.metrics)
            rows.append({"Projeto": res.config.name, "Parque": park, "Cenário": scen, **m})
    return pd.DataFrame(rows)


def scenario_comparison(results: list) -> dict:
    """Cenários lado a lado: por parque (melhor variante de cada projeto) e totais por cenário.

    Os totais somam os cashflows dos parques ano a ano, por isso a TIR do cenário é a da carteira."""
    from .finance import irr
    rows, cfs = [], {}
    for res in results:
        if not res.variants:
            continue
        park, scen = park_and_scenario(res.config.name, getattr(res.config, "scenario", None))
        r = max(res.variants, key=lambda x: x.metrics["VAL (EUR)"])
        m = r.metrics
        rows.append({"Parque": park, "Cenário": scen, "Variante": r.variant.name, "Capex (EUR)": m["Capex (EUR)"],
                     "Ganho 1.º ano face à base (EUR)": m["Ganho 1.º ano face à base (EUR)"],
                     "EBITDA 1.º ano (EUR)": m["EBITDA 1.º ano (EUR)"], "VAL (EUR)": m["VAL (EUR)"], "TIR": m["TIR"],
                     "Emissões evitadas 1.º ano (t CO2)": m.get("Emissões evitadas 1.º ano (t CO2)"),
                     "_rate": res.config.discount_rate})
        cfs.setdefault(scen, []).append(r.cashflows)
    per = pd.DataFrame(rows)
    if per.empty:
        return {"per_park": per, "totals": per, "cashflows": pd.DataFrame()}
    tot = []
    cf_tot = {}
    for scen, g in per.groupby("Cenário", sort=False):
        cf = pd.concat(cfs[scen], axis=1).fillna(0.0).sum(axis=1).sort_index()
        cf_tot[scen] = cf
        tot.append({"Cenário": scen, "Parques": len(g), "Capex (EUR)": g["Capex (EUR)"].sum(),
                    "Ganho 1.º ano face à base (EUR)": g["Ganho 1.º ano face à base (EUR)"].sum(),
                    "EBITDA 1.º ano (EUR)": g["EBITDA 1.º ano (EUR)"].sum(), "VAL (EUR)": g["VAL (EUR)"].sum(),
                    "TIR": irr(cf.values), "Emissões evitadas 1.º ano (t CO2)": g["Emissões evitadas 1.º ano (t CO2)"].sum()})
    return {"per_park": per.drop(columns="_rate"), "totals": pd.DataFrame(tot), "cashflows": pd.DataFrame(cf_tot)}


def portfolio_excel(results: list, path_or_buffer) -> None:
    with pd.ExcelWriter(path_or_buffer) as xw:
        portfolio_table(results).to_excel(xw, sheet_name="Carteira", index=False)
        sc = scenario_comparison(results)
        if not sc["totals"].empty:
            sc["totals"].to_excel(xw, sheet_name="Cenários", index=False)
            sc["per_park"].pivot_table(index="Parque", columns="Cenário", values=["Capex (EUR)", "VAL (EUR)", "TIR"],
                                       aggfunc="first").to_excel(xw, sheet_name="Cenários por parque")
            sc["cashflows"].to_excel(xw, sheet_name="Cashflows por cenário")
        cfs = {}
        for res in results:
            for r in res.variants:
                cfs[f"{res.config.name} | {r.variant.name}"] = r.cashflows
        pd.DataFrame(cfs).to_excel(xw, sheet_name="Cashflows")
        rows = []
        for res in results:
            for r in res.variants:
                for y, s in r.yearly_streams.iterrows():
                    for k, val in s.items():
                        rows.append({"Projeto": res.config.name, "Variante": r.variant.name, "Ano": y,
                                     "Fonte de valor": k, "EUR": val})
        pd.DataFrame(rows).to_excel(xw, sheet_name="Fontes de valor", index=False)
