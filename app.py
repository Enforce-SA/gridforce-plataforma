"""GridForce: interface web (Streamlit).

Correr localmente:  streamlit run app.py
"""
from __future__ import annotations

import datetime as dt
import io
import json

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import importlib

import gridforce.dispatch
import gridforce.finance
import gridforce.project
import gridforce.presets

# Recarregar o motor a cada execução: depois de uma atualização no GitHub o Streamlit Cloud
# pode manter a versão antiga dos módulos em memória.
for _m in (gridforce.dispatch, gridforce.finance, gridforce.project, gridforce.presets):
    importlib.reload(_m)
from gridforce.project import ProjectConfig, Variant, run_project, to_excel
from gridforce.presets import config_from_dict, portfolio_excel, portfolio_table

st.set_page_config(page_title="GridForce", page_icon="⚡", layout="wide")

# Identidade visual Enforce (Manual de Normas Gráficas, 02/07/2026):
# verde principal #AEC000, verde médio #5C8831, verde escuro #2B4D22, preto #000000
BRAND = {"primary": "#AEC000", "accent": "#5C8831", "dark": "#2B4D22", "bg": "#0B0F0A", "panel": "#151C13",
         "text": "#EEF2EA", "grid": "#25311F"}
SERIES = ["#AEC000", "#5C8831", "#E3EC8A", "#9AA79A", "#F2C14E", "#4FB3A5", "#D9DED5", "#E07A5F"]
px.defaults.template = "plotly_dark"
px.defaults.color_discrete_sequence = SERIES

st.markdown(f"""
<style>
  .stApp {{ background: radial-gradient(1100px 520px at 0% -10%, {BRAND['dark']} 0%, {BRAND['bg']} 58%); }}
  h1 {{ color: {BRAND['text']}; font-weight: 900; letter-spacing: .3px; }}
  h1 span.gf {{ color: {BRAND['primary']}; }}
  [data-testid="stMetric"] {{ background: {BRAND['panel']}; border: 1px solid {BRAND['dark']};
        border-left: 4px solid {BRAND['primary']}; border-radius: 10px; padding: 14px 18px; }}
  [data-testid="stMetricValue"] {{ color: {BRAND['primary']}; }}
  .stTabs [aria-selected="true"] {{ color: {BRAND['primary']} !important; }}
  .stButton > button[kind="primary"], .stDownloadButton > button {{ background: {BRAND['primary']}; border: 0; color: #000; font-weight: 700; }}
  .stButton > button[kind="primary"]:hover {{ background: {BRAND['accent']}; color: #fff; }}
</style>
""", unsafe_allow_html=True)


def _style(fig):
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", colorway=SERIES,
                      font=dict(color=BRAND["text"]))
    fig.update_xaxes(gridcolor=BRAND["grid"])
    fig.update_yaxes(gridcolor=BRAND["grid"])
    return fig

from pathlib import Path

_logo = Path(__file__).parent / "assets" / "enforce_logo.png"
if _logo.exists():
    st.image(str(_logo), width=220)
st.markdown('<h1>Grid<span class="gf">Force</span></h1>', unsafe_allow_html=True)
st.caption("Dimensionamento e simulação de PV e baterias em Portugal: autoconsumo, mercado diário OMIE e serviços de sistema.")

DEFAULT_VARIANTS = pd.DataFrame([
    {"Variante": "PV 700 kW + 2 MWh", "PV (kWp)": 700, "BESS (kWh)": 2000, "BESS (kW)": 1000, "Capex total (EUR)": None},
    {"Variante": "PV 1 MW + 2 MWh", "PV (kWp)": 1000, "BESS (kWh)": 2000, "BESS (kW)": 1000, "Capex total (EUR)": None},
    {"Variante": "PV 2 MW + 2 MWh", "PV (kWp)": 2000, "BESS (kWh)": 2000, "BESS (kW)": 1000, "Capex total (EUR)": None},
    {"Variante": "Só PV 1 MW", "PV (kWp)": 1000, "BESS (kWh)": 0, "BESS (kW)": 0, "Capex total (EUR)": None},
]).astype({"Capex total (EUR)": float})

LOAD_MODES = ["Perfil tipo de centro comercial", "Carregar diagrama de carga (CSV)",
              "Sem consumo (parque de produção e armazenamento)"]
