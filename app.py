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
import gridforce.sensitivity
import gridforce.library

# Recarregar o motor a cada execução: depois de uma atualização no GitHub o Streamlit Cloud
# pode manter a versão antiga dos módulos em memória.
for _m in (gridforce.dispatch, gridforce.finance, gridforce.project, gridforce.presets,
           gridforce.sensitivity, gridforce.library):
    importlib.reload(_m)
from gridforce.project import ProjectConfig, Variant, run_project, to_excel
from gridforce.presets import config_from_dict, portfolio_excel, portfolio_table
from gridforce import sensitivity as sens
from gridforce import library as lib

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
st.caption("Dimensionamento e simulação de PV e baterias em Portugal: autoconsumo, mercados diário e intradiário OMIE e serviços de sistema (aFRR, mFRR).")

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

with st.expander("Biblioteca de projetos", expanded=False):
    if lib.is_shared():
        st.caption("Projetos guardados e partilhados com a equipa. Não se perdem ao atualizar a página.")
    else:
        st.warning("A biblioteca partilhada ainda não está ligada: os projetos guardados aqui só duram até "
                   "a aplicação reiniciar.")
    loaded = {}
    try:
        lib_files = lib.list_projects()
    except Exception as e:  # noqa: BLE001
        lib_files = []
        st.error(f"Não foi possível ler a biblioteca: {e}")
    _d = lib.days_to_expiry()
    if _d is not None and _d <= 30:
        st.warning(f"A chave de acesso à biblioteca expira dentro de {_d} dias. Crie uma nova no GitHub "
                   "(GridForce biblioteca, Regenerate token) e atualize-a nos Secrets do Streamlit.")
    c1, c2 = st.columns([3, 1])
    with c1:
        sel = st.multiselect("Projetos da biblioteca a abrir", lib_files, key="lib_sel",
                             format_func=lambda x: x[:-5].replace("_", " "))
    with c2:
        st.write("")
        if lib_files and st.button("Selecionar todos"):
            st.session_state["lib_sel"] = lib_files
            st.rerun()
    for fn in sel:
        try:
            d = lib.load_project(fn)
            loaded[d.get("Nome do projeto", fn[:-5])] = (d, f"lib_{fn}")
        except Exception as e:  # noqa: BLE001
            st.error(f"{fn}: não foi possível abrir ({e})")
    ups = st.file_uploader("Ou carregar ficheiros de projeto (.json) do computador", type=["json"],
                           key="preset_files", accept_multiple_files=True)
    up_dicts = []
    for u in ups or []:
        try:
            d = json.loads(u.getvalue().decode("utf-8"))
            up_dicts.append(d)
            loaded[d.get("Nome do projeto", u.name)] = (d, getattr(u, "file_id", u.name))
        except Exception as e:  # noqa: BLE001
            st.error(f"{u.name}: ficheiro inválido ({e})")
    if up_dicts and st.button(f"Guardar {len(up_dicts)} ficheiro(s) carregado(s) na biblioteca"):
        try:
            for d in up_dicts:
                lib.save_project(d)
            st.success("Guardado na biblioteca.")
            st.rerun()
        except Exception as e:  # noqa: BLE001
            st.error(f"Não foi possível guardar: {e}")
    if sel:
        with st.popover("Apagar da biblioteca"):
            st.write("Apaga os projetos selecionados acima. Não se pode desfazer.")
            if st.button(f"Apagar {len(sel)} projeto(s)", type="primary"):
                for fn in sel:
                    lib.delete_project(fn)
                st.session_state["lib_sel"] = []
                st.rerun()
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
            if f is None and PRESET.get("Diagrama de carga (kW)"):
                load_kw = np.asarray(PRESET["Diagrama de carga (kW)"], dtype=float)
                st.info(f"A usar o diagrama de carga guardado no projeto ({load_kw.sum() * 0.25 / 1000:,.1f} MWh/ano).")
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
        max_cyc = st.number_input("Máximo de ciclos por dia (0 = sem limite)", value=P("Máximo de ciclos por dia (0 = sem limite)", 2.0),
                                  min_value=0.0, help="Média por semana, contando também a energia das ativações aFRR/mFRR. "
                                                      "Garantias típicas: 1 a 2 ciclos por dia.")
        b_capex = st.number_input("Capex bateria (EUR/kWh)", value=P("Capex bateria (EUR/kWh)", 509.05))
        b_opex = st.number_input("Opex bateria (EUR/kWh/ano)", value=P("Opex bateria (EUR/kWh/ano)", 0.0))
        with st.expander("Mais parâmetros da bateria"):
            eta_c = st.number_input("Eficiência de carga (%, 0 = usar a round-trip)", value=P("Eficiência de carga (%)", 0.0),
                                    min_value=0.0, max_value=100.0) / 100
            eta_d = st.number_input("Eficiência de descarga (%, 0 = usar a round-trip)", value=P("Eficiência de descarga (%)", 0.0),
                                    min_value=0.0, max_value=100.0) / 100
            avail = st.number_input("Disponibilidade técnica (%)", value=P("Disponibilidade técnica (%)", 100.0),
                                    min_value=0.0, max_value=100.0) / 100
            aux = st.number_input("Consumos auxiliares (kW por MW de bateria)", value=P("Consumos auxiliares (kW por MW)", 0.0),
                                  min_value=0.0, help="AVAC, controlo, transformador. Típico: 5 a 15 kW/MW.")
        with st.expander("Degradação, fim de vida e substituições"):
            DEG = ["Linear (% por ano)", "Por ciclos e calendário"]
            deg_mode = st.radio("Modelo de degradação", DEG, index=DEG.index(P("Modelo de degradação", DEG[0])),
                                help="Linear usa a 'Perda de capacidade anual'. Por ciclos soma a perda de calendário "
                                     "e a perda por ciclo equivalente, com os ciclos que a simulação faz.")
            cal = st.number_input("Perda por calendário (%/ano)", value=P("Perda por calendário (%/ano)", 1.0),
                                  disabled=deg_mode == DEG[0]) / 100
            cyc = st.number_input("Perda por ciclo equivalente (%)", value=P("Perda por ciclo equivalente (%)", 0.0033),
                                  format="%.4f", disabled=deg_mode == DEG[0]) / 100
            eol = st.number_input("Fim de vida (% da capacidade inicial)", value=P("Fim de vida (%)", 70.0),
                                  disabled=deg_mode == DEG[0]) / 100
            aug = st.checkbox("Repor capacidade no fim de vida (augmentation)", P("Augmentation", False),
                              disabled=deg_mode == DEG[0])
            aug_cost = st.number_input("Custo da reposição (EUR por kWh reposto)", value=P("Custo da reposição (EUR/kWh)", 150.0),
                                       disabled=not aug or deg_mode == DEG[0])
            pcs_y = st.number_input("Ano de substituição do PCS (0 = não)", value=P("Ano de substituição do PCS", 0), step=1,
                                    min_value=0)
            pcs_c = st.number_input("Custo da substituição do PCS (EUR/kW)", value=P("Custo da substituição do PCS (EUR/kW)", 0.0))

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
        cap_scale = st.number_input("Ajuste dos preços de capacidade aFRR (%)",
                                    value=P("Ajuste dos preços de capacidade aFRR (%)", 100.0), min_value=0.0,
                                    help="100% = preços da ENTSO-E dos últimos 12 meses. Ex.: 300% para usar preços 3 vezes maiores.") / 100
        intra = st.checkbox("Mercado intradiário contínuo", P("Intradiário", False),
                            help="A bateria compra e vende ao melhor preço entre o diário e o intradiário (OMIE).")
        capt = st.number_input("Vantagem do intradiário capturada (%)", value=P("Vantagem do intradiário capturada (%)", 25.0),
                               min_value=0.0, max_value=100.0, disabled=not intra,
                               help="Com previsão perfeita, escolher sempre o melhor mercado sobrestima o ganho.") / 100
        mfrr = st.checkbox("Reserva de substituição manual (mFRR)", P("mFRR", False),
                           help="Só energia ativada, a preços da ENTSO-E. Precisa da chave ENTSOE_TOKEN.")
        m_up = st.number_input("Ativação mFRR a subir (%)", value=P("Ativação mFRR a subir (%)", 40.0), disabled=not mfrr) / 100
        m_dn = st.number_input("Ativação mFRR a descer (%)", value=P("Ativação mFRR a descer (%)", 49.0), disabled=not mfrr) / 100
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
        HOR = ["Semana (previsão perfeita)", "Dia a dia (mais realista)"]
        hor = st.selectbox("Horizonte do despacho", HOR, index=HOR.index(P("Horizonte do despacho", HOR[0])),
                           help="Dia a dia: a bateria só conhece os preços do dia seguinte, como no mercado diário real, "
                                "e volta ao estado de carga inicial no fim de cada dia.")
        st.subheader("Outros custos do projeto")
        other_capex = st.number_input("Capex adicional (EUR)", value=P("Capex adicional (EUR)", 0.0), min_value=0.0,
                                      help="Licenciamento, ligação à rede, desenvolvimento...")
        om = st.number_input("O&M no 1.º ano (EUR/ano)", value=P("O&M no 1.º ano (EUR/ano)", 0.0), min_value=0.0)
        om_esc = st.number_input("Crescimento anual do O&M (%)", value=P("Crescimento anual do O&M (%)", 2.0)) / 100
        ins = st.number_input("Seguro no 1.º ano (EUR/ano)", value=P("Seguro no 1.º ano (EUR/ano)", 0.0), min_value=0.0)
        ins_chg = st.number_input("Variação anual do seguro (% do valor inicial)", value=P("Variação anual do seguro (% do valor inicial)", 0.0),
                                  help="Linear. Ex.: -2 reduz o seguro 2% do valor inicial por ano.") / 100
        bsp_fee = st.number_input("Comissão do agregador/BSP (% das receitas de serviços de sistema)",
                                  value=P("Comissão do agregador/BSP (%)", 0.0), min_value=0.0, max_value=100.0) / 100
        esc = st.number_input("Escalada anual dos preços de mercado (%)", value=P("Escalada anual dos preços (%)", 0.0),
                              help="Aplica-se a mercados, serviços de sistema e tarifas. O preço fixo (PPA) tem o seu próprio aumento.") / 100
        resid = st.number_input("Valor residual no fim (% do capex)", value=P("Valor residual (% do capex)", 0.0),
                                min_value=0.0, max_value=100.0) / 100
        with st.expander("Financiamento e impostos"):
            st.caption("Com imposto e dívida a zero, o caso é antes de impostos e só com capital próprio (como a GridCog).")
            tax = st.number_input("Imposto sobre lucros, IRC + derrama (%)", value=P("Imposto sobre lucros (%)", 0.0),
                                  min_value=0.0, max_value=60.0) / 100
            dep_y = st.number_input("Amortização fiscal do capex (anos)", value=P("Amortização fiscal (anos)", 15), min_value=1, step=1)
            debt_pct = st.number_input("Dívida (% do capex)", value=P("Dívida (% do capex)", 0.0), min_value=0.0, max_value=100.0) / 100
            debt_rate = st.number_input("Taxa de juro da dívida (%)", value=P("Taxa de juro da dívida (%)", 5.0), min_value=0.0) / 100
            debt_ten = st.number_input("Prazo da dívida (anos)", value=P("Prazo da dívida (anos)", 10), min_value=1, step=1)
            KINDS = ["Prestação constante (anuidade)", "Amortização constante"]
            debt_kind = st.selectbox("Reembolso", KINDS, index=KINDS.index(P("Reembolso", KINDS[0])))
            dscr_min = st.number_input("DSCR mínimo exigido (0 = sem limite)", value=P("DSCR mínimo", 0.0), min_value=0.0,
                                       help="Se definido, a dívida é reduzida até cada ano ter pelo menos este DSCR.")
            eq_rate = st.number_input("Custo do capital próprio (%)", value=P("Custo do capital próprio (%)", 10.0), min_value=0.0) / 100

