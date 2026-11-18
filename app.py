"""GridForce: interface web (Streamlit).

Correr localmente:  streamlit run app.py
"""
from __future__ import annotations

import datetime as dt
import io

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from gridforce.project import ProjectConfig, Variant, run_project, to_excel

st.set_page_config(page_title="GridForce", page_icon="⚡", layout="wide")

st.title("GridForce")
st.caption("Dimensionamento e simulação de PV e baterias em Portugal: autoconsumo, mercado diário OMIE e serviços de sistema.")

DEFAULT_VARIANTS = pd.DataFrame([
    {"Variante": "PV 700 kW + 2 MWh", "PV (kWp)": 700, "BESS (kWh)": 2000, "BESS (kW)": 1000},
    {"Variante": "PV 1 MW + 2 MWh", "PV (kWp)": 1000, "BESS (kWh)": 2000, "BESS (kW)": 1000},
    {"Variante": "PV 2 MW + 2 MWh", "PV (kWp)": 2000, "BESS (kWh)": 2000, "BESS (kW)": 1000},
    {"Variante": "Só PV 1 MW", "PV (kWp)": 1000, "BESS (kWh)": 0, "BESS (kW)": 0},
])

tab_site, tab_tech, tab_mkt, tab_var, tab_res = st.tabs(
    ["1. Local e consumo", "2. PV e bateria", "3. Mercados, tarifas e finanças", "4. Variantes", "5. Resultados"])

with tab_site:
    c1, c2 = st.columns(2)
    with c1:
        name = st.text_input("Nome do projeto", "Shopping Centre")
        lat = st.number_input("Latitude", value=38.96, format="%.4f")
        lon = st.number_input("Longitude", value=-9.33, format="%.4f")
    with c2:
        load_mode = st.radio("Consumo do local", ["Perfil tipo de centro comercial", "Carregar diagrama de carga (CSV)"])
        load_kw = None
        annual = st.number_input("Consumo anual (MWh)", value=4666.4, min_value=0.0,
                                 disabled=load_mode != "Perfil tipo de centro comercial")
        if load_mode != "Perfil tipo de centro comercial":
            f = st.file_uploader("CSV com uma coluna de potência em kW (35 040 linhas de 15 min ou 8 760 horárias)",
                                 type=["csv"])
            if f is not None:
                raw = pd.read_csv(f, sep=None, engine="python")
                col = raw.select_dtypes("number").columns[-1]
                vals = raw[col].to_numpy(float)
                if len(vals) in (8760, 8784):
                    vals = np.repeat(vals, 4)
                load_kw = vals
                st.success(f"{len(vals):,} intervalos, {vals.sum() * 0.25 / 1000:,.1f} MWh/ano, ponta {vals.max():,.0f} kW")
    c3, c4 = st.columns(2)
    with c3:
        imp_lim = st.number_input("Limite de importação (kW, 0 = sem limite)", value=0.0, min_value=0.0)
    with c4:
        exp_lim = st.number_input("Limite de injeção na rede (kW, 0 = sem limite)", value=0.0, min_value=0.0)

with tab_tech:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("PV")
        tilt = st.number_input("Inclinação (°)", value=10.0)
        az = st.number_input("Azimute (°, 180 = sul)", value=180.0)
        loss = st.number_input("Perdas do sistema (%)", value=14.0)
        dcac = st.number_input("Rácio DC/AC do inversor", value=1.2, min_value=0.5)
        pv_deg = st.number_input("Degradação anual (%)", value=0.5) / 100
        pv_capex = st.number_input("Capex PV (EUR/kWp)", value=900.0)
        pv_opex = st.number_input("Opex PV (EUR/kWp/ano)", value=0.0)
    with c2:
        st.subheader("Bateria")
        rte = st.number_input("Eficiência round-trip (%)", value=88.0) / 100
        soc_min, soc_max = st.slider("Janela de SOC (%)", 0, 100, (5, 95))
        b_deg = st.number_input("Perda de capacidade anual (%)", value=2.0) / 100
        wear = st.number_input("Custo de desgaste (EUR/MWh descarregado)", value=5.0)
        b_capex = st.number_input("Capex bateria (EUR/kWh)", value=509.05)
        b_opex = st.number_input("Opex bateria (EUR/kWh/ano)", value=0.0)