LEVELS = ["MT", "BTE", "AT", "MAT", "Sem tarifas de acesso"]
SALES = ["Mercado diário OMIE", "Preço fixo (PPA)"]

with st.expander("Abrir projetos guardados (ficheiros .json)", expanded=False):
    ups = st.file_uploader("Ficheiros de projeto GridForce (pode escolher vários de uma vez)", type=["json"],
                           key="preset_files", accept_multiple_files=True)
    loaded = {}
    for u in ups or []:
        try:
            d = json.loads(u.getvalue().decode("utf-8"))
            loaded[d.get("Nome do projeto", u.name)] = (d, getattr(u, "file_id", u.name))
        except Exception as e:  # noqa: BLE001
            st.error(f"{u.name}: ficheiro inválido ({e})")
    if loaded:
        pick = st.selectbox("Projeto a mostrar nos separadores", list(loaded), key="preset_pick")
        st.session_state["preset"], st.session_state["preset_id"] = loaded[pick][0], f"{loaded[pick][1]}_{pick}"
        st.success(f"{len(loaded)} projeto(s) carregado(s). Os separadores mostram: {pick}.")
        if len(loaded) > 1 and st.button(f"Correr os {len(loaded)} projetos", type="primary"):
            bar = st.progress(0.0, "A preparar...")
            out = []
            for i, (nm, (d, _)) in enumerate(loaded.items()):
                try:
                    out.append(run_project(config_from_dict(d), progress=lambda f, t, i=i, nm=nm: bar.progress(
                        (i + f) / len(loaded), f"{nm}: {t}")))
                except Exception as e:  # noqa: BLE001
                    st.error(f"{nm}: a simulação falhou ({e})")
            bar.progress(1.0, "Concluído")
            st.session_state["portfolio"] = out
            st.info("Resultados no separador 5.")
PRESET = st.session_state.get("preset", {})
PRESET_ID = st.session_state.get("preset_id", "base")


def P(key, default):
    v = PRESET.get(key, default)
    if isinstance(default, float) and not isinstance(v, bool):
        try:
            return float(v)
        except (TypeError, ValueError):
            return default
    if isinstance(default, int) and not isinstance(default, bool):
        try:
            return int(v)
        except (TypeError, ValueError):
            return default
    return v


def _variants_default():
    if "Variantes" in PRESET:
        df = pd.DataFrame(PRESET["Variantes"])
    else:
        df = DEFAULT_VARIANTS.copy()
    for c in ("PV (kWp)", "BESS (kWh)", "BESS (kW)", "Capex total (EUR)"):
        if c not in df:
            df[c] = None
    return df.astype({"PV (kWp)": float, "BESS (kWh)": float, "BESS (kW)": float, "Capex total (EUR)": float})


tab_site, tab_tech, tab_mkt, tab_var, tab_res = st.tabs(
    ["1. Local e consumo", "2. PV e bateria", "3. Mercados, tarifas e finanças", "4. Variantes", "5. Resultados"])

with tab_site:
    c1, c2 = st.columns(2)
    with c1:
        name = st.text_input("Nome do projeto", P("Nome do projeto", "Shopping Centre"))
        lat = st.number_input("Latitude", value=P("Latitude", 38.96), format="%.4f")
        lon = st.number_input("Longitude", value=P("Longitude", -9.33), format="%.4f")
    with c2:
        load_mode = st.radio("Consumo do local", LOAD_MODES, index=LOAD_MODES.index(P("Consumo do local", LOAD_MODES[0])))
        load_kw = None
        annual = st.number_input("Consumo anual (MWh)", value=P("Consumo anual (MWh)", 4666.4), min_value=0.0,
                                 disabled=load_mode != "Perfil tipo de centro comercial")
        if load_mode.startswith("Sem consumo"):
            annual = 0.0
        elif load_mode != "Perfil tipo de centro comercial":
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
        imp_lim = st.number_input("Limite de importação (kW, 0 = sem limite)", value=P("Limite de importação (kW, 0 = sem limite)", 0.0), min_value=0.0)
    with c4:
        exp_lim = st.number_input("Limite de injeção na rede (kW, 0 = sem limite)", value=P("Limite de injeção na rede (kW, 0 = sem limite)", 0.0), min_value=0.0)

