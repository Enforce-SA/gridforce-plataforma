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

import sys as _sys

# Recarregar o motor a cada execução: depois de uma atualização no GitHub o Streamlit Cloud
# pode manter a versão antiga dos módulos em memória. A ordem conta: primeiro os módulos de que
# os outros dependem (dados, tarifas), depois os que os importam.
for _name in ["gridforce.data.pvgis", "gridforce.data.omie", "gridforce.data.entsoe", "gridforce.data.load",
              "gridforce.tariffs", "gridforce.i18n", "gridforce.version", "gridforce.finance", "gridforce.dispatch",
              "gridforce.project", "gridforce.presets", "gridforce.sensitivity", "gridforce.library", "gridforce.report"]:
    if _name in _sys.modules:
        importlib.reload(_sys.modules[_name])
    else:
        importlib.import_module(_name)
from gridforce.project import ProjectConfig, Variant, run_project, to_excel
from gridforce.report import to_docx
from gridforce.data.pvgis import MOUNTING_DEFAULT, MOUNTINGS
from gridforce.presets import CAPEX_MODES, capex_mode, config_from_dict, portfolio_excel, portfolio_table, scenario_comparison
from gridforce.project import compare as compare_variants
from gridforce import sensitivity as sens
from gridforce import library as lib
from gridforce.version import VERSION, DATE as VERSION_DATE
from gridforce.i18n import EN, T, TD, TF, TP, set_lang, translate_xlsx

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


# Uma cor diferente para cada fonte de valor (famílias: mercado verde, PPA amarelo, aFRR azuis, mFRR roxos, tarifas cinzentos)
STREAM_COLORS = {
    "Mercado diário - venda (export)": "#5C8831", "Mercado diário - compra (import)": "#2B4D22",
    "Mercado intradiário - venda (export)": "#8FD14F", "Mercado intradiário - compra (import)": "#3E6B2A",
    "Venda PV a preço fixo (PPA)": "#F2C14E",
    "aFRR subir - capacidade": "#2E86AB", "aFRR descer - capacidade": "#7FC8F8",
    "aFRR subir - ativação": "#1B4F72", "aFRR descer - ativação": "#A9D6E5",
    "mFRR subir - ativação": "#8E6CCF", "mFRR descer - ativação": "#D4B8F0",
    "Tarifas de acesso - energia e potência em ponta": "#9AA79A", "Tarifas de acesso - potência contratada": "#E07A5F",
}


def _style(fig):
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", colorway=SERIES,
                      font=dict(color=BRAND["text"]))
    fig.update_xaxes(gridcolor=BRAND["grid"])
    fig.update_yaxes(gridcolor=BRAND["grid"])
    return fig

from pathlib import Path

_LANGS = {"pt": "Português", "en": "English"}
_lang0 = st.query_params.get("lang", "pt")
_c_logo, _c_lang = st.columns([5, 1])
with _c_lang:
    _lang = st.radio("Língua / Language", list(_LANGS), index=list(_LANGS).index(_lang0) if _lang0 in _LANGS else 0,
                     format_func=_LANGS.get, horizontal=True, label_visibility="collapsed", key="lang")
set_lang(_lang)
if st.query_params.get("lang") != _lang:
    st.query_params["lang"] = _lang
_logo = Path(__file__).parent / "assets" / "enforce_logo.png"
if _logo.exists():
    with _c_logo:
        st.image(str(_logo), width=220)
def _secret(name, default=None):
    import os
    v = os.environ.get(name)
    if v:
        return v
    try:
        return st.secrets.get(name, default)
    except Exception:  # noqa: BLE001
        return default


QA = str(_secret("GRIDFORCE_ENV", "producao")).lower().startswith(("q", "test"))

# Palavra-passe opcional (usada no ambiente de Qualidade, se a app for pública)
_pw = _secret("APP_PASSWORD")
if _pw and not st.session_state.get("auth_ok"):
    _typed = st.text_input(T("Palavra-passe"), type="password")
    if _typed == _pw:
        st.session_state["auth_ok"] = True
        st.rerun()
    if _typed:
        st.error(T("Palavra-passe errada."))
    st.stop()

st.markdown('<h1>Grid<span class="gf">Force</span></h1>', unsafe_allow_html=True)
if QA:
    st.warning(T("AMBIENTE DE QUALIDADE (testes). Os resultados e projetos daqui não são os de Produção."), icon="🧪")
st.caption(T("Dimensionamento e simulação de PV e baterias em Portugal: autoconsumo, mercados diário e intradiário OMIE e serviços de sistema (aFRR, mFRR)."))