with tab_var:
    st.write("Cada linha é uma variante a comparar. Adiciona ou apaga linhas à vontade. "
             "Se preencheres o capex total, substitui o cálculo por EUR/kWp e EUR/kWh.")
    variants_df = st.data_editor(_variants_default(), num_rows="dynamic", width="stretch", key=f"variants_{PRESET_ID}")

def _current_project() -> dict:
    vdf = variants_df.dropna(subset=["Variante"]).copy()
    vdf = vdf.astype(object).where(pd.notna(vdf), None)
    d = {
        "Nome do projeto": name, "Latitude": lat, "Longitude": lon, "Consumo do local": load_mode,
        "Consumo anual (MWh)": annual,
        "Limite de importação (kW, 0 = sem limite)": imp_lim, "Limite de injeção na rede (kW, 0 = sem limite)": exp_lim,
        "Inclinação (°)": tilt, "Azimute (°, 180 = sul)": az, "Perdas do sistema (%)": loss,
        "Rácio DC/AC do inversor": dcac, "Degradação anual (%)": pv_deg * 100, "Capex PV (EUR/kWp)": pv_capex,
        "Opex PV (EUR/kWp/ano)": pv_opex, "Eficiência round-trip (%)": rte * 100, "Janela de SOC (%)": [soc_min, soc_max],
        "Perda de capacidade anual (%)": b_deg * 100, "Custo de desgaste (EUR/MWh descarregado)": wear,
        "Máximo de ciclos por dia (0 = sem limite)": max_cyc, "Capex bateria (EUR/kWh)": b_capex,
        "Opex bateria (EUR/kWh/ano)": b_opex, "Eficiência de carga (%)": eta_c * 100 if eta_c else 0.0,
        "Eficiência de descarga (%)": eta_d * 100 if eta_d else 0.0, "Disponibilidade técnica (%)": avail * 100,
        "Consumos auxiliares (kW por MW)": aux, "Modelo de degradação": deg_mode,
        "Perda por calendário (%/ano)": cal * 100, "Perda por ciclo equivalente (%)": cyc * 100,
        "Fim de vida (%)": eol * 100, "Augmentation": aug, "Custo da reposição (EUR/kWh)": aug_cost,
        "Ano de substituição do PCS": int(pcs_y), "Custo da substituição do PCS (EUR/kW)": pcs_c,
        "Preços OMIE: últimos 12 meses até": p_end.isoformat(), "Arbitragem": arbitrage, "aFRR": afrr,
        "Taxa de ativação aFRR (%)": act * 100, "Duração mínima da reserva (h)": dur, "Ofertas aceites (%)": acc * 100,
        "Ajuste dos preços de capacidade aFRR (%)": cap_scale * 100, "Intradiário": intra,
        "Vantagem do intradiário capturada (%)": capt * 100, "mFRR": mfrr, "Ativação mFRR a subir (%)": m_up * 100,
        "Ativação mFRR a descer (%)": m_dn * 100, "Nível de tensão": lvl, "Outros custos na compra (EUR/MWh)": extra,
        "Comissão na venda (EUR/MWh)": fee, "Venda da energia PV injetada": sale, "Preço fixo no 1.º ano (EUR/MWh)": ppa,
        "Aumento anual do preço fixo (EUR/MWh por ano)": ppa_esc, "Ano de início": int(start_year),
        "Duração (anos)": int(years), "Taxa de desconto (%)": disc * 100, "Modo rápido": fast,
        "Horizonte do despacho": hor, "Capex adicional (EUR)": other_capex, "O&M no 1.º ano (EUR/ano)": om,
        "Crescimento anual do O&M (%)": om_esc * 100, "Seguro no 1.º ano (EUR/ano)": ins,
        "Variação anual do seguro (% do valor inicial)": ins_chg * 100, "Comissão do agregador/BSP (%)": bsp_fee * 100,
        "Escalada anual dos preços (%)": esc * 100, "Valor residual (% do capex)": resid * 100,
        "Imposto sobre lucros (%)": tax * 100, "Amortização fiscal (anos)": int(dep_y),
        "Dívida (% do capex)": debt_pct * 100, "Taxa de juro da dívida (%)": debt_rate * 100,
        "Prazo da dívida (anos)": int(debt_ten), "Reembolso": debt_kind, "DSCR mínimo": dscr_min,
        "Custo do capital próprio (%)": eq_rate * 100,
        "Variantes": vdf.to_dict("records"),
    }
    if load_kw is not None:
        d["Diagrama de carga (kW)"] = [round(float(x), 3) for x in load_kw]
    return {k: (round(v, 10) if isinstance(v, float) else v) for k, v in d.items()}


