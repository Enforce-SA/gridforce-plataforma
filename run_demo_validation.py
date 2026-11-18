"""Corre as 5 variantes do caso de demonstração GridCog (Shopping Centre) e
compara com os números do investment case recebido.

Uso:  python run_demo_validation.py [--afrr] [--sem-tarifas]
  --afrr         inclui aFRR (precisa de chave ENTSO-E; ver gridforce/data/entsoe.py)
  --sem-tarifas  ignora as tarifas de acesso ERSE (como o caso GridCog do agregador)
"""
from __future__ import annotations

import collections
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd

from gridforce.data.load import shopping_centre
from gridforce.data.omie import day_ahead_prices
from gridforce.data.pvgis import map_to_index, pv_profile_per_kwp
from gridforce.dispatch import Battery, Markets, Site, simulate_year
from gridforce.finance import Costs, annual_energy, annual_streams, investment_case
from gridforce.tariffs import TAR_2026, contracted_power_cost, import_adder_eur_mwh

HERE = Path(__file__).parent
CACHE = HERE / "cache"
DEMO = HERE.parent / "Demo_Portugal3yZzLQni-sim11-investment_case-Aggregator.xlsx"
OUT = HERE / "output"

LAT, LON, TILT, AZ = 38.96, -9.33, 10, 180
BASE_LOAD_MWH = 4666.4  # importação do cenário base da demonstração (s1, 2026)
START_YEAR = 2026
DC_AC_RATIO = 1.2       # relatório GridCog: 700 kW DC com inversor de 583,3 kW AC
VARIANTS = {  # chave da demo -> (PV kW, BESS kWh, BESS kW)
    "var-12": (1000, 2000, 1000),
    "var-16": (2000, 2000, 1000),
    "var-19": (5000, 1000, 500),
    "var-20": (5000, 2000, 1000),
    "var-24": (700, 2000, 1000),
}


def demo_numbers() -> pd.DataFrame:
    wb = openpyxl.load_workbook(DEMO, read_only=True, data_only=True)
    cash = collections.defaultdict(float)
    for r in wb["Raw Cashflows"].iter_rows(min_row=2, values_only=True):
        if r[1] != START_YEAR:
            continue
        v = r[0].split("_")[-1]
        item = r[9]
        if "Wholesale Import" in item:
            key = "Mercado diário - compra (import)"
        elif "Wholesale Export" in item:
            key = "Mercado diário - venda (export)"
        elif item.startswith("Activation aFRR Up"):
            key = "aFRR subir - ativação"
        elif item.startswith("Activation aFRR Down"):
            key = "aFRR descer - ativação"
        elif item.startswith("aFRR Up"):
            key = "aFRR subir - capacidade"
        else:
            key = "aFRR descer - capacidade"
        cash[(v, key)] += r[16] or 0
    flows = collections.defaultdict(float)
    for r in wb["Raw Ordered Flows"].iter_rows(min_row=2, values_only=True):
        if r[1] != START_YEAR or not r[0].startswith("s4"):
            continue
        v = r[0].split("_")[-1]
        src, dst, mwh = r[7], r[9], r[11]
        if src == "Grid":
            flows[(v, "Importação (MWh)")] += mwh
        if dst == "Grid":
            flows[(v, "Exportação (MWh)")] += mwh
        if src == "Solar" and r[8] is None:
            flows[(v, "PV disponível (MWh)")] += mwh
        if src == "Solar" and dst == "Excess":
            flows[(v, "PV cortado (MWh)")] += mwh
        if r[10] in ("Battery To Baseload", "Battery To Grid"):
            flows[(v, "Descarga bateria (MWh)")] += mwh
    rows = {}
    for (v, k), val in list(cash.items()) + list(flows.items()):
        rows.setdefault(v, {})[k] = val
    return pd.DataFrame(rows).T