with st.expander("📘 " + T("Guia rápido"), expanded=False):
    from gridforce.report import guide_docx, guide_markdown
    _gmd = guide_markdown()
    st.markdown(_gmd)
    _gb = io.BytesIO()
    guide_docx(_gb, _gmd)
    st.download_button(T("Descarregar guia (Word)"), _gb.getvalue(), file_name=T("GridForce_guia_rapido") + ".docx",
                       mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")

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

# Campos que ficam vazios num projeto novo (são próprios de cada projeto); os restantes ficam com valores típicos
NEW_BLANK = {"Nome do projeto": "", "Latitude": None, "Longitude": None, "Consumo anual (MWh)": None,
             "Capex PV (EUR/kWp)": None, "Capex bateria (EUR/kWh)": None, "Preço fixo no 1.º ano (EUR/MWh)": None}


def _new_project():
    n = st.session_state.get("new_n", 0) + 1
    st.session_state["new_n"] = n
    st.session_state["lib_sel"] = []
    st.session_state["preset"], st.session_state["preset_id"] = {"_novo": True}, f"novo{n}"
    for k in ("result", "portfolio", "price_years", "mc_last", "rep_key", "rep_doc"):
        st.session_state.pop(k, None)


with st.expander(T("Biblioteca de projetos"), expanded=False):
    if lib.is_shared():
        st.caption(T("Projetos guardados e partilhados com a equipa. Não se perdem ao atualizar a página."))
    else:
        st.warning(T("A biblioteca partilhada ainda não está ligada: os projetos guardados aqui só duram até "
                   "a aplicação reiniciar."))
    loaded = {}
    try:
        lib_files = lib.list_projects()
    except Exception as e:  # noqa: BLE001
        lib_files = []
        st.error(T("Não foi possível ler a biblioteca: {e}").format(e=e))
    _d = lib.days_to_expiry()
    if _d is not None and _d <= 30:
        st.warning(T("A chave de acesso à biblioteca expira dentro de {d} dias. Crie uma nova no GitHub "
                     "(GridForce biblioteca, Regenerate token) e atualize-a nos Secrets do Streamlit.").format(d=_d))
    c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
    with c1:
        sel = st.multiselect(T("Projetos da biblioteca a abrir"), lib_files, key="lib_sel",
                             format_func=lambda x: x[:-5].replace("_", " "))
    with c2:
        if lib_files and st.button(T("Selecionar todos"), width="stretch"):
            st.session_state["lib_sel"] = lib_files
            st.rerun()
    for fn in sel:
        try:
            d = lib.load_project(fn)
            loaded[d.get("Nome do projeto", fn[:-5])] = (d, f"lib_{fn}")
        except Exception as e:  # noqa: BLE001
            st.error(T("{fn}: não foi possível abrir ({e})").format(fn=fn, e=e))
    ups = st.file_uploader(T("Ou carregar ficheiros de projeto (.json) do computador"), type=["json"],
                           key=f"preset_files_{st.session_state.get('new_n', 0)}", accept_multiple_files=True)
    up_dicts = []
    for u in ups or []:
        try:
            d = json.loads(u.getvalue().decode("utf-8"))
            up_dicts.append(d)
            loaded[d.get("Nome do projeto", u.name)] = (d, getattr(u, "file_id", u.name))
        except Exception as e:  # noqa: BLE001
            st.error(T("{fn}: ficheiro inválido ({e})").format(fn=u.name, e=e))
    if up_dicts and st.button(T("Guardar {n} ficheiro(s) carregado(s) na biblioteca").format(n=len(up_dicts))):
        try:
            for d in up_dicts:
                lib.save_project(d)
            st.success(T("Guardado na biblioteca."))
            st.rerun()
        except Exception as e:  # noqa: BLE001
            st.error(T("Não foi possível guardar: {e}").format(e=e))
    if sel:
        with st.popover(T("Apagar da biblioteca")):
            st.write(T("Apaga os projetos selecionados acima. Não se pode desfazer."))
            if st.button(T("Apagar {n} projeto(s)").format(n=len(sel)), type="primary"):
                for fn in sel:
                    lib.delete_project(fn)
                st.session_state["lib_sel"] = []
                st.rerun()
    if loaded:
        pick = st.selectbox(T("Projeto a mostrar nos separadores"), list(loaded), key="preset_pick")
        st.session_state["preset"], st.session_state["preset_id"] = loaded[pick][0], f"{loaded[pick][1]}_{pick}"
        st.success(T("{n} projeto(s) carregado(s). Os separadores mostram: {p}.").format(n=len(loaded), p=pick))
        if len(loaded) > 1 and st.button(T("Correr os {n} projetos").format(n=len(loaded)), type="primary"):
            bar = st.progress(0.0, T("A preparar..."))
            out = []
            for i, (nm, (d, _)) in enumerate(loaded.items()):
                try:
                    out.append(run_project(config_from_dict(d), progress=lambda f, t, i=i, nm=nm: bar.progress(
                        (i + f) / len(loaded), f"{nm}: {TP(t)}")))
                except Exception as e:  # noqa: BLE001
                    st.error(T("{nm}: a simulação falhou ({e})").format(nm=nm, e=e))
            bar.progress(1.0, T("Concluído"))
            st.session_state["portfolio"] = out
            st.info(T("Resultados no separador 5."))
PRESET = st.session_state.get("preset", {})
PRESET_ID = st.session_state.get("preset_id", "base")


NEW = bool(PRESET.get("_novo"))


def P(key, default):
    if NEW and key in NEW_BLANK:
        return NEW_BLANK[key]
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
    if NEW:
        df = pd.DataFrame(columns=["Variante", "PV (kWp)", "BESS (kWh)", "BESS (kW)", "Capex total (EUR)"])
    elif "Variantes" in PRESET:
        df = pd.DataFrame(PRESET["Variantes"])
    else:
        df = DEFAULT_VARIANTS.copy()
    for c in ("PV (kWp)", "BESS (kWh)", "BESS (kW)", "Capex total (EUR)"):
        if c not in df:
            df[c] = None
    return df.astype({"PV (kWp)": float, "BESS (kWh)": float, "BESS (kW)": float, "Capex total (EUR)": float})


st.button("➕ " + T("Novo projeto"), on_click=_new_project,
          help=T("Limpa os separadores 1 a 4 para começar um projeto do zero. Os projetos da biblioteca não são alterados."))
if NEW:
    st.info(T("Projeto novo. Preenche os campos vazios (nome, localização, consumo, custos e variantes). "
              "Os outros campos têm valores típicos: confirma-os antes de correr."))

# Cada campo dos separadores 1 a 4 tem uma chave ligada ao projeto aberto: ao abrir outro projeto ou começar um novo,
# todos os campos voltam aos valores desse projeto (e mudar de língua já não apaga o que se escreveu).
_REV = {v: k for k, v in EN.items()}
_WIDGETS = ("text_input", "number_input", "checkbox", "radio", "selectbox", "slider", "date_input")
_ORIG = {w: getattr(st, w) for w in _WIDGETS}


def _keyed(fn):
    def wrapper(label, *a, **k):
        k.setdefault("key", f"{PRESET_ID}|{_REV.get(label, label)}")
        return fn(label, *a, **k)
    return wrapper


for _w in _WIDGETS:
    setattr(st, _w, _keyed(_ORIG[_w]))

tab_site, tab_tech, tab_mkt, tab_var, tab_res = st.tabs(
    [T(x) for x in ["1. Local e consumo", "2. PV e bateria", "3. Mercados, tarifas e finanças", "4. Variantes", "5. Resultados"]])

with tab_site:
    c1, c2 = st.columns(2)
    with c1:
        name = st.text_input(T("Nome do projeto"), P("Nome do projeto", "Shopping Centre"))
        scenario = st.text_input(T("Cenário (opcional)"), P("Cenário", ""),
                                 help=T("Ex.: Investment Grade ou Ultra Conservative. Ao correr vários projetos, os "
                                      "cenários aparecem lado a lado. Se ficar vazio, usa o texto entre parênteses "
                                      "no fim do nome do projeto."))
        lat = st.number_input(T("Latitude"), value=P("Latitude", 38.96), format="%.4f")
        lon = st.number_input(T("Longitude"), value=P("Longitude", -9.33), format="%.4f")
    with c2:
        load_mode = st.radio(T("Consumo do local"), LOAD_MODES, format_func=T, index=LOAD_MODES.index(P("Consumo do local", LOAD_MODES[0])))
        load_kw = None
        annual = st.number_input(T("Consumo anual (MWh)"), value=P("Consumo anual (MWh)", 4666.4), min_value=0.0,
                                 disabled=load_mode != "Perfil tipo de centro comercial")
        if load_mode.startswith("Sem consumo"):
            annual = 0.0
        elif load_mode != "Perfil tipo de centro comercial":
            f = st.file_uploader(T("CSV com uma coluna de potência em kW (35 040 linhas de 15 min ou 8 760 horárias)"),
                                 type=["csv"])
            if f is None and PRESET.get("Diagrama de carga (kW)"):
                load_kw = np.asarray(PRESET["Diagrama de carga (kW)"], dtype=float)
                st.info(T("A usar o diagrama de carga guardado no projeto ({x} MWh/ano).").format(x=f"{load_kw.sum() * 0.25 / 1000:,.1f}"))
            if f is not None:
                raw = pd.read_csv(f, sep=None, engine="python")
                col = raw.select_dtypes("number").columns[-1]
                vals = raw[col].to_numpy(float)
                if len(vals) in (8760, 8784):
                    vals = np.repeat(vals, 4)
                load_kw = vals
                st.success(T("{n} intervalos, {e} MWh/ano, ponta {p} kW").format(n=f"{len(vals):,}", e=f"{vals.sum() * 0.25 / 1000:,.1f}", p=f"{vals.max():,.0f}"))
    c3, c4 = st.columns(2)
    with c3:
        imp_lim = st.number_input(T("Limite de importação (kW, 0 = sem limite)"), value=P("Limite de importação (kW, 0 = sem limite)", 0.0), min_value=0.0)
    with c4:
        exp_lim = st.number_input(T("Limite de injeção na rede (kW, 0 = sem limite)"), value=P("Limite de injeção na rede (kW, 0 = sem limite)", 0.0), min_value=0.0)

with tab_tech:
    capex_m = st.radio(T("Capex do equipamento (PV e bateria)"), CAPEX_MODES, format_func=T, horizontal=True,
                       index=CAPEX_MODES.index(capex_mode(PRESET)) if not NEW else 0,
                       help=T("Calculado: kWp x EUR/kWp + kWh x EUR/kWh, com os valores deste separador. "
                            "Valor fixo: escreves o capex do equipamento de cada variante no separador 4."))
    FIXED = capex_m == CAPEX_MODES[1]
    c1, c2 = st.columns(2)
    with c1:
        st.subheader(T("PV"))
        _mnt0 = P("Montagem PV", MOUNTING_DEFAULT)
        mounting = st.selectbox(T("Montagem PV"), list(MOUNTINGS), format_func=T,
                                index=list(MOUNTINGS).index(_mnt0) if _mnt0 in MOUNTINGS else 0,
                                help=T("Fixo ou com seguidor. O perfil de produção vem do PVGIS para o tipo escolhido. "
                                       "Nos seguidores o azimute não conta; no de eixo horizontal e no de 2 eixos a "
                                       "inclinação também não; no de eixo inclinado a inclinação é a do eixo. "
                                       "O PVGIS não considera backtracking nem sombreamento entre filas."))
        _trk = mounting != MOUNTING_DEFAULT
        tilt = st.number_input(T("Inclinação (°)"), value=P("Inclinação (°)", 10.0),
                               disabled=MOUNTINGS[mounting] in (1, 2))
        az = st.number_input(T("Azimute (°, 180 = sul)"), value=P("Azimute (°, 180 = sul)", 180.0), disabled=_trk)
        loss = st.number_input(T("Perdas do sistema (%)"), value=P("Perdas do sistema (%)", 14.0))
        dcac = st.number_input(T("Rácio DC/AC do inversor"), value=P("Rácio DC/AC do inversor", 1.2), min_value=0.5)
        pv_peak_slot = st.container()   # preenchido depois do separador 4 (a potência de pico vem das variantes)
        pv_deg = st.number_input(T("Degradação anual (%)"), value=P("Degradação anual (%)", 0.5)) / 100
        pv_capex = st.number_input(T("Capex PV (EUR/kWp)"), value=P("Capex PV (EUR/kWp)", 900.0), disabled=FIXED,
                                   help=T("Não conta: o capex está como valor fixo por variante (separador 4).") if FIXED else None)
        pv_opex = st.number_input(T("Opex PV (EUR/kWp/ano)"), value=P("Opex PV (EUR/kWp/ano)", 0.0))
    with c2:
        st.subheader(T("Bateria"))
        rte = st.number_input(T("Eficiência round-trip (%)"), value=P("Eficiência round-trip (%)", 88.0)) / 100
        soc_min, soc_max = st.slider(T("Janela de SOC (%)"), 0, 100, tuple(P("Janela de SOC (%)", (5, 95))))
        b_deg = st.number_input(T("Perda de capacidade anual (%)"), value=P("Perda de capacidade anual (%)", 2.0)) / 100
        wear = st.number_input(T("Custo de desgaste (EUR/MWh descarregado)"), value=P("Custo de desgaste (EUR/MWh descarregado)", 5.0))
        max_cyc = st.number_input(T("Máximo de ciclos por dia (0 = sem limite)"), value=P("Máximo de ciclos por dia (0 = sem limite)", 2.0),
                                  min_value=0.0, help=T("Média por semana, contando também a energia das ativações aFRR/mFRR. "
                                                      "Garantias típicas: 1 a 2 ciclos por dia."))
        b_capex = st.number_input(T("Capex bateria (EUR/kWh)"), value=P("Capex bateria (EUR/kWh)", 509.05), disabled=FIXED,
                                  help=T("Não conta: o capex está como valor fixo por variante (separador 4).") if FIXED else None)
        b_opex = st.number_input(T("Opex bateria (EUR/kWh/ano)"), value=P("Opex bateria (EUR/kWh/ano)", 0.0))
        with st.expander(T("Mais parâmetros da bateria")):
            eta_c = st.number_input(T("Eficiência de carga (%, 0 = usar a round-trip)"), value=P("Eficiência de carga (%)", 0.0),
                                    min_value=0.0, max_value=100.0) / 100
            eta_d = st.number_input(T("Eficiência de descarga (%, 0 = usar a round-trip)"), value=P("Eficiência de descarga (%)", 0.0),
                                    min_value=0.0, max_value=100.0) / 100
            avail = st.number_input(T("Disponibilidade técnica (%)"), value=P("Disponibilidade técnica (%)", 100.0),
                                    min_value=0.0, max_value=100.0) / 100
            aux = st.number_input(T("Consumos auxiliares (kW por MW de bateria)"), value=P("Consumos auxiliares (kW por MW)", 0.0),
                                  min_value=0.0, help=T("AVAC, controlo, transformador. Típico: 5 a 15 kW/MW."))
        with st.expander(T("Degradação, fim de vida e substituições")):
            DEG = ["Linear (% por ano)", "Por ciclos e calendário"]
            deg_mode = st.radio(T("Modelo de degradação"), DEG, format_func=T, index=DEG.index(P("Modelo de degradação", DEG[0])),
                                help=T("Linear usa a 'Perda de capacidade anual'. Por ciclos soma a perda de calendário "
                                     "e a perda por ciclo equivalente, com os ciclos que a simulação faz."))
            cal = st.number_input(T("Perda por calendário (%/ano)"), value=P("Perda por calendário (%/ano)", 1.0),
                                  disabled=deg_mode == DEG[0]) / 100
            cyc = st.number_input(T("Perda por ciclo equivalente (%)"), value=P("Perda por ciclo equivalente (%)", 0.0033),
                                  format="%.4f", disabled=deg_mode == DEG[0]) / 100
            eol = st.number_input(T("Fim de vida (% da capacidade inicial)"), value=P("Fim de vida (%)", 70.0),
                                  disabled=deg_mode == DEG[0]) / 100
            aug = st.checkbox(T("Repor capacidade no fim de vida (augmentation)"), P("Augmentation", False),
                              disabled=deg_mode == DEG[0])
            aug_cost = st.number_input(T("Custo da reposição (EUR por kWh reposto)"), value=P("Custo da reposição (EUR/kWh)", 150.0),
                                       disabled=not aug or deg_mode == DEG[0])
            pcs_y = st.number_input(T("Ano de substituição do PCS (0 = não)"), value=P("Ano de substituição do PCS", 0), step=1,
                                    min_value=0)
            pcs_c = st.number_input(T("Custo da substituição do PCS (EUR/kW)"), value=P("Custo da substituição do PCS (EUR/kW)", 0.0))

with tab_mkt:
    c1, c2, c3 = st.columns(3)
    with c1:
        st.subheader(T("Mercados"))
        p_end = st.date_input(T("Preços OMIE: últimos 12 meses até"), dt.date.fromisoformat(P("Preços OMIE: últimos 12 meses até", "2026-09-30")))
        arbitrage = st.checkbox(T("Arbitragem no mercado diário (carregar da rede para vender)"), P("Arbitragem", True))
        afrr = st.checkbox(T("Banda de regulação secundária (aFRR)"), P("aFRR", False),
                           help=T("Precisa da chave ENTSO-E (variável ENTSOE_TOKEN)."))
        act = st.number_input(T("Taxa de ativação aFRR (%)"), value=P("Taxa de ativação aFRR (%)", 10.0)) / 100
        dur = st.number_input(T("Duração mínima da reserva (h)"), value=P("Duração mínima da reserva (h)", 1.0))
        acc = st.number_input(T("Ofertas aceites (%)"), value=P("Ofertas aceites (%)", 100.0), min_value=0.0, max_value=100.0,
                              help=T("Percentagem das horas em que a oferta de reserva é aceite. A GridCog usa 50%.")) / 100
        cap_scale = st.number_input(T("Ajuste dos preços de capacidade aFRR (%)"),
                                    value=P("Ajuste dos preços de capacidade aFRR (%)", 100.0), min_value=0.0,
                                    help=T("100% = preços da ENTSO-E dos últimos 12 meses. Ex.: 300% para usar preços 3 vezes maiores.")) / 100
        intra = st.checkbox(T("Mercado intradiário contínuo"), P("Intradiário", False),
                            help=T("A bateria compra e vende ao melhor preço entre o diário e o intradiário (OMIE)."))
        capt = st.number_input(T("Vantagem do intradiário capturada (%)"), value=P("Vantagem do intradiário capturada (%)", 25.0),
                               min_value=0.0, max_value=100.0, disabled=not intra,
                               help=T("Com previsão perfeita, escolher sempre o melhor mercado sobrestima o ganho.")) / 100
        mfrr = st.checkbox(T("Reserva de substituição manual (mFRR)"), P("mFRR", False),
                           help=T("Só energia ativada, a preços da ENTSO-E. Precisa da chave ENTSOE_TOKEN."))
        m_up = st.number_input(T("Ativação mFRR a subir (%)"), value=P("Ativação mFRR a subir (%)", 40.0), disabled=not mfrr) / 100
        m_dn = st.number_input(T("Ativação mFRR a descer (%)"), value=P("Ativação mFRR a descer (%)", 49.0), disabled=not mfrr) / 100
    with c2:
        st.subheader(T("Tarifas"))
        lvl = st.selectbox(T("Nível de tensão (tarifa de acesso ERSE)"), LEVELS, format_func=T, index=LEVELS.index(P("Nível de tensão", "MT")))
        extra = st.number_input(T("Outros custos na compra (EUR/MWh)"), value=P("Outros custos na compra (EUR/MWh)", 0.0),
                                help=T("Margem do comercializador, CIEG, imposto especial de consumo, etc."))
        fee = st.number_input(T("Comissão na venda (EUR/MWh)"), value=P("Comissão na venda (EUR/MWh)", 0.0))
        sale = st.radio(T("Venda da energia PV injetada"), SALES, format_func=T, index=SALES.index(P("Venda da energia PV injetada", SALES[0])),
                        help=T("Com preço fixo, a energia PV injetada diretamente é paga a esse preço; a bateria "
                             "continua a vender no mercado."))
        ppa = st.number_input(T("Preço fixo no 1.º ano (EUR/MWh)"), value=P("Preço fixo no 1.º ano (EUR/MWh)", 45.9), disabled=sale != "Preço fixo (PPA)")
        ppa_esc = st.number_input(T("Aumento anual do preço fixo (EUR/MWh por ano)"), value=P("Aumento anual do preço fixo (EUR/MWh por ano)", 0.9),
                                  disabled=sale != "Preço fixo (PPA)")
    with c3:
        st.subheader(T("Finanças"))
        start_year = st.number_input(T("Ano de início"), value=P("Ano de início", 2026), step=1)
        years = st.number_input(T("Duração (anos)"), value=P("Duração (anos)", 16), step=1, min_value=1)
        disc = st.number_input(T("Taxa de desconto (%)"), value=P("Taxa de desconto (%)", 8.0)) / 100
        fast = st.checkbox(T("Modo rápido (simula 1.º e último ano e interpola)"), P("Modo rápido", True))
        HOR = ["Semana (previsão perfeita)", "Dia a dia (mais realista)"]
        hor = st.selectbox(T("Horizonte do despacho"), HOR, format_func=T, index=HOR.index(P("Horizonte do despacho", HOR[0])),
                           help=T("Dia a dia: a bateria só conhece os preços do dia seguinte, como no mercado diário real, "
                                "e volta ao estado de carga inicial no fim de cada dia."))
        st.subheader(T("Outros custos do projeto"))
        lic_capex = st.number_input(T("Licenciamento e ligação à rede (EUR)"),
                                    value=P("Licenciamento e ligação à rede (EUR)", 0.0), min_value=0.0,
                                    help=T("Custo de investimento separado do equipamento: licenças, estudos, "
                                         "ramal e ligação à rede. Soma-se ao capex de cada variante."))
        other_capex = st.number_input(T("Capex adicional (EUR)"), value=P("Capex adicional (EUR)", 0.0), min_value=0.0,
                                      help=T("Outros custos de investimento: desenvolvimento, etc. Projetos antigos "
                                           "podem ter aqui o licenciamento e a ligação à rede (o resultado é o mesmo)."))
        UNITS = ["EUR/ano", "EUR/dia"]
        unit = st.radio(T("Unidade do O&M e do seguro"), UNITS, format_func=T, horizontal=True,
                        index=UNITS.index(P("Unidade do O&M e seguro", "EUR/ano")) if P("Unidade do O&M e seguro", "EUR/ano") in UNITS else 0)
        _k = 365.0 if unit == "EUR/dia" else 1.0
        for _u in UNITS:  # o campo da outra unidade volta a ser criado a partir do valor anual atual
            if _u != unit:
                st.session_state.pop(f"{PRESET_ID}|O&M no 1.º ano (EUR/ano)|{_u}", None)
                st.session_state.pop(f"{PRESET_ID}|Seguro no 1.º ano (EUR/ano)|{_u}", None)
        _om_last = st.session_state.get(f"{PRESET_ID}|om_annual", P("O&M no 1.º ano (EUR/ano)", 0.0))
        _ins_last = st.session_state.get(f"{PRESET_ID}|ins_annual", P("Seguro no 1.º ano (EUR/ano)", 0.0))
        om = st.number_input(T("O&M no 1.º ano ({u})").format(u=T(unit)), value=round(float(_om_last or 0.0) / _k, 3),
                             min_value=0.0, key=f"{PRESET_ID}|O&M no 1.º ano (EUR/ano)|{unit}") * _k
        om_esc = st.number_input(T("Crescimento anual do O&M (%)"), value=P("Crescimento anual do O&M (%)", 2.0)) / 100
        ins = st.number_input(T("Seguro no 1.º ano ({u})").format(u=T(unit)), value=round(float(_ins_last or 0.0) / _k, 3),
                              min_value=0.0, key=f"{PRESET_ID}|Seguro no 1.º ano (EUR/ano)|{unit}") * _k
        st.session_state[f"{PRESET_ID}|om_annual"], st.session_state[f"{PRESET_ID}|ins_annual"] = om, ins
        if unit == "EUR/dia" and (om or ins):
            st.caption(T("Por ano: O&M {a} EUR, seguro {b} EUR.").format(a=f"{om:,.0f}", b=f"{ins:,.0f}"))
        ins_chg = st.number_input(T("Variação anual do seguro (% do valor inicial)"), value=P("Variação anual do seguro (% do valor inicial)", 0.0),
                                  help=T("Linear. Ex.: -2 reduz o seguro 2% do valor inicial por ano.")) / 100
        bsp_fee = st.number_input(T("Comissão do agregador/BSP (% das receitas de serviços de sistema)"),
                                  value=P("Comissão do agregador/BSP (%)", 0.0), min_value=0.0, max_value=100.0) / 100
        esc = st.number_input(T("Escalada anual dos preços de mercado (%)"), value=P("Escalada anual dos preços (%)", 0.0),
                              help=T("Aplica-se a mercados, serviços de sistema e tarifas. O preço fixo (PPA) tem o seu próprio aumento.")) / 100
        resid = st.number_input(T("Valor residual no fim (% do capex)"), value=P("Valor residual (% do capex)", 0.0),
                                min_value=0.0, max_value=100.0) / 100
        emf = st.number_input(T("Fator de emissões da rede (g CO2/kWh)"), value=P("Fator de emissões da rede (g CO2/kWh)", 470.0),
                              min_value=0.0, help=T("Para calcular as emissões evitadas. A Enforce usa 470 g CO2/kWh "
                                                  "para a indústria."))
        with st.expander(T("Financiamento e impostos")):
            st.caption(T("Com imposto e dívida a zero, o caso é antes de impostos e só com capital próprio (como a GridCog)."))
            tax = st.number_input(T("Imposto sobre lucros, IRC + derrama (%)"), value=P("Imposto sobre lucros (%)", 0.0),
                                  min_value=0.0, max_value=60.0) / 100
            dep_y = st.number_input(T("Amortização fiscal do capex (anos)"), value=P("Amortização fiscal (anos)", 15), min_value=1, step=1)
            debt_pct = st.number_input(T("Dívida (% do capex)"), value=P("Dívida (% do capex)", 0.0), min_value=0.0, max_value=100.0) / 100
            debt_rate = st.number_input(T("Taxa de juro da dívida (%)"), value=P("Taxa de juro da dívida (%)", 5.0), min_value=0.0) / 100
            debt_ten = st.number_input(T("Prazo da dívida (anos)"), value=P("Prazo da dívida (anos)", 10), min_value=1, step=1)
            KINDS = ["Prestação constante (anuidade)", "Amortização constante"]
            debt_kind = st.selectbox(T("Reembolso"), KINDS, format_func=T, index=KINDS.index(P("Reembolso", KINDS[0])))
            dscr_min = st.number_input(T("DSCR mínimo exigido (0 = sem limite)"), value=P("DSCR mínimo", 0.0), min_value=0.0,
                                       help=T("Se definido, a dívida é reduzida até cada ano ter pelo menos este DSCR."))
            eq_rate = st.number_input(T("Custo do capital próprio (%)"), value=P("Custo do capital próprio (%)", 10.0), min_value=0.0) / 100

with tab_var:
    st.write(T("Cada linha é uma variante a comparar. Adiciona ou apaga linhas à vontade."))
    if FIXED:
        st.info(T("Capex do equipamento: valor fixo por variante. Escreve-o na última coluna. Para usar EUR/kWp e "
                  "EUR/kWh, muda a opção no separador 2. O licenciamento e o capex adicional (separador 3) somam-se."))
    else:
        st.info(T("Capex do equipamento calculado com os EUR/kWp e EUR/kWh do separador 2 (vê o quadro em baixo). "
                  "Para escrever um valor fixo por variante, muda a opção no separador 2."))
    st.caption(T("Para ver o valor da bateria, junta uma linha só com PV (BESS a 0) e compara-a com a de PV + bateria "
               "nos resultados, em \"Cenário base e valor incremental\"."))
    variants_df = st.data_editor(_variants_default(), num_rows="dynamic", width="stretch", key=f"variants_{PRESET_ID}",
                                 column_order=["Variante", "PV (kWp)", "BESS (kWh)", "BESS (kW)"] + (["Capex total (EUR)"] if FIXED else []),
                                 column_config={**{c: st.column_config.Column(T(c)) for c in
                                                   ("Variante", "PV (kWp)", "BESS (kWh)", "BESS (kW)")},
                                                "Capex total (EUR)": st.column_config.NumberColumn(
                                                    T("Capex do equipamento (EUR)"), format="%.0f",
                                                    help=T("PV e bateria, por variante."))})
    _vv = variants_df.dropna(subset=["Variante"])
    if not _vv.empty:
        def _n(x):
            try:
                return 0.0 if x is None or pd.isna(x) else float(x)
            except (TypeError, ValueError):
                return 0.0
        _rows = []
        for _, _r in _vv.iterrows():
            _eq_in = _r.get("Capex total (EUR)") if FIXED else None
            _eq = _n(_eq_in) if _eq_in is not None and not pd.isna(_eq_in) else \
                _n(_r.get("PV (kWp)")) * (pv_capex or 0.0) + _n(_r.get("BESS (kWh)")) * (b_capex or 0.0)
            _rows.append({"Variante": _r["Variante"],
                          "Capex do equipamento (EUR)": _eq,
                          "Origem": "indicado na tabela" if _eq_in is not None and not pd.isna(_eq_in) else "calculado por EUR/kWp e EUR/kWh",
                          "Licenciamento e ligação à rede (EUR)": lic_capex or 0.0,
                          "Capex adicional (EUR)": other_capex or 0.0,
                          "Capex total do projeto (EUR)": _eq + (lic_capex or 0.0) + (other_capex or 0.0)})
        st.markdown(T("**Capex total usado na simulação**"))
        _ct = pd.DataFrame(_rows)
        _ct["Origem"] = _ct["Origem"].map(T)
        st.dataframe(TD(_ct).style.format({T(c): "{:,.0f}" for c in _ct.columns if c.endswith("(EUR)")}),
                     width="stretch", hide_index=True)
        _miss = [str(_r["Variante"]) for _, _r in _vv.iterrows()
                 if FIXED and (_r.get("Capex total (EUR)") is None or pd.isna(_r.get("Capex total (EUR)")))]
        if _miss:
            st.warning(T("Falta o capex do equipamento de: {v}.").format(v=", ".join(_miss)))
with pv_peak_slot:
    _vv = variants_df.dropna(subset=["Variante"])
    for _i, (_, _r) in enumerate(_vv.iterrows()):
        try:
            _kwp = float(_r.get("PV (kWp)") or 0.0)
        except (TypeError, ValueError):
            _kwp = 0.0
        if pd.isna(_kwp):
            _kwp = 0.0
        _ca, _cb = st.columns(2)
        _lbl = f" · {_r['Variante']}" if len(_vv) > 1 else ""
        _ca.number_input(T("Potência de pico PV (kWp)") + _lbl, value=_kwp, disabled=True, format="%.1f",
                         key=f"{PRESET_ID}|kwp_{_i}_{_r['Variante']}_{_kwp}")
        _cb.number_input(T("Potência AC do inversor (kW)") + _lbl, value=_kwp / dcac if dcac else 0.0, disabled=True,
                         format="%.1f", key=f"{PRESET_ID}|kwac_{_i}_{_r['Variante']}_{_kwp}_{dcac}")
    st.caption(T("A potência de pico é definida por variante, no separador 4. Potência AC = kWp / rácio DC/AC."))
for _w in _WIDGETS:
    setattr(st, _w, _ORIG[_w])

def _current_project() -> dict:
    vdf = variants_df.dropna(subset=["Variante"]).copy()
    vdf = vdf.astype(object).where(pd.notna(vdf), None)
    d = {
        "Nome do projeto": name, "Latitude": lat, "Longitude": lon, "Consumo do local": load_mode,
        "Consumo anual (MWh)": annual,
        "Limite de importação (kW, 0 = sem limite)": imp_lim, "Limite de injeção na rede (kW, 0 = sem limite)": exp_lim,
        "Montagem PV": mounting, "Inclinação (°)": tilt, "Azimute (°, 180 = sul)": az, "Perdas do sistema (%)": loss,
        "Modo do capex": capex_m, "Rácio DC/AC do inversor": dcac, "Degradação anual (%)": pv_deg * 100, "Capex PV (EUR/kWp)": pv_capex,
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
        "Licenciamento e ligação à rede (EUR)": lic_capex, "Unidade do O&M e seguro": unit,
        "Fator de emissões da rede (g CO2/kWh)": emf, "Cenário": scenario,
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
    run = st.button(T("Correr simulação"), type="primary")
with c_save:
    if st.button(T("Guardar projeto na biblioteca")):
        try:
            fn = lib.save_project(_current_project())
            st.success(T("Guardado como {fn}. Se já existia com este nome, foi substituído.").format(fn=fn[:-5].replace('_', ' ')))
        except Exception as e:  # noqa: BLE001
            st.error(T("Não foi possível guardar: {e}").format(e=e))
    with st.popover(T("Gravar como...")):
        st.caption(T("Grava uma cópia com outro nome (nova versão ou projeto novo). O projeto original fica como estava."))
        _base = (name or "").strip() or T("Projeto")
        _sugg, _i = f"{_base} v2", 2
        while lib.safe_name(_sugg) in lib_files:
            _i += 1
            _sugg = f"{_base} v{_i}"
        new_name = st.text_input(T("Novo nome do projeto"), _sugg, key=f"saveas_name_{PRESET_ID}")
        _exists = bool(new_name.strip()) and lib.safe_name(new_name.strip()) in lib_files
        _over = st.checkbox(T("Já existe um projeto com este nome: substituir"), key=f"saveas_over_{PRESET_ID}") if _exists else True
        if _exists and not _over:
            st.warning(T("Já existe um projeto com este nome. Escolhe outro nome ou confirma a substituição."))

        def _save_as(d, new):
            try:
                d = dict(d, **{"Nome do projeto": new})
                fn = lib.save_project(d)
                st.session_state["saveas_msg"] = ("ok", fn)
                st.session_state["lib_sel"] = [fn]
                st.session_state.pop("preset_pick", None)
                st.session_state["preset"], st.session_state["preset_id"] = d, f"lib_{fn}_{new}_{dt.datetime.now():%H%M%S}"
                for k in ("result", "rep_key", "rep_doc"):
                    st.session_state.pop(k, None)
            except Exception as e:  # noqa: BLE001
                st.session_state["saveas_msg"] = ("err", str(e))
        st.button(T("Gravar com este nome"), type="primary", disabled=not new_name.strip() or not _over,
                  on_click=_save_as, args=(_current_project(), new_name.strip()))
    _msg = st.session_state.pop("saveas_msg", None)
    if _msg and _msg[0] == "ok":
        st.success(T("Gravado como {fn}. Os separadores mostram agora este projeto.").format(fn=_msg[1][:-5].replace('_', ' ')))
    elif _msg:
        st.error(T("Não foi possível guardar: {e}").format(e=_msg[1]))
with c_dl:
    st.download_button(T("Descarregar projeto (.json)"), json.dumps(_current_project(), ensure_ascii=False, indent=2),
                       file_name=lib.safe_name(name), mime="application/json")

_missing = []
if run:
    for _lbl, _val in [("Nome do projeto", name.strip()), ("Latitude", lat), ("Longitude", lon)]:
        if _val in (None, ""):
            _missing.append(T(_lbl))
    if load_mode == "Perfil tipo de centro comercial" and annual is None:
        _missing.append(T("Consumo anual (MWh)"))
    if load_mode == "Carregar diagrama de carga (CSV)" and load_kw is None:
        _missing.append(T("Diagrama de carga (CSV)"))
    if sale == "Preço fixo (PPA)" and ppa is None:
        _missing.append(T("Preço fixo no 1.º ano (EUR/MWh)"))
    _vd = variants_df.dropna(subset=["Variante"])
    if _vd.empty:
        _missing.append(T("Variantes (separador 4)"))
    else:
        _no_total = _vd["Capex total (EUR)"].isna() if FIXED else pd.Series(True, index=_vd.index)
        if FIXED and _no_total.any():
            _missing.append(T("Capex do equipamento (separador 4)"))
        if not FIXED and pv_capex is None and (_no_total & (_vd["PV (kWp)"].fillna(0) > 0)).any():
            _missing.append(T("Capex PV (EUR/kWp)"))
        if not FIXED and b_capex is None and (_no_total & (_vd["BESS (kWh)"].fillna(0) > 0)).any():
            _missing.append(T("Capex bateria (EUR/kWh)"))
    if _missing:
        st.error(T("Falta preencher: {x}.").format(x=", ".join(_missing)))
        run = False
if run:
    def _num(x, default=0.0):
        try:
            return default if x is None or pd.isna(x) or str(x).strip() == "" else float(x)
        except (TypeError, ValueError):
            return default
    vs = [Variant(str(r["Variante"]), _num(r.get("PV (kWp)")), _num(r.get("BESS (kWh)")), _num(r.get("BESS (kW)")),
                  capex_eur=_num(r.get("Capex total (EUR)"), None) if FIXED else None)
          for _, r in variants_df.dropna(subset=["Variante"]).iterrows()]
    cfg = ProjectConfig(
        name=name, scenario=scenario, lat=lat, lon=lon, annual_load_mwh=annual or 0.0, load_kw=load_kw,
        voltage_level=None if lvl.startswith("Sem") else lvl,
        import_limit_kw=imp_lim or 1e6, export_limit_kw=exp_lim or 1e6,
        extra_import_eur_mwh=extra, export_fee_eur_mwh=fee,
        ppa_price_eur_mwh=ppa if sale == "Preço fixo (PPA)" else None, ppa_escalation_eur_mwh_yr=ppa_esc,
        other_capex_eur=other_capex, licensing_capex_eur=lic_capex, emission_factor_g_kwh=emf, om_eur_yr=om, om_escalation_yr=om_esc, insurance_eur_yr=ins,
        insurance_change_yr=ins_chg,
        pv_tilt=tilt, pv_azimuth=az, pv_mounting=mounting, pv_loss_pct=loss, pv_dc_ac_ratio=dcac, pv_degradation_yr=pv_deg,
        pv_capex_eur_kwp=pv_capex if pv_capex is not None else 0.0, pv_opex_eur_kwp_yr=pv_opex,
        bess_rte=rte, bess_soc_min=soc_min / 100, bess_soc_max=soc_max / 100, bess_degradation_yr=b_deg,
        bess_wear_eur_mwh=wear, bess_max_cycles_day=max_cyc or None, bess_capex_eur_kwh=b_capex if b_capex is not None else 0.0, bess_opex_eur_kwh_yr=b_opex,
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
    bar = st.progress(0.0, T("A preparar dados de mercado e PV..."))
    try:
        st.session_state["result"] = run_project(cfg, progress=lambda f, t: bar.progress(f, TP(t)))
        bar.progress(1.0, T("Concluído"))
    except Exception as e:  # noqa: BLE001
        bar.empty()
        st.error(T("A simulação falhou: {e}").format(e=e))

with tab_res:
    port = st.session_state.get("portfolio")
    if port:
        st.subheader(T("Carteira de projetos"))
        pt = portfolio_table(port)
        cols = ["Projeto", "Variante", "Capex (EUR)", "Opex (EUR/ano)", "Ganho 1.º ano face à base (EUR)",
                "VAL (EUR)", "TIR", "Payback (anos)"]
        st.dataframe(TD(pt[cols]).style.format(TF({
            "Capex (EUR)": "{:,.0f}", "Opex (EUR/ano)": "{:,.0f}", "Ganho 1.º ano face à base (EUR)": "{:,.0f}",
            "VAL (EUR)": "{:,.0f}", "TIR": lambda x: T("n.d.") if pd.isna(x) else f"{x * 100:.1f}%",
            "Payback (anos)": lambda x: T("n.d.") if pd.isna(x) else f"{x:.1f}"})), width="stretch", hide_index=True)
        k1, k2, k3 = st.columns(3)
        k1.metric(T("Capex total"), f"{pt['Capex (EUR)'].sum():,.0f} EUR")
        k2.metric(T("VAL total (NPV)"), f"{pt['VAL (EUR)'].sum():,.0f} EUR")
        k3.metric(T("Ganho total 1.º ano"), f"{pt['Ganho 1.º ano face à base (EUR)'].sum():,.0f} EUR")
        pbuf = io.BytesIO()
        portfolio_excel(port, pbuf)
        sc = scenario_comparison(port)
        if not sc["totals"].empty and len(sc["totals"]) > 1:
            st.subheader(T("Cenários lado a lado"))
            st.caption(T("Para cada projeto conta a variante com maior VAL. A TIR do cenário é a dos cashflows "
                       "de todos os parques somados."))
            st.dataframe(TD(sc["totals"]).style.format(TF({
                "Capex (EUR)": "{:,.0f}", "Ganho 1.º ano face à base (EUR)": "{:,.0f}", "EBITDA 1.º ano (EUR)": "{:,.0f}",
                "VAL (EUR)": "{:,.0f}", "TIR": lambda x: T("n.d.") if x is None or pd.isna(x) else f"{x * 100:.1f}%",
                "Emissões evitadas 1.º ano (t CO2)": "{:,.0f}"})), width="stretch", hide_index=True)
            pp = sc["per_park"]
            c1, c2 = st.columns(2)
            with c1:
                wide = pp.pivot_table(index="Parque", columns="Cenário", values="VAL (EUR)", aggfunc="first", sort=False)
                wide_t = pp.pivot_table(index="Parque", columns="Cenário", values="TIR", aggfunc="first", sort=False)
                both = pd.concat({T("VAL (EUR)"): wide, T("TIR"): wide_t}, axis=1)
                both.columns = [f"{a} · {b}" for a, b in both.columns]
                _pf = lambda x: "" if x is None or pd.isna(x) else f"{x * 100:.1f}%"
                _ef = lambda x: "" if x is None or pd.isna(x) else f"{x:,.0f}"
                st.dataframe(both.style.format({c: (_pf if c.startswith(T("TIR")) else _ef) for c in both.columns}),
                             width="stretch")
            with c2:
                fig = px.bar(pp, x="Parque", y="VAL (EUR)", color="Cenário", barmode="group",
                             labels={"Parque": T("Parque"), "VAL (EUR)": T("VAL (EUR)"), "Cenário": T("Cenário")})
                fig.update_layout(height=360, margin=dict(t=30))
                st.plotly_chart(_style(fig), width="stretch")
        st.download_button(T("Descarregar carteira (Excel)"), translate_xlsx(pbuf.getvalue()), file_name="GridForce_carteira.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        st.divider()
    res = st.session_state.get("result")
    if res is None and port:
        st.caption(T("Para ver gráficos e despacho de um projeto, escolhe-o em cima e carrega em Correr simulação."))
    elif res is None:
        st.info(T("Preenche os separadores 1 a 4 e carrega em **Correr simulação**."))
    else:
        summ = pd.DataFrame([r.metrics for r in res.variants])
        best = summ.loc[summ["VAL (EUR)"].idxmax()]
        k1, k2, k3, k4 = st.columns(4)
        k1.metric(T("Melhor variante (maior VAL / NPV)"), best["Variante"])
        k2.metric(T("VAL (NPV)"), f"{best['VAL (EUR)']:,.0f} EUR",
                  help=T("Valor Atual Líquido, em inglês Net Present Value (NPV), à taxa de desconto do separador 3."))
        k3.metric(T("TIR (IRR)"), T("n.d.") if pd.isna(best["TIR"]) else f"{best['TIR'] * 100:.1f}%")
        k4.metric(T("Payback"), T("n.d.") if pd.isna(best["Payback (anos)"]) else f"{best['Payback (anos)']:.1f} {T('anos')}")

        st.subheader(T("Resumo das variantes"))
        st.dataframe(TD(summ).style.format(TF({
            "PV (kWp)": "{:,.0f}", "BESS (kWh)": "{:,.0f}", "BESS (kW)": "{:,.0f}",
            "Capex (EUR)": "{:,.0f}", "Opex (EUR/ano)": "{:,.0f}", "VAL (EUR)": "{:,.0f}",
            "TIR": lambda x: T("n.d.") if pd.isna(x) else f"{x * 100:.1f}%",
            "Payback (anos)": lambda x: T("n.d.") if pd.isna(x) else f"{x:.1f}",
            "Ganho 1.º ano face à base (EUR)": "{:,.0f}", "Autoconsumo PV (%)": lambda x: "" if pd.isna(x) else f"{x:.0f}%",
            "Importação 1.º ano (MWh)": "{:,.0f}", "EBITDA 1.º ano (EUR)": "{:,.0f}",
            "Ganho 1.º ano por MW de bateria (EUR/MW)": lambda x: "" if pd.isna(x) else f"{x:,.0f}",
            "Ciclos por dia (1.º ano)": lambda x: "" if pd.isna(x) else f"{x:.2f}",
            "LCOS (EUR/MWh descarregado)": lambda x: "" if pd.isna(x) else f"{x:,.1f}",
            "Estado de saúde no fim (%)": lambda x: "" if pd.isna(x) else f"{x:.0f}%",
            "Augmentation e substituições (EUR)": "{:,.0f}",
            "Custo nivelado do PV e bateria (EUR/MWh PV)": lambda x: "" if pd.isna(x) else f"{x:,.1f}",
            "TIR do projeto após impostos": lambda x: T("n.d.") if pd.isna(x) else f"{x * 100:.1f}%",
            "TIR do acionista": lambda x: T("n.d.") if pd.isna(x) else f"{x * 100:.1f}%",
            "VAL do projeto após impostos (EUR)": "{:,.0f}", "VAL do acionista (EUR)": "{:,.0f}", "Dívida (EUR)": "{:,.0f}",
            "DSCR mínimo": lambda x: "" if pd.isna(x) else f"{x:.2f}", "DSCR médio": lambda x: "" if pd.isna(x) else f"{x:.2f}"})),
            width="stretch", hide_index=True)

        c1, c2 = st.columns(2)
        with c1:
            st.subheader(T("Value stack, 1.º ano, face à base"))
            rows = []
            for r in res.variants:
                for k, v in r.yearly_streams.iloc[0].items():
                    delta = v - res.baseline_streams.get(k, 0.0)
                    if abs(delta) > 1:
                        rows.append({T("Variante"): r.variant.name, T("Fonte de valor"): T(k), "EUR": delta})
            fig = px.bar(pd.DataFrame(rows), x=T("Variante"), y="EUR", color=T("Fonte de valor"), barmode="relative",
                         color_discrete_map={T(k): c for k, c in STREAM_COLORS.items()})
            fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, xanchor="left"), height=520, margin=dict(t=110))
            st.plotly_chart(_style(fig), width="stretch")
            if res.config.ppa_price_eur_mwh is not None:
                st.caption(T("Com PPA, todo o PV injetado diretamente na rede é vendido ao preço fixo. \"Mercado diário - "
                           "venda\" é a energia que a bateria descarrega e vende no mercado (carregada com PV ou com "
                           "energia da rede), nas horas de preço mais alto."))
        with c2:
            st.subheader(T("Cashflow descontado acumulado"))
            fig = go.Figure()
            for r in res.variants:
                cf = r.cashflows
                disc_cf = cf / (1 + res.config.discount_rate) ** np.arange(len(cf))
                fig.add_trace(go.Scatter(x=cf.index, y=disc_cf.cumsum(), mode="lines", name=r.variant.name))
            fig.add_hline(y=0, line_dash="dot")
            fig.update_layout(height=520, margin=dict(t=110), yaxis_title="EUR", legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, xanchor="left"))
            st.plotly_chart(_style(fig), width="stretch")

        st.subheader(T("Despacho num dia"))
        c1, c2 = st.columns([1, 3])
        with c1:
            vname = st.selectbox(T("Variante"), [r.variant.name for r in res.variants])
            r = next(x for x in res.variants if x.variant.name == vname)
            days = sorted({d.date() for d in r.dispatch_y1.index})
            day = st.select_slider(T("Dia"), options=days, value=days[len(days) // 2])
        with c2:
            d = r.dispatch_y1[r.dispatch_y1.index.date == day]
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=d.index, y=d.load, name=T("Consumo"), line=dict(color=BRAND["text"], width=2)))
            fig.add_trace(go.Bar(x=d.index, y=d.pv, name=T("PV usado")))
            fig.add_trace(go.Bar(x=d.index, y=d.dis - d.ch, name=T("Bateria (+descarga / -carga)")))
            fig.add_trace(go.Bar(x=d.index, y=d.imp - d.exp, name=T("Rede, mercado (+import / -export)")))
            if d.xpv.sum() > 0:
                fig.add_trace(go.Bar(x=d.index, y=-d.xpv, name=T("Rede, PV a preço fixo")))
            if d.rup.sum() + d.rdn.sum() > 0:
                fig.add_trace(go.Scatter(x=d.index, y=d.rup, name=T("Reserva aFRR subir"), line=dict(dash="dot")))
            fig.add_trace(go.Scatter(x=d.index, y=d.da_price, name=T("Preço OMIE (EUR/MWh)"), yaxis="y2",
                                     line=dict(color="#F2C14E")))
            fig.update_layout(barmode="relative", height=480, margin=dict(t=80), yaxis_title="kW",
                              yaxis2=dict(overlaying="y", side="right", title="EUR/MWh"),
                              legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, xanchor="left"))
            st.plotly_chart(_style(fig), width="stretch")

        st.subheader(T("Contas anuais"))
        vname_a = st.selectbox(T("Variante "), [x.variant.name for x in res.variants], key="annual_pick")
        ra = next(x for x in res.variants if x.variant.name == vname_a)
        if ra.annual is not None:
            fmt_a = {c: ("{:.2f}" if c == "DSCR" else "{:.0f}" if c.startswith("Estado") else
                         "{:.0f}" if c.startswith("Ciclos") else "{:,.0f}") for c in ra.annual.columns}
            st.dataframe(TD(ra.annual).style.format(TF(fmt_a), na_rep=""), width="stretch")
        st.subheader(T("Riscos e sensibilidades"))
        st.caption(T("Cada fator varia sozinho, com o despacho do caso base. Os outros ficam como no caso base."))
        c1, c2, c3 = st.columns([2, 1, 1])
        with c1:
            vname_s = st.selectbox(T("Variante  "), [x.variant.name for x in res.variants], key="sens_pick")
        with c2:
            s_pct = st.number_input(T("Variação de receitas e opex (%)"), value=20.0, min_value=1.0, max_value=90.0) / 100
        with c3:
            c_pct = st.number_input(T("Variação do capex (%)"), value=10.0, min_value=1.0, max_value=90.0) / 100
        rs = next(x for x in res.variants if x.variant.name == vname_s)
        if rs.parts is not None:
            tor = sens.tornado(rs.parts, s_pct, c_pct)
            b0 = tor.attrs["base_npv"]
            fig = go.Figure()
            fig.add_trace(go.Bar(y=[T(f_) for f_ in tor["Fator"]], x=tor["VAL com fator a descer (EUR)"] - b0, base=b0, orientation="h",
                                 name=T("Fator a descer"), marker_color="#E4572E"))
            fig.add_trace(go.Bar(y=[T(f_) for f_ in tor["Fator"]], x=tor["VAL com fator a subir (EUR)"] - b0, base=b0, orientation="h",
                                 name=T("Fator a subir"), marker_color="#2E86AB"))
            fig.update_layout(barmode="overlay", height=120 + 45 * len(tor), margin=dict(t=60, l=10),
                              xaxis_title=T("VAL (EUR)"), yaxis=dict(autorange="reversed"),
                              legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, xanchor="left"))
            fig.add_vline(x=b0, line_dash="dot")
            st.plotly_chart(_style(fig), width="stretch")
            _tor = tor.drop(columns=["Amplitude (EUR)"]).assign(Fator=lambda x: x["Fator"].map(T))
            st.dataframe(TD(_tor).style.format(TF({
                "VAL com fator a descer (EUR)": "{:,.0f}", "VAL com fator a subir (EUR)": "{:,.0f}",
                "TIR com fator a descer": lambda x: "" if x is None or pd.isna(x) else f"{x:.1%}",
                "TIR com fator a subir": lambda x: "" if x is None or pd.isna(x) else f"{x:.1%}"})),
                width="stretch", hide_index=True)

            st.markdown(T("**Cenários com preços de anos anteriores (P90 / P50 / P10)**"))
            st.caption(T("Simula o 1.º ano com os preços de cada um dos últimos anos e sorteia, para cada ano do projeto, "
                       "um desses anos. P90 é o valor excedido em 90% dos casos (o mais prudente)."))
            c1, c2 = st.columns([1, 2])
            with c1:
                n_hist = st.number_input(T("Anos de preços a usar"), value=3, min_value=2, max_value=6, step=1)
                go_hist = st.button(T("Correr cenários de preços"))
            key_h = (id(res), int(n_hist))
            if go_hist:
                bar_h = st.progress(0.0, T("A simular anos de preços..."))
                try:
                    st.session_state["price_years"] = (key_h, sens.run_price_years(
                        res.config, int(n_hist), progress=lambda f, t: bar_h.progress(f, TP(t))))
                except Exception as e:  # noqa: BLE001
                    st.error(T("Os cenários falharam: {e}").format(e=e))
                bar_h.empty()
            ph = st.session_state.get("price_years")
            if ph and ph[0] == key_h:
                py = ph[1]
                for f_ in py["failed"]:
                    st.warning(T("Sem dados para {x}").format(x=f_))
                mc = sens.monte_carlo(rs.parts, vname_s, py)
                st.session_state["mc_last"] = (id(res), vname_s, mc)
                if mc:
                    m1, m2, m3 = st.columns(3)
                    for col_, p_ in zip((m1, m2, m3), ("P90", "P50", "P10")):
                        t_ = mc[f"{p_} TIR"]
                        col_.metric(f"{p_} {T('VAL (NPV)')}", f"{mc[f'{p_} VAL (EUR)']:,.0f} EUR",
                                    help=None)
                        col_.caption(f"{T('TIR')} {t_:.1%}" if t_ is not None else f"{T('TIR')} {T('n.d.')}")
                    st.dataframe(TD(mc["por_ano"].assign(Preços=lambda x: x["Preços"].map(T))).style.format(TF({
                        "Ganho 1.º ano face à base (EUR)": "{:,.0f}", "VAL se todos os anos fossem assim (EUR)": "{:,.0f}",
                        "TIR": lambda x: "" if x is None or pd.isna(x) else f"{x:.1%}"})), width="stretch", hide_index=True)
                    fig = px.histogram(x=mc["npvs"], nbins=40, labels={"x": T("VAL (EUR)")})
                    fig.update_layout(height=300, yaxis_title=T("Casos"), margin=dict(t=30))
                    st.plotly_chart(_style(fig), width="stretch")

        if res.audit:
            with st.expander(T("Auditoria da execução")):
                st.table(TD(pd.Series(res.audit, name=T("Valor")).astype(str).to_frame()))

        st.subheader(T("Energia no 1.º ano"))
        en = pd.DataFrame({T("Base"): res.baseline_energy, **{x.variant.name: x.energy_y1 for x in res.variants}})
        st.dataframe(TD(en).style.format("{:,.1f}"), width="stretch")

        # ---------------------------------------------- cenário base e valor incremental
        st.subheader(T("Cenário base e valor incremental"))
        st.caption(T("O cenário base é o local sem PV nem bateria. Todos os resultados acima são o ganho face a "
                   "esta base. Aqui podes comparar duas variantes entre si (ex.: PV + bateria face a só PV, para "
                   "ver o valor da bateria) ou uma variante com a base."))
        _bs = {k: v for k, v in res.baseline_streams.items() if abs(v) > 0.5}
        if _bs:
            st.dataframe(TD(pd.Series(_bs, name=T("Base, 1.º ano (EUR)")).rename(index=T).to_frame()).style.format("{:,.0f}"),
                         width="stretch")
        else:
            st.caption(T("Neste projeto a base não tem custos nem receitas (sem consumo), por isso o valor face à base "
                       "é o valor total dos ativos."))
        _BASE = T("Cenário base (sem ativos)")
        _vn = [x.variant.name for x in res.variants]
        c1, c2 = st.columns(2)
        with c1:
            a_name = st.selectbox(T("Variante A"), _vn, index=_vn.index(best["Variante"]), key="cmp_a")
        with c2:
            _opts_b = [_BASE] + [n for n in _vn if n != a_name]
            b_name = st.selectbox(T("Comparar com (B)"), _opts_b, key="cmp_b")
        ra_ = next(x for x in res.variants if x.variant.name == a_name)
        rb_ = None if b_name == _BASE else next(x for x in res.variants if x.variant.name == b_name)
        cmpr = compare_variants(ra_, rb_, res.config.discount_rate)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric(T("VAL de A face a B"), f"{cmpr['npv']:,.0f} EUR")
        m2.metric(T("TIR incremental"), T("n.d.") if cmpr["irr"] is None else f"{cmpr['irr'] * 100:.1f}%")
        _cb = rb_.metrics["Capex (EUR)"] if rb_ else 0.0
        _gb = rb_.metrics["Ganho 1.º ano face à base (EUR)"] if rb_ else 0.0
        m3.metric(T("Capex adicional de A"), f"{ra_.metrics['Capex (EUR)'] - _cb:,.0f} EUR")
        m4.metric(T("Ganho 1.º ano de A face a B"), f"{ra_.metrics['Ganho 1.º ano face à base (EUR)'] - _gb:,.0f} EUR")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(T("**Cashflow relativo (A - B)**"))
            tb = cmpr["table"]
            fig = go.Figure()
            fig.add_trace(go.Bar(x=tb.index, y=tb["Diferença (A - B)"], name=T("Diferença (A - B)")))
            fig.add_trace(go.Scatter(x=tb.index, y=tb["Diferença descontada acumulada"], mode="lines",
                                     name=T("Diferença descontada acumulada")))
            fig.add_hline(y=0, line_dash="dot")
            fig.update_layout(height=380, margin=dict(t=60), yaxis_title="EUR",
                              legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, xanchor="left"))
            st.plotly_chart(_style(fig), width="stretch")
        with c2:
            st.markdown(T("**Value stack do 1.º ano: A - B**"))
            sb = rb_.yearly_streams.iloc[0] if rb_ else pd.Series(res.baseline_streams)
            dd = (ra_.yearly_streams.iloc[0] - sb.reindex(ra_.yearly_streams.columns).fillna(0.0))
            dd = dd[dd.abs() > 1]
            fig = px.bar(x=dd.values, y=[T(k) for k in dd.index], orientation="h", labels={"x": "EUR", "y": ""})
            fig.update_layout(height=380, margin=dict(t=60))
            st.plotly_chart(_style(fig), width="stretch")
        with st.expander(T("Cashflow relativo por ano")):
            st.dataframe(TD(cmpr["table"]).style.format("{:,.0f}"), width="stretch")

        # ---------------------------------------------- preços aplicados
        if res.rates is not None and len(res.rates):
            st.subheader(T("Preços aplicados por ano"))
            st.caption(T("Preços médios de mercado e custos usados em cada ano, já com escalada, ajuste aFRR e "
                       "comissões. Serve para auditar os pressupostos."))
            rt = res.rates.copy()
            rt["Item"] = rt["Item"].map(T)
            rt["Unidade"] = rt["Unidade"].map(T)
            ycols = [c for c in rt.columns if not isinstance(c, str)]
            rt.columns = [str(c) for c in rt.columns]
            _rf = lambda x: "" if x is None or pd.isna(x) else (f"{x:,.0f}" if abs(x) >= 1000 else f"{x:,.2f}")
            st.dataframe(TD(rt).style.format({str(c): _rf for c in ycols}), width="stretch", hide_index=True,
                         height=36 * (len(rt) + 1) + 4)

        # ---------------------------------------------- fluxos de energia e emissões
        st.subheader(T("Fluxos de energia entre ativos e emissões evitadas"))
        c1, c2 = st.columns([1, 2])
        with c1:
            vname_f = st.selectbox(T("Variante   "), _vn, index=_vn.index(best["Variante"]), key="flow_pick")
            rf = next(x for x in res.variants if x.variant.name == vname_f)
            if rf.flows_y1:
                st.dataframe(TD(pd.Series(rf.flows_y1, name=T("MWh no 1.º ano")).rename(index=T).to_frame())
                             .style.format("{:,.0f}"), width="stretch")
            if rf.emissions is not None:
                em = rf.emissions["Emissões evitadas (t CO2)"]
                st.metric(T("Emissões evitadas no 1.º ano"), f"{em.iloc[0]:,.0f} t CO2")
                st.metric(T("Emissões evitadas no projeto"), f"{em.sum():,.0f} t CO2")
                st.caption(T("Face à base, com {f} g CO2/kWh.").format(f=f"{res.config.emission_factor_g_kwh:,.0f}"))
        with c2:
            if rf.flows_y1:
                nodes = [T("PV"), T("Bateria"), T("Rede"), T("Consumo"), T("Bateria"), T("Rede")]
                # origens: 0 PV, 1 Bateria, 2 Rede; destinos: 3 Consumo, 4 Bateria, 5 Rede
                links = {"PV → consumo": (0, 3), "PV → bateria": (0, 4), "PV → rede": (0, 5),
                         "Bateria → consumo": (1, 3), "Bateria → rede": (1, 5), "Rede → consumo": (2, 3),
                         "Rede → bateria": (2, 4)}
                src, tgt, val = [], [], []
                for k, (a_, b_) in links.items():
                    if rf.flows_y1.get(k, 0) > 0.5:
                        src.append(a_); tgt.append(b_); val.append(rf.flows_y1[k])
                if val:
                    fig = go.Figure(go.Sankey(
                        node=dict(label=nodes, pad=18, thickness=18,
                                  color=["#AEC000", "#4FB3A5", "#9AA79A", "#EEF2EA", "#4FB3A5", "#9AA79A"]),
                        link=dict(source=src, target=tgt, value=val, color="rgba(174,192,0,0.35)"),
                        valueformat=",.0f", valuesuffix=" MWh"))
                    fig.update_layout(height=380, margin=dict(t=20, b=20))
                    st.plotly_chart(_style(fig), width="stretch")

        st.subheader(T("Relatório e exportação"))
        _names = [x.variant.name for x in res.variants]
        c1, c2, c3 = st.columns([2, 1, 1], vertical_alignment="bottom")
        with c1:
            vname_r = st.selectbox(T("Variante do relatório"), _names, index=_names.index(best["Variante"]), key="rep_pick")
        _mc = st.session_state.get("mc_last")
        _mc = _mc[2] if _mc and _mc[0] == id(res) and _mc[1] == vname_r else None
        _rk = (id(res), vname_r, _lang, id(_mc) if _mc else None, s_pct, c_pct)
        if st.session_state.get("rep_key") != _rk:
            with st.spinner(T("A preparar o relatório...")):
                _rb = io.BytesIO()
                to_docx(res, vname_r, _rb, price_scen=_mc, sens_pct=s_pct, capex_pct=c_pct)
            st.session_state["rep_key"], st.session_state["rep_doc"] = _rk, _rb.getvalue()
        with c2:
            st.download_button(T("Descarregar relatório (Word)"), st.session_state["rep_doc"],
                               file_name=lib.safe_name(f"{res.config.name} {vname_r} {T('relatorio')}")[:-5] + ".docx",
                               mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        buf = io.BytesIO()
        to_excel(res, buf)
        with c3:
            st.download_button(T("Descarregar investment case (Excel)"), translate_xlsx(buf.getvalue()),
                               file_name=f"{res.config.name}_investment_case.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        st.caption(T("O relatório Word inclui os cenários P90 / P50 / P10 se os correres antes para a mesma variante."))

st.divider()
_cv1, _cv2 = st.columns([1, 3])
with _cv1:
    st.caption(f"GridForce v{VERSION} ({VERSION_DATE}) · {T('Qualidade') if QA else T('Produção')}")
with _cv2:
    with st.expander(T("Histórico de versões")):
        _cl = Path(__file__).parent / "CHANGELOG.md"
        if _cl.exists():
            st.markdown(_cl.read_text(encoding="utf-8").split("\n", 1)[1])