with tab_mkt:
    c1, c2, c3 = st.columns(3)
    with c1:
        st.subheader("Mercados")
        p_end = st.date_input("Preços OMIE: últimos 12 meses até", dt.date(2026, 9, 30))
        arbitrage = st.checkbox("Arbitragem no mercado diário (carregar da rede para vender)", True)
        afrr = st.checkbox("Banda de regulação secundária (aFRR)", False,
                           help="Precisa da chave ENTSO-E (variável ENTSOE_TOKEN).")
        act = st.number_input("Taxa de ativação aFRR (%)", value=10.0) / 100
        dur = st.number_input("Duração mínima da reserva (h)", value=1.0)
    with c2:
        st.subheader("Tarifas")
        lvl = st.selectbox("Nível de tensão (tarifa de acesso ERSE)", ["MT", "BTE", "AT", "MAT", "Sem tarifas de acesso"])
        extra = st.number_input("Outros custos na compra (EUR/MWh)", value=0.0,
                                help="Margem do comercializador, CIEG, imposto especial de consumo, etc.")
        fee = st.number_input("Comissão na venda (EUR/MWh)", value=0.0)
    with c3:
        st.subheader("Finanças")
        start_year = st.number_input("Ano de início", value=2026, step=1)
        years = st.number_input("Duração (anos)", value=16, step=1, min_value=1)
        disc = st.number_input("Taxa de desconto (%)", value=8.0) / 100
        fast = st.checkbox("Modo rápido (simula 1.º e último ano e interpola)", True)

with tab_var:
    st.write("Cada linha é uma variante a comparar. Adiciona ou apaga linhas à vontade.")
    variants_df = st.data_editor(DEFAULT_VARIANTS, num_rows="dynamic", use_container_width=True, key="variants")

run = st.button("Correr simulação", type="primary")

if run:
    vs = [Variant(str(r["Variante"]), float(r["PV (kWp)"] or 0), float(r["BESS (kWh)"] or 0), float(r["BESS (kW)"] or 0))
          for _, r in variants_df.dropna(subset=["Variante"]).iterrows()]
    cfg = ProjectConfig(
        name=name, lat=lat, lon=lon, annual_load_mwh=annual, load_kw=load_kw,
        voltage_level=None if lvl.startswith("Sem") else lvl,
        import_limit_kw=imp_lim or 1e6, export_limit_kw=exp_lim or 1e6,
        extra_import_eur_mwh=extra, export_fee_eur_mwh=fee,
        pv_tilt=tilt, pv_azimuth=az, pv_loss_pct=loss, pv_dc_ac_ratio=dcac, pv_degradation_yr=pv_deg,
        pv_capex_eur_kwp=pv_capex, pv_opex_eur_kwp_yr=pv_opex,
        bess_rte=rte, bess_soc_min=soc_min / 100, bess_soc_max=soc_max / 100, bess_degradation_yr=b_deg,
        bess_wear_eur_mwh=wear, bess_capex_eur_kwh=b_capex, bess_opex_eur_kwh_yr=b_opex,
        arbitrage=arbitrage, afrr=afrr, afrr_act_rate=act, afrr_duration_h=dur,
        prices_start=(pd.Timestamp(p_end) - pd.DateOffset(years=1) + pd.Timedelta(days=1)).date(), prices_end=p_end,
        start_year=int(start_year), years=int(years), discount_rate=disc, fast=fast, variants=vs)
    bar = st.progress(0.0, "A preparar dados de mercado e PV...")
    try:
        st.session_state["result"] = run_project(cfg, progress=lambda f, t: bar.progress(f, t))
        bar.progress(1.0, "Concluído")
    except Exception as e:  # noqa: BLE001
        bar.empty()
        st.error(f"A simulação falhou: {e}")