def main(with_afrr: bool, with_tariffs: bool = True):
    OUT.mkdir(exist_ok=True)
    da = day_ahead_prices(dt.date(2025, 10, 1), dt.date(2026, 9, 30), cache_dir=CACHE)
    idx = da.index
    pv1 = map_to_index(pv_profile_per_kwp(LAT, LON, TILT, AZ, cache_dir=CACHE), idx)
    load = shopping_centre(idx, BASE_LOAD_MWH)
    afrr = None
    if with_afrr:
        from gridforce.data.entsoe import afrr_prices
        afrr = afrr_prices(idx, cache_dir=CACHE)
    mkt = Markets(day_ahead=da.values,
                  afrr_up_cap=None if afrr is None else afrr.up_cap.values,
                  afrr_dn_cap=None if afrr is None else afrr.dn_cap.values,
                  afrr_up_act_price=None if afrr is None else afrr.up_act.values,
                  afrr_dn_act_price=None if afrr is None else afrr.dn_act.values,
                  enable_afrr=afrr is not None)
    tar = TAR_2026["MT"]
    site = Site(import_adder_eur_mwh=import_adder_eur_mwh(idx, tar) if with_tariffs else 0.0)

    def streams(df):
        st = annual_streams(df, act_up=mkt.afrr_up_act_rate, act_dn=mkt.afrr_dn_act_rate)
        st["Tarifas de acesso - potência contratada"] = -contracted_power_cost(df.imp.values, tar) if with_tariffs else 0.0
        return st
    costs = Costs()

    base = simulate_year(idx, load, np.zeros_like(load), mkt, None, site)
    base_net = sum(streams(base.df).values())

    summary, year1, cash_rows = [], {}, []
    for key, (pv_kw, e_kwh, p_kw) in VARIANTS.items():
        yearly = []
        for y in range(costs.years):
            pv = np.minimum(pv1 * pv_kw * (1 - costs.pv_degradation_yr) ** y, pv_kw / DC_AC_RATIO)
            bat = Battery(e_kwh * (1 - costs.bess_degradation_yr) ** y, p_kw)
            res = simulate_year(idx, load, pv, mkt, bat, site)
            st = streams(res.df)
            yearly.append(st)
            for k, v in st.items():
                cash_rows.append({"Variante": key, "Ano": START_YEAR + y, "Fonte de valor": k, "EUR": v})
            if y == 0:
                year1[key] = {**st, **annual_energy(res.df)}
        net_vs_base = [sum(s.values()) - base_net for s in yearly]
        capex = pv_kw * costs.pv_capex_eur_kwp + e_kwh * costs.bess_capex_eur_kwh
        opex = pv_kw * costs.pv_opex_eur_kwp_yr + e_kwh * costs.bess_opex_eur_kwh_yr
        ic = investment_case(net_vs_base, capex, opex, costs.discount_rate, START_YEAR)
        summary.append({"Variante": key, "PV (kW)": pv_kw, "BESS (kWh)": e_kwh, "BESS (kW)": p_kw,
                        "Capex (EUR)": capex, "Opex (EUR/ano)": opex, "VAL (EUR)": ic["npv"],
                        "TIR": ic["irr"], "Payback (anos)": ic["payback_years"],
                        "Poupança 1.º ano vs base (EUR)": net_vs_base[0]})
        print(f"{key}: VAL {ic['npv']:,.0f} EUR, TIR {ic['irr']}, payback {ic['payback_years']}")

    ours = pd.DataFrame(year1).T
    demo = demo_numbers()
    comp = []
    for v in VARIANTS:
        for col in ["Importação (MWh)", "Exportação (MWh)", "PV disponível (MWh)", "PV cortado (MWh)",
                    "Descarga bateria (MWh)", "Mercado diário - compra (import)", "Mercado diário - venda (export)",
                    "aFRR subir - capacidade", "aFRR descer - capacidade", "aFRR subir - ativação", "aFRR descer - ativação"]:
            a, b = ours.loc[v].get(col, np.nan), demo.loc[v].get(col, np.nan) if v in demo.index else np.nan
            comp.append({"Variante": v, "Métrica (2026)": col, "GridForce": a, "GridCog (demo)": b,
                         "Diferença %": (a - b) / abs(b) * 100 if b and not np.isnan(b) else None})

    tag = "" if with_tariffs else "_sem_tarifas"
    path = OUT / f"validacao_demo_{dt.date.today():%Y%m%d}{tag}.xlsx"
    with pd.ExcelWriter(path) as xw:
        pd.DataFrame([{
            "Projeto": "Shopping Centre (réplica do caso de demonstração)",
            "Local": f"{LAT}N, {abs(LON)}W", "Período de preços": "OMIE PT 01/10/2025 a 30/09/2026",
            "Horizonte": f"{START_YEAR} a {START_YEAR + costs.years - 1}", "Taxa de desconto": costs.discount_rate,
            "Consumo anual (MWh)": BASE_LOAD_MWH, "aFRR incluído": bool(afrr is not None),
            "Tarifas de acesso": "ERSE MT, ciclo semanal (períodos 2027)" if with_tariffs else "não incluídas",
            "Custo base de energia (EUR/ano)": -base_net,
        }]).T.rename(columns={0: "Valor"}).to_excel(xw, sheet_name="Pressupostos")
        pd.DataFrame(summary).to_excel(xw, sheet_name="Resumo", index=False)
        pd.DataFrame(comp).to_excel(xw, sheet_name="Validação vs GridCog", index=False)
        pd.DataFrame(cash_rows).to_excel(xw, sheet_name="Cashflows brutos", index=False)
        ours.to_excel(xw, sheet_name="Energia e receitas 2026")
    print("Escrito:", path)


if __name__ == "__main__":
    main("--afrr" in sys.argv, "--sem-tarifas" not in sys.argv)