with tab_tech:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("PV")
        tilt = st.number_input("Inclinação (°)", value=P("Inclinação (°)", 10.0))
        az = st.number_input("Azimute (°, 180 = sul)", value=P("Azimute (°, 180 = sul)", 180.0))
        loss = st.number_input("Perdas do sistema (%)", value=P("Perdas do sistema (%)", 14.0))
        dcac = st.number_input("Rácio DC/AC do inversor", value=P("Rácio DC/AC do inversor", 1.2), min_value=0.5)
        pv_deg = st.number_input("Degradação anual (%)", value=P("Degradação anual (%)", 0.5)) / 100
        pv_capex = st.number_input("Capex PV (EUR/kWp)", value=P("Capex PV (EUR/kWp)", 900.0))
        pv_opex = st.number_input("Opex PV (EUR/kWp/ano)", value=P("Opex PV (EUR/kWp/ano)", 0.0))
    with c2:
        st.subheader("Bateria")
        rte = st.number_input("Eficiência round-trip (%)", value=P("Eficiência round-trip (%)", 88.0)) / 100
        soc_min, soc_max = st.slider("Janela de SOC (%)", 0, 100, tuple(P("Janela de SOC (%)", (5, 95))))
        b_deg = st.number_input("Perda de capacidade anual (%)", value=P("Perda de capacidade anual (%)", 2.0)) / 100
        wear = st.number_input("Custo de desgaste (EUR/MWh descarregado)", value=P("Custo de desgaste (EUR/MWh descarregado)", 5.0))
        b_capex = st.number_input("Capex bateria (EUR/kWh)", value=P("Capex bateria (EUR/kWh)", 509.05))
        b_opex = st.number_input("Opex bateria (EUR/kWh/ano)", value=P("Opex bateria (EUR/kWh/ano)", 0.0))

with tab_mkt:
    c1, c2, c3 = st.columns(3)
    with c1:
        st.subheader("Mercados")
        p_end = st.date_input("Preços OMIE: últimos 12 meses até", dt.date.fromisoformat(P("Preços OMIE: últimos 12 meses até", "2026-09-30")))
        arbitrage = st.checkbox("Arbitragem no mercado diário (carregar da rede para vender)", P("Arbitragem", True))
        afrr = st.checkbox("Banda de regulação secundária (aFRR)", P("aFRR", False),
                           help="Precisa da chave ENTSO-E (variável ENTSOE_TOKEN).")
        act = st.number_input("Taxa de ativação aFRR (%)", value=P("Taxa de ativação aFRR (%)", 10.0)) / 100
        dur = st.number_input("Duração mínima da reserva (h)", value=P("Duração mínima da reserva (h)", 1.0))
        acc = st.number_input("Ofertas aceites (%)", value=P("Ofertas aceites (%)", 100.0), min_value=0.0, max_value=100.0,
                              help="Percentagem das horas em que a oferta de reserva é aceite. A GridCog usa 50%.") / 100
    with c2:
        st.subheader("Tarifas")
        lvl = st.selectbox("Nível de tensão (tarifa de acesso ERSE)", LEVELS, index=LEVELS.index(P("Nível de tensão", "MT")))
        extra = st.number_input("Outros custos na compra (EUR/MWh)", value=P("Outros custos na compra (EUR/MWh)", 0.0),
                                help="Margem do comercializador, CIEG, imposto especial de consumo, etc.")
        fee = st.number_input("Comissão na venda (EUR/MWh)", value=P("Comissão na venda (EUR/MWh)", 0.0))
        sale = st.radio("Venda da energia PV injetada", SALES, index=SALES.index(P("Venda da energia PV injetada", SALES[0])),
                        help="Com preço fixo, a energia PV injetada diretamente é paga a esse preço; a bateria "
                             "continua a vender no mercado.")
        ppa = st.number_input("Preço fixo no 1.º ano (EUR/MWh)", value=P("Preço fixo no 1.º ano (EUR/MWh)", 45.9), disabled=sale != "Preço fixo (PPA)")
        ppa_esc = st.number_input("Aumento anual do preço fixo (EUR/MWh por ano)", value=P("Aumento anual do preço fixo (EUR/MWh por ano)", 0.9),
                                  disabled=sale != "Preço fixo (PPA)")
    with c3:
        st.subheader("Finanças")
        start_year = st.number_input("Ano de início", value=P("Ano de início", 2026), step=1)
        years = st.number_input("Duração (anos)", value=P("Duração (anos)", 16), step=1, min_value=1)
        disc = st.number_input("Taxa de desconto (%)", value=P("Taxa de desconto (%)", 8.0)) / 100
        fast = st.checkbox("Modo rápido (simula 1.º e último ano e interpola)", P("Modo rápido", True))
        st.subheader("Outros custos do projeto")
        other_capex = st.number_input("Capex adicional (EUR)", value=P("Capex adicional (EUR)", 0.0), min_value=0.0,
                                      help="Licenciamento, ligação à rede, desenvolvimento...")
        om = st.number_input("O&M no 1.º ano (EUR/ano)", value=P("O&M no 1.º ano (EUR/ano)", 0.0), min_value=0.0)
        om_esc = st.number_input("Crescimento anual do O&M (%)", value=P("Crescimento anual do O&M (%)", 2.0)) / 100
        ins = st.number_input("Seguro no 1.º ano (EUR/ano)", value=P("Seguro no 1.º ano (EUR/ano)", 0.0), min_value=0.0)
        ins_chg = st.number_input("Variação anual do seguro (% do valor inicial)", value=P("Variação anual do seguro (% do valor inicial)", 0.0),
                                  help="Linear. Ex.: -2 reduz o seguro 2% do valor inicial por ano.") / 100