c_run, c_save, c_dl = st.columns([1, 1, 1])
with c_run:
    run = st.button("Correr simulação", type="primary")
with c_save:
    if st.button("Guardar projeto na biblioteca"):
        try:
            fn = lib.save_project(_current_project())
            st.success(f"Guardado como {fn[:-5].replace('_', ' ')}. Se já existia com este nome, foi substituído.")
        except Exception as e:  # noqa: BLE001
            st.error(f"Não foi possível guardar: {e}")
with c_dl:
    st.download_button("Descarregar projeto (.json)", json.dumps(_current_project(), ensure_ascii=False, indent=2),
                       file_name=lib.safe_name(name), mime="application/json")

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
        bess_wear_eur_mwh=wear, bess_max_cycles_day=max_cyc or None, bess_capex_eur_kwh=b_capex, bess_opex_eur_kwh_yr=b_opex,
        bess_eta_charge=eta_c or None, bess_eta_discharge=eta_d or None, bess_availability=avail,
        bess_aux_kw_per_mw=aux, bess_deg_mode="ciclos" if deg_mode.startswith("Por ciclos") else "linear",
        bess_cal_fade_yr=cal, bess_cycle_fade_per_efc=cyc, bess_eol_pct=eol, bess_augment=aug,
        bess_augment_eur_kwh=aug_cost, pcs_replace_year=int(pcs_y), pcs_replace_eur_kw=pcs_c, bsp_fee_pct=bsp_fee, price_escalation_yr=esc, residual_value_pct=resid,
        arbitrage=arbitrage, afrr=afrr, afrr_act_rate=act, afrr_duration_h=dur, afrr_acceptance=acc, afrr_cap_scale=cap_scale,
        intraday=intra, intraday_capture=capt, mfrr=mfrr, mfrr_up_act_rate=m_up, mfrr_dn_act_rate=m_dn,
        prices_start=(pd.Timestamp(p_end) - pd.DateOffset(years=1) + pd.Timedelta(days=1)).date(), prices_end=p_end,
        start_year=int(start_year), years=int(years), discount_rate=disc, fast=fast,
        horizon_days=1 if hor.startswith("Dia") else 7,
        tax_rate=tax, dep_years=int(dep_y), debt_pct=debt_pct, debt_rate=debt_rate, debt_tenor=int(debt_ten),
        debt_kind="anuidade" if debt_kind.startswith("Prest") else "constante", min_dscr=dscr_min or None,
        equity_rate=eq_rate, variants=vs)
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
        k2.metric("VAL total (NPV)", f"{pt['VAL (EUR)'].sum():,.0f} EUR")
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
        k1.metric("Melhor variante (maior VAL / NPV)", best["Variante"])
        k2.metric("VAL (NPV)", f"{best['VAL (EUR)']:,.0f} EUR",
                  help="Valor Atual Líquido, em inglês Net Present Value (NPV), à taxa de desconto do separador 3.")
        k3.metric("TIR (IRR)", "n.d." if pd.isna(best["TIR"]) else f"{best['TIR'] * 100:.1f}%")
        k4.metric("Payback", "n.d." if pd.isna(best["Payback (anos)"]) else f"{best['Payback (anos)']:.1f} anos")

        st.subheader("Resumo das variantes")
        st.dataframe(summ.style.format({
            "PV (kWp)": "{:,.0f}", "BESS (kWh)": "{:,.0f}", "BESS (kW)": "{:,.0f}",
            "Capex (EUR)": "{:,.0f}", "Opex (EUR/ano)": "{:,.0f}", "VAL (EUR)": "{:,.0f}",
            "TIR": lambda x: "n.d." if pd.isna(x) else f"{x * 100:.1f}%",
            "Payback (anos)": lambda x: "n.d." if pd.isna(x) else f"{x:.1f}",
            "Ganho 1.º ano face à base (EUR)": "{:,.0f}", "Autoconsumo PV (%)": lambda x: "" if pd.isna(x) else f"{x:.0f}%",
            "Importação 1.º ano (MWh)": "{:,.0f}", "EBITDA 1.º ano (EUR)": "{:,.0f}",
            "Ganho 1.º ano por MW de bateria (EUR/MW)": lambda x: "" if pd.isna(x) else f"{x:,.0f}",
            "Ciclos por dia (1.º ano)": lambda x: "" if pd.isna(x) else f"{x:.2f}",
            "LCOS (EUR/MWh descarregado)": lambda x: "" if pd.isna(x) else f"{x:,.1f}",
            "Estado de saúde no fim (%)": lambda x: "" if pd.isna(x) else f"{x:.0f}%",
            "Augmentation e substituições (EUR)": "{:,.0f}",
            "Custo nivelado do PV e bateria (EUR/MWh PV)": lambda x: "" if pd.isna(x) else f"{x:,.1f}",
            "TIR do projeto após impostos": lambda x: "n.d." if pd.isna(x) else f"{x * 100:.1f}%",
            "TIR do acionista": lambda x: "n.d." if pd.isna(x) else f"{x * 100:.1f}%",
            "VAL do projeto após impostos (EUR)": "{:,.0f}", "VAL do acionista (EUR)": "{:,.0f}", "Dívida (EUR)": "{:,.0f}",
            "DSCR mínimo": lambda x: "" if pd.isna(x) else f"{x:.2f}", "DSCR médio": lambda x: "" if pd.isna(x) else f"{x:.2f}"}),
            width="stretch", hide_index=True)

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
            fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, xanchor="left"), height=520, margin=dict(t=110))
            st.plotly_chart(_style(fig), width="stretch")
        with c2:
            st.subheader("Cashflow descontado acumulado")
            fig = go.Figure()
            for r in res.variants:
                cf = r.cashflows
                disc_cf = cf / (1 + res.config.discount_rate) ** np.arange(len(cf))
                fig.add_trace(go.Scatter(x=cf.index, y=disc_cf.cumsum(), mode="lines", name=r.variant.name))
            fig.add_hline(y=0, line_dash="dot")
            fig.update_layout(height=520, margin=dict(t=110), yaxis_title="EUR", legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, xanchor="left"))
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
            fig.update_layout(barmode="relative", height=480, margin=dict(t=80), yaxis_title="kW",
                              yaxis2=dict(overlaying="y", side="right", title="EUR/MWh"),
                              legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, xanchor="left"))
            st.plotly_chart(_style(fig), width="stretch")

        st.subheader("Contas anuais")
        vname_a = st.selectbox("Variante ", [x.variant.name for x in res.variants], key="annual_pick")
        ra = next(x for x in res.variants if x.variant.name == vname_a)
        if ra.annual is not None:
            fmt_a = {c: ("{:.2f}" if c == "DSCR" else "{:.0f}" if c.startswith("Estado") else
                         "{:.0f}" if c.startswith("Ciclos") else "{:,.0f}") for c in ra.annual.columns}
            st.dataframe(ra.annual.style.format(fmt_a, na_rep=""), width="stretch")
        st.subheader("Riscos e sensibilidades")
        st.caption("Cada fator varia sozinho, com o despacho do caso base. Os outros ficam como no caso base.")
        c1, c2, c3 = st.columns([2, 1, 1])
        with c1:
            vname_s = st.selectbox("Variante  ", [x.variant.name for x in res.variants], key="sens_pick")
        with c2:
            s_pct = st.number_input("Variação de receitas e opex (%)", value=20.0, min_value=1.0, max_value=90.0) / 100
        with c3:
            c_pct = st.number_input("Variação do capex (%)", value=10.0, min_value=1.0, max_value=90.0) / 100
        rs = next(x for x in res.variants if x.variant.name == vname_s)
        if rs.parts is not None:
            tor = sens.tornado(rs.parts, s_pct, c_pct)
            b0 = tor.attrs["base_npv"]
            fig = go.Figure()
            fig.add_trace(go.Bar(y=tor["Fator"], x=tor["VAL com fator a descer (EUR)"] - b0, base=b0, orientation="h",
                                 name="Fator a descer", marker_color="#E4572E"))
            fig.add_trace(go.Bar(y=tor["Fator"], x=tor["VAL com fator a subir (EUR)"] - b0, base=b0, orientation="h",
                                 name="Fator a subir", marker_color="#2E86AB"))
            fig.update_layout(barmode="overlay", height=120 + 45 * len(tor), margin=dict(t=60, l=10),
                              xaxis_title="VAL (EUR)", yaxis=dict(autorange="reversed"),
                              legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, xanchor="left"))
            fig.add_vline(x=b0, line_dash="dot")
            st.plotly_chart(_style(fig), width="stretch")
            st.dataframe(tor.drop(columns=["Amplitude (EUR)"]).style.format({
                "VAL com fator a descer (EUR)": "{:,.0f}", "VAL com fator a subir (EUR)": "{:,.0f}",
                "TIR com fator a descer": lambda x: "" if x is None or pd.isna(x) else f"{x:.1%}",
                "TIR com fator a subir": lambda x: "" if x is None or pd.isna(x) else f"{x:.1%}"}),
                width="stretch", hide_index=True)

            st.markdown("**Cenários com preços de anos anteriores (P90 / P50 / P10)**")
            st.caption("Simula o 1.º ano com os preços de cada um dos últimos anos e sorteia, para cada ano do projeto, "
                       "um desses anos. P90 é o valor excedido em 90% dos casos (o mais prudente).")
            c1, c2 = st.columns([1, 2])
            with c1:
                n_hist = st.number_input("Anos de preços a usar", value=3, min_value=2, max_value=6, step=1)
                go_hist = st.button("Correr cenários de preços")
            key_h = (id(res), int(n_hist))
            if go_hist:
                bar_h = st.progress(0.0, "A simular anos de preços...")
                try:
                    st.session_state["price_years"] = (key_h, sens.run_price_years(
                        res.config, int(n_hist), progress=lambda f, t: bar_h.progress(f, t)))
                except Exception as e:  # noqa: BLE001
                    st.error(f"Os cenários falharam: {e}")
                bar_h.empty()
            ph = st.session_state.get("price_years")
            if ph and ph[0] == key_h:
                py = ph[1]
                for f_ in py["failed"]:
                    st.warning(f"Sem dados para {f_}")
                mc = sens.monte_carlo(rs.parts, vname_s, py)
                if mc:
                    m1, m2, m3 = st.columns(3)
                    for col_, p_ in zip((m1, m2, m3), ("P90", "P50", "P10")):
                        t_ = mc[f"{p_} TIR"]
                        col_.metric(f"{p_} VAL", f"{mc[f'{p_} VAL (EUR)']:,.0f} EUR",
                                    help=None)
                        col_.caption(f"TIR {t_:.1%}" if t_ is not None else "TIR n/d")
                    st.dataframe(mc["por_ano"].style.format({
                        "Ganho 1.º ano face à base (EUR)": "{:,.0f}", "VAL se todos os anos fossem assim (EUR)": "{:,.0f}",
                        "TIR": lambda x: "" if x is None or pd.isna(x) else f"{x:.1%}"}), width="stretch", hide_index=True)
                    fig = px.histogram(x=mc["npvs"], nbins=40, labels={"x": "VAL (EUR)"})
                    fig.update_layout(height=300, yaxis_title="Casos", margin=dict(t=30))
                    st.plotly_chart(_style(fig), width="stretch")

        if res.audit:
            with st.expander("Auditoria da execução"):
                st.table(pd.Series(res.audit, name="Valor").astype(str))

        st.subheader("Energia no 1.º ano")
        en = pd.DataFrame({"Base": res.baseline_energy, **{x.variant.name: x.energy_y1 for x in res.variants}})
        st.dataframe(en.style.format("{:,.1f}"), width="stretch")

        buf = io.BytesIO()
        to_excel(res, buf)
        st.download_button("Descarregar investment case (Excel)", buf.getvalue(),
                           file_name=f"{res.config.name}_investment_case.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