with tab_res:
    res = st.session_state.get("result")
    if res is None:
        st.info("Preenche os separadores 1 a 4 e carrega em **Correr simulação**.")
    else:
        summ = pd.DataFrame([r.metrics for r in res.variants])
        best = summ.loc[summ["VAL (EUR)"].idxmax()]
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Melhor variante (VAL)", best["Variante"])
        k2.metric("VAL", f"{best['VAL (EUR)']:,.0f} EUR")
        k3.metric("TIR", "n.d." if pd.isna(best["TIR"]) else f"{best['TIR'] * 100:.1f}%")
        k4.metric("Payback", "n.d." if pd.isna(best["Payback (anos)"]) else f"{best['Payback (anos)']:.1f} anos")

        st.subheader("Resumo das variantes")
        st.dataframe(summ.style.format({
            "PV (kWp)": "{:,.0f}", "BESS (kWh)": "{:,.0f}", "BESS (kW)": "{:,.0f}",
            "Capex (EUR)": "{:,.0f}", "Opex (EUR/ano)": "{:,.0f}", "VAL (EUR)": "{:,.0f}",
            "TIR": lambda x: "n.d." if pd.isna(x) else f"{x * 100:.1f}%",
            "Payback (anos)": lambda x: "n.d." if pd.isna(x) else f"{x:.1f}",
            "Poupança 1.º ano (EUR)": "{:,.0f}", "Autoconsumo PV (%)": lambda x: "" if pd.isna(x) else f"{x:.0f}%",
            "Importação 1.º ano (MWh)": "{:,.0f}"}), use_container_width=True, hide_index=True)

        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Value stack, 1.º ano, face à base")
            rows = []
            for r in res.variants:
                for k, v in r.yearly_streams.iloc[0].items():
                    delta = v - res.baseline_streams.get(k, 0.0)
                    if abs(delta) > 1:
                        rows.append({"Variante": r.variant.name, "Fonte de valor": k, "EUR": delta})
            fig = px.bar(pd.DataFrame(rows), x="Variante", y="EUR", color="Fonte de valor", barmode="relative")
            fig.update_layout(legend=dict(orientation="h", y=-0.3), height=460, margin=dict(t=10))
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            st.subheader("Cashflow descontado acumulado")
            fig = go.Figure()
            for r in res.variants:
                cf = r.cashflows
                disc_cf = cf / (1 + res.config.discount_rate) ** np.arange(len(cf))
                fig.add_trace(go.Scatter(x=cf.index, y=disc_cf.cumsum(), mode="lines", name=r.variant.name))
            fig.add_hline(y=0, line_dash="dot")
            fig.update_layout(height=460, margin=dict(t=10), yaxis_title="EUR", legend=dict(orientation="h", y=-0.2))
            st.plotly_chart(fig, use_container_width=True)

        st.subheader("Despacho num dia")
        c1, c2 = st.columns([1, 3])
        with c1:
            vname = st.selectbox("Variante", [r.variant.name for r in res.variants])
            r = next(x for x in res.variants if x.variant.name == vname)
            days = sorted({d.date() for d in r.dispatch_y1.index})
            day = st.select_slider("Dia", options=days, value=days[len(days) // 2])
        with c2:
            d = r.dispatch_y1[r.dispatch_y1.index.date == day]
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=d.index, y=d.load, name="Consumo", line=dict(color="black")))
            fig.add_trace(go.Bar(x=d.index, y=d.pv, name="PV usado"))
            fig.add_trace(go.Bar(x=d.index, y=d.dis - d.ch, name="Bateria (+descarga / -carga)"))
            fig.add_trace(go.Bar(x=d.index, y=d.imp - d.exp, name="Rede (+import / -export)"))
            if d.rup.sum() + d.rdn.sum() > 0:
                fig.add_trace(go.Scatter(x=d.index, y=d.rup, name="Reserva aFRR subir", line=dict(dash="dot")))
            fig.add_trace(go.Scatter(x=d.index, y=d.da_price, name="Preço OMIE (EUR/MWh)", yaxis="y2",
                                     line=dict(color="orange")))
            fig.update_layout(barmode="relative", height=420, margin=dict(t=10), yaxis_title="kW",
                              yaxis2=dict(overlaying="y", side="right", title="EUR/MWh"),
                              legend=dict(orientation="h", y=-0.2))
            st.plotly_chart(fig, use_container_width=True)

        st.subheader("Energia no 1.º ano")
        en = pd.DataFrame({"Base": res.baseline_energy, **{x.variant.name: x.energy_y1 for x in res.variants}})
        st.dataframe(en.style.format("{:,.1f}"), use_container_width=True)

        buf = io.BytesIO()
        to_excel(res, buf)
        st.download_button("Descarregar investment case (Excel)", buf.getvalue(),
                           file_name=f"{res.config.name}_investment_case.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