with tab_var:
    st.write("Cada linha é uma variante a comparar. Adiciona ou apaga linhas à vontade. "
             "Se preencheres o capex total, substitui o cálculo por EUR/kWp e EUR/kWh.")
    variants_df = st.data_editor(_variants_default(), num_rows="dynamic", width="stretch", key=f"variants_{PRESET_ID}")

run = st.button("Correr simulação", type="primary")

if run:
    def _num(x, default=0.0):
        try:
            return default if x is None or pd.isna(x) or str(x).strip() == "" else float(x)
        except (TypeError, ValueError):
            return default
    vs = [Variant(str(r["Variante"]), _num(r.get("PV (kWp)")), _num(r.get("BESS (kWh)")), _num(r.get("BESS (kW)")),
                  capex_eur=_num(r.get("Capex total (EUR)"), None))
          for _, r in variants_df.dropna(subset=["Variante"]).iterrows()]
    cfg = ProjectConfig(
        name=name, lat=lat, lon=lon, annual_load_mwh=annual, load_kw=load_kw,
        voltage_level=None if lvl.startswith("Sem") else lvl,
        import_limit_kw=imp_lim or 1e6, export_limit_kw=exp_lim or 1e6,
        extra_import_eur_mwh=extra, export_fee_eur_mwh=fee,
        ppa_price_eur_mwh=ppa if sale == "Preço fixo (PPA)" else None, ppa_escalation_eur_mwh_yr=ppa_esc,
        other_capex_eur=other_capex, om_eur_yr=om, om_escalation_yr=om_esc, insurance_eur_yr=ins,
        insurance_change_yr=ins_chg,
        pv_tilt=tilt, pv_azimuth=az, pv_loss_pct=loss, pv_dc_ac_ratio=dcac, pv_degradation_yr=pv_deg,
        pv_capex_eur_kwp=pv_capex, pv_opex_eur_kwp_yr=pv_opex,
        bess_rte=rte, bess_soc_min=soc_min / 100, bess_soc_max=soc_max / 100, bess_degradation_yr=b_deg,
        bess_wear_eur_mwh=wear, bess_capex_eur_kwh=b_capex, bess_opex_eur_kwh_yr=b_opex,
        arbitrage=arbitrage, afrr=afrr, afrr_act_rate=act, afrr_duration_h=dur, afrr_acceptance=acc,
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
    port = st.session_state.get("portfolio")
    if port:
        st.subheader("Carteira de projetos")
        pt = portfolio_table(port)
        cols = ["Projeto", "Variante", "Capex (EUR)", "Opex (EUR/ano)", "Ganho 1.º ano face à base (EUR)",
                "VAL (EUR)", "TIR", "Payback (anos)"]
        st.dataframe(pt[cols].style.format({
            "Capex (EUR)": "{:,.0f}", "Opex (EUR/ano)": "{:,.0f}", "Ganho 1.º ano face à base (EUR)": "{:,.0f}",
            "VAL (EUR)": "{:,.0f}", "TIR": lambda x: "n.d." if pd.isna(x) else f"{x * 100:.1f}%",
            "Payback (anos)": lambda x: "n.d." if pd.isna(x) else f"{x:.1f}"}), width="stretch", hide_index=True)
        k1, k2, k3 = st.columns(3)
        k1.metric("Capex total", f"{pt['Capex (EUR)'].sum():,.0f} EUR")
        k2.metric("VAL total", f"{pt['VAL (EUR)'].sum():,.0f} EUR")
        k3.metric("Ganho total 1.º ano", f"{pt['Ganho 1.º ano face à base (EUR)'].sum():,.0f} EUR")
        pbuf = io.BytesIO()
        portfolio_excel(port, pbuf)
        st.download_button("Descarregar carteira (Excel)", pbuf.getvalue(), file_name="GridForce_carteira.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        st.divider()
    res = st.session_state.get("result")
    if res is None and port:
        st.caption("Para ver gráficos e despacho de um projeto, escolhe-o em cima e carrega em Correr simulação.")
    elif res is None:
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
            "Ganho 1.º ano face à base (EUR)": "{:,.0f}", "Autoconsumo PV (%)": lambda x: "" if pd.isna(x) else f"{x:.0f}%",
            "Importação 1.º ano (MWh)": "{:,.0f}"}), width="stretch", hide_index=True)

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
            st.plotly_chart(_style(fig), width="stretch")
        with c2:
            st.subheader("Cashflow descontado acumulado")
            fig = go.Figure()
            for r in res.variants:
                cf = r.cashflows
                disc_cf = cf / (1 + res.config.discount_rate) ** np.arange(len(cf))
                fig.add_trace(go.Scatter(x=cf.index, y=disc_cf.cumsum(), mode="lines", name=r.variant.name))
            fig.add_hline(y=0, line_dash="dot")
            fig.update_layout(height=460, margin=dict(t=10), yaxis_title="EUR", legend=dict(orientation="h", y=-0.2))
            st.plotly_chart(_style(fig), width="stretch")

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
            fig.add_trace(go.Scatter(x=d.index, y=d.load, name="Consumo", line=dict(color=BRAND["text"], width=2)))
            fig.add_trace(go.Bar(x=d.index, y=d.pv, name="PV usado"))
            fig.add_trace(go.Bar(x=d.index, y=d.dis - d.ch, name="Bateria (+descarga / -carga)"))
            fig.add_trace(go.Bar(x=d.index, y=d.imp - d.exp, name="Rede, mercado (+import / -export)"))
            if d.xpv.sum() > 0:
                fig.add_trace(go.Bar(x=d.index, y=-d.xpv, name="Rede, PV a preço fixo"))
            if d.rup.sum() + d.rdn.sum() > 0:
                fig.add_trace(go.Scatter(x=d.index, y=d.rup, name="Reserva aFRR subir", line=dict(dash="dot")))
            fig.add_trace(go.Scatter(x=d.index, y=d.da_price, name="Preço OMIE (EUR/MWh)", yaxis="y2",
                                     line=dict(color="#F2C14E")))
            fig.update_layout(barmode="relative", height=420, margin=dict(t=10), yaxis_title="kW",
                              yaxis2=dict(overlaying="y", side="right", title="EUR/MWh"),
                              legend=dict(orientation="h", y=-0.2))
            st.plotly_chart(_style(fig), width="stretch")

        st.subheader("Energia no 1.º ano")
        en = pd.DataFrame({"Base": res.baseline_energy, **{x.variant.name: x.energy_y1 for x in res.variants}})
        st.dataframe(en.style.format("{:,.1f}"), width="stretch")

        buf = io.BytesIO()
        to_excel(res, buf)
        st.download_button("Descarregar investment case (Excel)", buf.getvalue(),
                           file_name=f"{res.config.name}_investment_case.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
