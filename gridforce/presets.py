"""Ficheiros de projeto (.json) da interface: conversão para ProjectConfig.

As chaves são os rótulos dos campos da aplicação, para que o mesmo ficheiro sirva para
preencher o formulário e para correr vários projetos de uma vez.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from .project import ProjectConfig, Variant


def _f(d, k, default):
    v = d.get(k, default)
    try:
        return default if v is None or (isinstance(v, float) and pd.isna(v)) else float(v)
    except (TypeError, ValueError):
        return default


def config_from_dict(d: dict) -> ProjectConfig:
    p_end = dt.date.fromisoformat(d.get("Preços OMIE: últimos 12 meses até", "2026-09-30"))
    soc = d.get("Janela de SOC (%)", [5, 95])
    lvl = d.get("Nível de tensão", "MT")
    load_mode = d.get("Consumo do local", "Perfil tipo de centro comercial")
    variants = []
    for r in d.get("Variantes", []):
        if not r.get("Variante"):
            continue
        cap = r.get("Capex total (EUR)")
        variants.append(Variant(str(r["Variante"]), _f(r, "PV (kWp)", 0.0), _f(r, "BESS (kWh)", 0.0),
                                _f(r, "BESS (kW)", 0.0), capex_eur=None if cap in (None, "") else float(cap)))
    return ProjectConfig(
        name=d.get("Nome do projeto", "Projeto"), lat=_f(d, "Latitude", 38.96), lon=_f(d, "Longitude", -9.33),
        annual_load_mwh=0.0 if load_mode.startswith("Sem consumo") else _f(d, "Consumo anual (MWh)", 4666.4),
        voltage_level=None if str(lvl).startswith("Sem") else lvl,
        import_limit_kw=_f(d, "Limite de importação (kW, 0 = sem limite)", 0.0) or 1e6,
        export_limit_kw=_f(d, "Limite de injeção na rede (kW, 0 = sem limite)", 0.0) or 1e6,
        extra_import_eur_mwh=_f(d, "Outros custos na compra (EUR/MWh)", 0.0),
        export_fee_eur_mwh=_f(d, "Comissão na venda (EUR/MWh)", 0.0),
        ppa_price_eur_mwh=_f(d, "Preço fixo no 1.º ano (EUR/MWh)", 45.9)
        if d.get("Venda da energia PV injetada") == "Preço fixo (PPA)" else None,
        ppa_escalation_eur_mwh_yr=_f(d, "Aumento anual do preço fixo (EUR/MWh por ano)", 0.0),
        other_capex_eur=_f(d, "Capex adicional (EUR)", 0.0), om_eur_yr=_f(d, "O&M no 1.º ano (EUR/ano)", 0.0),
        om_escalation_yr=_f(d, "Crescimento anual do O&M (%)", 2.0) / 100,
        insurance_eur_yr=_f(d, "Seguro no 1.º ano (EUR/ano)", 0.0),
        insurance_change_yr=_f(d, "Variação anual do seguro (% do valor inicial)", 0.0) / 100,
        pv_tilt=_f(d, "Inclinação (°)", 10.0), pv_azimuth=_f(d, "Azimute (°, 180 = sul)", 180.0),
        pv_loss_pct=_f(d, "Perdas do sistema (%)", 14.0), pv_dc_ac_ratio=_f(d, "Rácio DC/AC do inversor", 1.2),
        pv_degradation_yr=_f(d, "Degradação anual (%)", 0.5) / 100,
        pv_capex_eur_kwp=_f(d, "Capex PV (EUR/kWp)", 900.0), pv_opex_eur_kwp_yr=_f(d, "Opex PV (EUR/kWp/ano)", 0.0),
        bess_rte=_f(d, "Eficiência round-trip (%)", 88.0) / 100, bess_soc_min=soc[0] / 100, bess_soc_max=soc[1] / 100,
        bess_degradation_yr=_f(d, "Perda de capacidade anual (%)", 2.0) / 100,
        bess_wear_eur_mwh=_f(d, "Custo de desgaste (EUR/MWh descarregado)", 5.0),
        bess_capex_eur_kwh=_f(d, "Capex bateria (EUR/kWh)", 509.05),
        bess_opex_eur_kwh_yr=_f(d, "Opex bateria (EUR/kWh/ano)", 0.0),
        arbitrage=bool(d.get("Arbitragem", True)), afrr=bool(d.get("aFRR", False)),
        afrr_act_rate=_f(d, "Taxa de ativação aFRR (%)", 10.0) / 100,
        afrr_duration_h=_f(d, "Duração mínima da reserva (h)", 1.0),
        afrr_acceptance=_f(d, "Ofertas aceites (%)", 100.0) / 100,
        intraday=bool(d.get("Intradiário", False)),
        intraday_capture=_f(d, "Vantagem do intradiário capturada (%)", 25.0) / 100,
        mfrr=bool(d.get("mFRR", False)), mfrr_up_act_rate=_f(d, "Ativação mFRR a subir (%)", 40.0) / 100,
        mfrr_dn_act_rate=_f(d, "Ativação mFRR a descer (%)", 49.0) / 100,
        prices_start=(pd.Timestamp(p_end) - pd.DateOffset(years=1) + pd.Timedelta(days=1)).date(), prices_end=p_end,
        start_year=int(_f(d, "Ano de início", 2026)), years=int(_f(d, "Duração (anos)", 16)),
        discount_rate=_f(d, "Taxa de desconto (%)", 8.0) / 100, fast=bool(d.get("Modo rápido", True)),
        variants=variants)


def portfolio_table(results: list) -> pd.DataFrame:
    rows = []
    for res in results:
        for r in res.variants:
            m = dict(r.metrics)
            rows.append({"Projeto": res.config.name, **m})
    return pd.DataFrame(rows)


def portfolio_excel(results: list, path_or_buffer) -> None:
    with pd.ExcelWriter(path_or_buffer) as xw:
        portfolio_table(results).to_excel(xw, sheet_name="Carteira", index=False)
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
