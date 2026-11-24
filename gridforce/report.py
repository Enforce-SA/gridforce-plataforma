"""Relatório Word (.docx) de uma variante, na língua escolhida na aplicação.

Segue a estrutura do relatório da GridCog (resumo, energia, análise comercial, anexo) e acrescenta
o que o GridForce calcula a mais: financiamento, sensibilidades, cenários de preços e auditoria.
Todo o texto passa por T(), por isso sai em português ou em inglês conforme a língua ativa.
"""
from __future__ import annotations

import datetime as dt
import io
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from docx import Document  # noqa: E402
from docx.enum.section import WD_ORIENT  # noqa: E402,F401
from docx.enum.table import WD_TABLE_ALIGNMENT  # noqa: E402
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK  # noqa: E402
from docx.oxml import OxmlElement  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402
from docx.shared import Cm, Pt, RGBColor  # noqa: E402

from . import i18n  # noqa: E402
from . import sensitivity as sens  # noqa: E402
from .i18n import T  # noqa: E402
from .version import DATE, VERSION  # noqa: E402

LOGO = Path(__file__).resolve().parent.parent / "assets" / "enforce_logo.png"
DARK = RGBColor(0x2B, 0x4D, 0x22)
MUTED = RGBColor(0x5F, 0x6B, 0x5C)
HEAD_FILL = "2B4D22"
ZEBRA = "F3F5EF"
# paleta categórica validada (fundo branco); a ordem é fixa
COLORS = ["#5C8831", "#2a78d6", "#eb6834", "#AEC000", "#6250d6", "#eda100"]
POS, NEG = "#5C8831", "#eb6834"
INK, SUB, GRID = "#1F2A1C", "#5F6B5C", "#E3E6DF"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": GRID, "axes.labelcolor": SUB,
    "xtick.color": SUB, "ytick.color": SUB, "axes.titlecolor": INK, "axes.titlesize": 10,
    "axes.titleweight": "bold", "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.axisbelow": True, "axes.spines.top": False, "axes.spines.right": False,
    "legend.frameon": False, "legend.fontsize": 8,
})


# ---------------------------------------------------------------- formatação

def _nan(x) -> bool:
    return x is None or (isinstance(x, (float, np.floating)) and np.isnan(x))


def num(x, d: int = 0) -> str:
    """Número com separadores da língua ativa (1 234,5 em português; 1,234.5 em inglês)."""
    if _nan(x):
        return T("n.d.")
    x = round(float(x), d) + 0.0          # evita "-0"
    s = f"{x:,.{d}f}"
    if i18n.LANG == "pt":
        s = s.replace(",", " ").replace(".", ",")
    return s


def eur(x, d: int = 0) -> str:
    return T("n.d.") if _nan(x) else f"{num(x, d)} EUR"


def pct(x, d: int = 1) -> str:
    return T("n.d.") if _nan(x) else f"{num(100 * x, d)}%"


def _fmt_date(d) -> str:
    return d.strftime("%d/%m/%Y") if i18n.LANG == "pt" else d.strftime("%d %b %Y")


# ---------------------------------------------------------------- blocos Word

def _shade(cell, hex_fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    tc_pr.append(shd)


def _cell_text(cell, text, bold=False, color=None, size=9, align=None) -> None:
    cell.text = ""
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(0)
    if align is not None:
        p.alignment = align
    run = p.add_run(str(text))
    run.bold = bold
    run.font.size = Pt(size)
    if color is not None:
        run.font.color.rgb = color


def table(doc, header: list[str], rows: list[list], widths: list[float] | None = None, size: int = 9,
          total_last: bool = False) -> None:
    """Tabela com cabeçalho verde, linhas alternadas e números alinhados à direita."""
    t = doc.add_table(rows=1, cols=len(header))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.style = "Table Grid"
    tr_pr = t.rows[0]._tr.get_or_add_trPr()          # repetir o cabeçalho quando a tabela muda de página
    th = OxmlElement("w:tblHeader")
    th.set(qn("w:val"), "true")
    tr_pr.append(th)
    for i, h in enumerate(header):
        c = t.rows[0].cells[i]
        _cell_text(c, h, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF), size=size,
                   align=WD_ALIGN_PARAGRAPH.LEFT if i == 0 else WD_ALIGN_PARAGRAPH.RIGHT)
        _shade(c, HEAD_FILL)
    for k, row in enumerate(rows):
        cells = t.add_row().cells
        last = total_last and k == len(rows) - 1
        for i, v in enumerate(row):
            _cell_text(cells[i], ("\u00a0" if last else "–") if v == "" and i else v, bold=last, size=size,
                       align=WD_ALIGN_PARAGRAPH.LEFT if i == 0 else WD_ALIGN_PARAGRAPH.RIGHT)
            if k % 2 == 1 or last:
                _shade(cells[i], ZEBRA)
    if widths:
        t.autofit = False
        for i, w in enumerate(widths):
            t.columns[i].width = Cm(w)
        for row in t.rows:
            for i, w in enumerate(widths):
                row.cells[i].width = Cm(w)
    doc.add_paragraph()


def kv_table(doc, pairs: list[tuple[str, str]], widths=(9.0, 7.0)) -> None:
    table(doc, [T("Indicador"), T("Valor")], [[a, b] for a, b in pairs], widths=list(widths))


def heading(doc, text: str, level: int = 1) -> None:
    h = doc.add_heading(text, level=level)
    for r in h.runs:
        r.font.color.rgb = DARK


def para(doc, text: str, italic: bool = False, size: int = 10, color=None) -> None:
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.italic = italic
    r.font.size = Pt(size)
    if color is not None:
        r.font.color.rgb = color


def caption(doc, text: str) -> None:
    para(doc, text, italic=True, size=8, color=MUTED)


def figure(doc, fig, width_cm: float = 16.0) -> None:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    doc.add_picture(buf, width=Cm(width_cm))
    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER


def _page_break(doc) -> None:
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def _thousands(ax, axis="y") -> None:
    """Eixo com separadores da língua; valores grandes em milhões (M) e no máximo 6 marcas."""
    a = ax.yaxis if axis == "y" else ax.xaxis
    a.set_major_locator(matplotlib.ticker.MaxNLocator(nbins=6))
    lo, hi = (ax.get_ylim() if axis == "y" else ax.get_xlim())
    big = max(abs(lo), abs(hi)) >= 2e6
    a.set_major_formatter(matplotlib.ticker.FuncFormatter(
        lambda v, _: (num(v / 1e6, 1) + " M") if big else num(v)))


# ---------------------------------------------------------------- gráficos

def _monthly_chart(d: pd.DataFrame):
    dd = d.copy()
    dd.index = dd.index.tz_localize(None) if dd.index.tz is not None else dd.index
    m = dd.resample("MS").sum() * 0.25 / 1000            # kW em 15 min -> MWh por mês
    exp = m.exp + (m.xpv if "xpv" in m else 0)
    labels = [x.strftime("%m/%y") for x in m.index]
    x = np.arange(len(m))
    fig, ax = plt.subplots(figsize=(7.5, 3.2))
    series = [(T("PV usado"), m.pv), (T("Importação"), m.imp), (T("Exportação"), exp)]
    w = 0.26
    for i, (name, s) in enumerate(series):
        ax.bar(x + (i - 1) * w, s.values, w * 0.92, label=name, color=COLORS[i])
    if m.load.sum() > 0:
        ax.plot(x, m.load.values, color=INK, lw=2, marker="o", ms=4, label=T("Consumo"))
    ax.set_xticks(x, labels)
    ax.set_ylabel("MWh")
    _thousands(ax)
    ax.legend(ncol=4, loc="upper left", bbox_to_anchor=(0, 1.16))
    return fig


def _daily_chart(d: pd.DataFrame):
    dd = d.copy()
    dd.index = dd.index.tz_localize(None) if dd.index.tz is not None else dd.index
    dd["bat"] = dd.dis - dd.ch
    dd["grid"] = dd.imp - dd.exp - (dd.xpv if "xpv" in dd else 0)
    dd["h"] = dd.index.hour + dd.index.minute / 60
    fig, axes = plt.subplots(1, 2, figsize=(7.5, 3.0), sharey=True)
    for ax, (title, mask) in zip(axes, [(T("Dias úteis"), dd.index.dayofweek < 5),
                                        (T("Fins de semana"), dd.index.dayofweek >= 5)]):
        p = dd[mask].groupby("h")[["load", "pv", "bat", "grid"]].mean()
        if p.load.abs().sum() > 0:
            ax.plot(p.index, p.load, color=INK, lw=2, label=T("Consumo"))
        ax.plot(p.index, p.pv, color=COLORS[0], lw=2, label=T("PV usado"))
        ax.plot(p.index, p.bat, color=COLORS[1], lw=2, label=T("Bateria (+descarga / -carga)"))
        ax.plot(p.index, p.grid, color=COLORS[2], lw=2, label=T("Rede (+importação / -exportação)"))
        ax.axhline(0, color=SUB, lw=0.8)
        ax.set_title(title)
        ax.set_xticks([0, 6, 12, 18, 24])
        ax.set_xlabel(T("Hora"))
    axes[0].set_ylabel(T("kW (média)"))
    _thousands(axes[0])
    axes[0].legend(ncol=2, loc="upper left", bbox_to_anchor=(0, 1.32))
    return fig


def _stack_chart(rows: list[tuple[str, float]]):
    rows = sorted(rows, key=lambda r: r[1])
    fig, ax = plt.subplots(figsize=(7.5, 0.5 + 0.38 * len(rows)))
    vals = [v for _, v in rows]
    ax.barh([n for n, _ in rows], vals, color=[POS if v >= 0 else NEG for v in vals], height=0.6)
    ax.axvline(0, color=SUB, lw=0.8)
    ax.set_xlabel(T("EUR no 1.º ano, face à base"))
    _thousands(ax, "x")
    ax.grid(axis="y", visible=False)
    return fig


def _cum_chart(res, vname: str):
    fig, ax = plt.subplots(figsize=(7.5, 3.2))
    r0 = res.config.discount_rate
    for i, r in enumerate(res.variants):
        cf = r.cashflows
        disc = (cf / (1 + r0) ** np.arange(len(cf))).cumsum()
        sel = r.variant.name == vname
        ax.plot(cf.index, disc.values, lw=2.4 if sel else 1.4, alpha=1 if sel else 0.75,
                color=COLORS[i % len(COLORS)], label=r.variant.name + (" ◄" if sel else ""))
    ax.axhline(0, color=SUB, lw=0.8, ls=":")
    ax.set_ylabel("EUR")
    _thousands(ax)
    ax.legend(loc="upper left", ncol=2)
    return fig


def _tornado_chart(tor: pd.DataFrame):
    b0 = tor.attrs["base_npv"]
    names = [T(f) for f in tor["Fator"]][::-1]
    lo = (tor["VAL com fator a descer (EUR)"] - b0).values[::-1]
    hi = (tor["VAL com fator a subir (EUR)"] - b0).values[::-1]
    fig, ax = plt.subplots(figsize=(7.5, 0.6 + 0.42 * len(tor)))
    ax.barh(names, lo, left=b0, color=NEG, height=0.6, label=T("Fator a descer"))
    ax.barh(names, hi, left=b0, color=COLORS[1], height=0.6, label=T("Fator a subir"))
    ax.axvline(b0, color=INK, lw=0.8, ls=":")
    ax.set_xlabel(T("VAL (EUR)"))
    _thousands(ax, "x")
    ax.grid(axis="y", visible=False)
    ax.legend(ncol=2, loc="upper left", bbox_to_anchor=(0, 1.12 + 0.3 / len(tor)))
    return fig


# ---------------------------------------------------------------- relatório

def to_docx(res, vname: str, buf, price_scen: dict | None = None, sens_pct: float = 0.2,
            capex_pct: float = 0.1) -> None:
    """Escreve o relatório da variante `vname` em `buf` (ficheiro ou BytesIO).

    price_scen: resultado de sensitivity.monte_carlo para esta variante (opcional)."""
    cfg = res.config
    r = next(x for x in res.variants if x.variant.name == vname)
    v, m, e1, eb = r.variant, r.metrics, r.energy_y1, res.baseline_energy
    has_pv, has_bess = v.pv_kwp > 0, v.bess_kwh > 0 and v.bess_kw > 0
    today = dt.date.today()

    doc = Document()
    sec = doc.sections[0]
    sec.page_height, sec.page_width = Cm(29.7), Cm(21.0)
    sec.left_margin = sec.right_margin = Cm(2.2)
    sec.top_margin = sec.bottom_margin = Cm(2.0)
    st_n = doc.styles["Normal"]
    st_n.font.name = "Calibri"
    st_n.font.size = Pt(10)
    for lvl, size in ((1, 16), (2, 12.5), (3, 11)):
        s = doc.styles[f"Heading {lvl}"]
        s.font.name = "Calibri"
        s.font.size = Pt(size)
        s.font.color.rgb = DARK
    foot = sec.footer.paragraphs[0]
    foot.text = f"GridForce v{VERSION} · {cfg.name} · {v.name}"
    foot.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in foot.runs:
        run.font.size = Pt(8)
        run.font.color.rgb = MUTED

    # ------------------------------------------------ capa
    if LOGO.exists():
        doc.add_picture(str(LOGO), width=Cm(6))
    for _ in range(5):
        doc.add_paragraph()
    p = doc.add_paragraph()
    rr = p.add_run(T("RELATÓRIO DA SOLUÇÃO"))
    rr.font.size, rr.bold, rr.font.color.rgb = Pt(12), True, MUTED
    p = doc.add_paragraph()
    rr = p.add_run(cfg.name)
    rr.font.size, rr.bold, rr.font.color.rgb = Pt(30), True, DARK
    p = doc.add_paragraph()
    rr = p.add_run(f"{T('Variante')}: {v.name}")
    rr.font.size, rr.font.color.rgb = Pt(16), DARK
    for _ in range(2):
        doc.add_paragraph()
    for a, b in [(T("Localização"), f"{num(cfg.lat, 4)}, {num(cfg.lon, 4)}"),
                 (T("Data do relatório"), _fmt_date(today)),
                 (T("Preços de mercado"), f"{_fmt_date(cfg.prices_start)} – {_fmt_date(cfg.prices_end)}"),
                 (T("Versão"), f"GridForce v{VERSION} ({DATE})")]:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(2)
        r1 = p.add_run(f"{a}: ")
        r1.bold, r1.font.color.rgb = True, MUTED
        p.add_run(b)
    _page_break(doc)

    # ------------------------------------------------ índice
    heading(doc, T("Índice"), 1)
    fin = "TIR do acionista" in m
    toc = [T("1. Resumo do projeto"), T("2. Energia"), T("3. Análise comercial")]
    toc += [T("4. Riscos e sensibilidades"), T("5. Comparação de variantes"), T("Anexo: pressupostos e auditoria")]
    for item in toc:
        para(doc, item, size=11)
    para(doc, "")
    caption(doc, T("Os resultados vêm de uma simulação com previsão perfeita de preços (limite superior económico). "
                   "Os valores \"face à base\" comparam o projeto com o mesmo local sem os novos ativos."))
    _page_break(doc)

    # ------------------------------------------------ 1. resumo
    heading(doc, T("1. Resumo do projeto"), 1)
    gain = m["Ganho 1.º ano face à base (EUR)"]
    para(doc, T("Este relatório apresenta a variante {v} do projeto {p}. No 1.º ano, o projeto melhora o resultado "
                "do local em {g} face à situação sem os novos ativos. Com um investimento de {c}, o VAL a {r} é de "
                "{n} e a TIR é de {i}.").format(v=v.name, p=cfg.name, g=eur(gain), c=eur(m["Capex (EUR)"]),
                                                  r=pct(cfg.discount_rate), n=eur(m["VAL (EUR)"]), i=pct(m["TIR"])))
    heading(doc, T("Indicadores do projeto"), 2)
    pairs = [(T("VAL (NPV)"), eur(m["VAL (EUR)"])), (T("TIR (IRR)"), pct(m["TIR"])),
             (T("Taxa de desconto"), pct(cfg.discount_rate)),
             (T("Payback"), T("n.d.") if _nan(m["Payback (anos)"]) else f"{num(m['Payback (anos)'], 1)} {T('anos')}"),
             (T("Duração do projeto"), f"{cfg.years} {T('anos')} ({cfg.start_year}–{cfg.start_year + cfg.years - 1})"),
             (T("Capex (EUR)"), eur(m["Capex (EUR)"])), (T("Opex (EUR/ano)"), eur(m["Opex (EUR/ano)"])),
             (T("Ganho 1.º ano face à base (EUR)"), eur(gain)), (T("EBITDA 1.º ano (EUR)"), eur(m["EBITDA 1.º ano (EUR)"]))]
    if not _nan(m.get("LCOS (EUR/MWh descarregado)")):
        pairs.append((T("LCOS (EUR/MWh descarregado)"), num(m["LCOS (EUR/MWh descarregado)"], 1)))
    if not _nan(m.get("Custo nivelado do PV e bateria (EUR/MWh PV)")):
        pairs.append((T("Custo nivelado do PV e bateria (EUR/MWh PV)"), num(m["Custo nivelado do PV e bateria (EUR/MWh PV)"], 1)))
    if fin:
        pairs += [(T("TIR do projeto após impostos"), pct(m["TIR do projeto após impostos"])),
                  (T("TIR do acionista"), pct(m["TIR do acionista"])),
                  (T("VAL do acionista (EUR)"), eur(m["VAL do acionista (EUR)"])),
                  (T("DSCR mínimo"), num(m["DSCR mínimo"], 2))]
    kv_table(doc, pairs)

    heading(doc, T("Indicadores de energia (1.º ano)"), 2)
    cons = e1["Consumo (MWh)"]
    pairs = []
    if cons > 0:
        pairs.append((T("Consumo (MWh)"), num(cons)))
        pairs.append((T("Independência da rede"), pct(1 - e1["Importação (MWh)"] / cons)))
    if has_pv:
        pairs += [(T("PV disponível (MWh)"), num(e1["PV disponível (MWh)"])), (T("PV usado (MWh)"), num(e1["PV usado (MWh)"])),
                  (T("Produção específica (kWh/kWp)"), num(1000 * e1["PV disponível (MWh)"] / v.pv_kwp))]
        if not _nan(m.get("Autoconsumo PV (%)")):
            pairs.append((T("Autoconsumo PV (%)"), f"{num(m['Autoconsumo PV (%)'])}%"))
    pairs += [(T("Importação (MWh)"), num(e1["Importação (MWh)"])), (T("Exportação (MWh)"), num(e1["Exportação (MWh)"]))]
    if has_bess:
        pairs += [(T("Descarga bateria (MWh)"), num(e1["Descarga bateria (MWh)"])),
                  (T("Ciclos por dia (1.º ano)"), num(m["Ciclos por dia (1.º ano)"], 2))]
    kv_table(doc, pairs)

    heading(doc, T("Ativos"), 2)
    if has_pv:
        heading(doc, T("Sistema fotovoltaico"), 3)
        sale = (T("Preço fixo (PPA)") + f": {num(cfg.ppa_price_eur_mwh, 2)} EUR/MWh"
                if cfg.ppa_price_eur_mwh is not None else T("Mercado diário OMIE"))
        kv_table(doc, [(T("Potência de pico (kWp)"), num(v.pv_kwp)),
                       (T("Potência do inversor (kW AC)"), num(v.pv_kwp / cfg.pv_dc_ac_ratio)),
                       (T("Montagem PV"), T(cfg.pv_mounting)),
                       (T("Inclinação / azimute"), f"{num(cfg.pv_tilt)}° / {num(cfg.pv_azimuth)}°"
                        if cfg.pv_mounting == "Fixo" else
                        (f"{num(cfg.pv_tilt)}° / -" if "inclinado" in cfg.pv_mounting else "-")),
                       (T("Perdas do sistema"), f"{num(cfg.pv_loss_pct, 1)}%"),
                       (T("Degradação anual"), pct(cfg.pv_degradation_yr, 2)),
                       (T("Venda do excedente"), sale),
                       (T("Capex PV (EUR/kWp)"), num(cfg.pv_capex_eur_kwp, 2)),
                       (T("Opex PV (EUR/kWp/ano)"), num(cfg.pv_opex_eur_kwp_yr, 2))])
    if has_bess:
        heading(doc, T("Bateria"), 3)
        mk = [T(x) for x, on in (("Arbitragem no mercado diário", cfg.arbitrage), ("Mercado intradiário", cfg.intraday),
                                 ("aFRR", cfg.afrr), ("mFRR", cfg.mfrr)) if on]
        kv_table(doc, [(T("Energia (kWh)"), num(v.bess_kwh)), (T("Potência (kW)"), num(v.bess_kw)),
                       (T("Duração (h)"), num(v.bess_kwh / v.bess_kw, 1)),
                       (T("Eficiência de ida e volta"), pct(cfg.bess_rte, 0)),
                       (T("Estado de carga mínimo / máximo"), f"{pct(cfg.bess_soc_min, 0)} / {pct(cfg.bess_soc_max, 0)}"),
                       (T("Degradação"), T("Por ciclos e calendário") if cfg.bess_deg_mode == "ciclos"
                        else f"{pct(cfg.bess_degradation_yr, 1)} {T('por ano')}"),
                       (T("Limite de ciclos por dia"), num(cfg.bess_max_cycles_day, 1) if cfg.bess_max_cycles_day else T("sem limite")),
                       (T("Mercados"), ", ".join(mk) or "–"),
                       (T("Capex bateria (EUR/kWh)"), num(cfg.bess_capex_eur_kwh, 2)),
                       (T("Opex bateria (EUR/kWh/ano)"), num(cfg.bess_opex_eur_kwh_yr, 2))])
    _page_break(doc)

    # ------------------------------------------------ 2. energia
    heading(doc, T("2. Energia"), 1)
    heading(doc, T("Balanço de energia do 1.º ano"), 2)
    rows = []
    for k in e1:
        a, b = eb.get(k, 0.0), e1[k]
        if abs(a) < 1e-6 and abs(b) < 1e-6:
            continue
        ch = T("n.d.") if abs(a) < 1e-9 else f"{num(100 * (b - a) / abs(a), 1)}%"
        nd = 2 if k.endswith("(MW)") else 0
        rows.append([T(k), num(a, nd), num(b, nd), ch])
    table(doc, [T("Grandeza"), T("Base"), T("Projeto"), T("Variação")], rows, widths=[7.5, 3, 3, 2.5])
    if r.flows_y1:
        heading(doc, T("Fluxos de energia entre ativos"), 2)
        table(doc, [T("Fluxo"), T("MWh no 1.º ano")],
              [[T(k), num(x, 0)] for k, x in r.flows_y1.items() if abs(x) > 1e-6], widths=[8, 4])
    if r.emissions is not None:
        em = r.emissions["Emissões evitadas (t CO2)"]
        para(doc, T("Emissões evitadas face à base: {a} t CO2 no 1.º ano e {b} t CO2 ao longo do projeto "
                    "(fator da rede {f} g CO2/kWh).").format(a=num(em.iloc[0], 0), b=num(em.sum(), 0),
                                                             f=num(cfg.emission_factor_g_kwh, 0)))
    heading(doc, T("Perfil mensal de energia"), 2)
    figure(doc, _monthly_chart(r.dispatch_y1))
    caption(doc, T("Energia por mês no 1.º ano, em MWh."))
    heading(doc, T("Perfil diário médio"), 2)
    figure(doc, _daily_chart(r.dispatch_y1))
    caption(doc, T("Potência média em cada hora do dia ao longo do 1.º ano, em kW."))
    _page_break(doc)

    # ------------------------------------------------ 3. análise comercial
    heading(doc, T("3. Análise comercial"), 1)
    heading(doc, T("Value stack do 1.º ano"), 2)
    y1 = r.yearly_streams.iloc[0]
    rows, srows, tb, tp_ = [], [], 0.0, 0.0
    for k, val in y1.items():
        b = res.baseline_streams.get(k, 0.0)
        if abs(val) < 1 and abs(b) < 1:
            continue
        rows.append([T(k), num(b), num(val), num(val - b)])
        tb, tp_ = tb + b, tp_ + val
        if abs(val - b) > 1:
            srows.append((T(k), val - b))
    rows.append([T("Total"), num(tb), num(tp_), num(tp_ - tb)])
    table(doc, [T("Fonte de valor (EUR)"), T("Base"), T("Projeto"), T("Variação")], rows,
          widths=[7.5, 3, 3, 2.5], total_last=True)
    caption(doc, T("Receitas com sinal positivo e custos com sinal negativo, em EUR, no 1.º ano."))
    if srows:
        figure(doc, _stack_chart(srows))
        caption(doc, T("Contributo de cada fonte de valor para o ganho do 1.º ano face à base."))

    heading(doc, T("Cashflow descontado acumulado"), 2)
    figure(doc, _cum_chart(res, vname))
    caption(doc, T("Cashflow do projeto face à base, descontado à taxa de {r} e acumulado, para todas as variantes. "
                   "A variante deste relatório está assinalada com ◄.").format(r=pct(cfg.discount_rate)))

    heading(doc, T("Custos de investimento e de operação"), 2)
    rows = []
    if v.capex_eur is not None:
        rows.append([T("Capex total da variante (valor indicado)"), "1", eur(v.capex_eur), eur(v.capex_eur)])
    else:
        if has_pv:
            rows.append([T("Sistema fotovoltaico"), f"{num(v.pv_kwp)} kWp", f"{num(cfg.pv_capex_eur_kwp, 2)} EUR/kWp",
                         eur(v.pv_kwp * cfg.pv_capex_eur_kwp)])
        if v.bess_kwh:
            rows.append([T("Bateria"), f"{num(v.bess_kwh)} kWh", f"{num(cfg.bess_capex_eur_kwh, 2)} EUR/kWh",
                         eur(v.bess_kwh * cfg.bess_capex_eur_kwh)])
    if getattr(cfg, "licensing_capex_eur", 0.0):
        rows.append([T("Licenciamento e ligação à rede"), "1", eur(cfg.licensing_capex_eur), eur(cfg.licensing_capex_eur)])
    if cfg.other_capex_eur:
        rows.append([T("Outros custos de investimento"), "1", eur(cfg.other_capex_eur), eur(cfg.other_capex_eur)])
    rows.append([T("Capex total"), "", "", eur(m["Capex (EUR)"])])
    table(doc, [T("Componente"), T("Quantidade"), T("Preço unitário"), T("Total")], rows,
          widths=[6.5, 3, 3.5, 3], total_last=True)
    rows = []
    if has_pv and cfg.pv_opex_eur_kwp_yr:
        rows.append([T("Opex PV"), f"{num(v.pv_kwp)} kWp", f"{num(cfg.pv_opex_eur_kwp_yr, 2)} EUR/kWp", eur(v.pv_kwp * cfg.pv_opex_eur_kwp_yr)])
    if v.bess_kwh and cfg.bess_opex_eur_kwh_yr:
        rows.append([T("Opex bateria"), f"{num(v.bess_kwh)} kWh", f"{num(cfg.bess_opex_eur_kwh_yr, 2)} EUR/kWh",
                     eur(v.bess_kwh * cfg.bess_opex_eur_kwh_yr)])
    if cfg.om_eur_yr:
        rows.append([T("O&M fixo"), "365 " + T("dias"), f"{num(cfg.om_eur_yr / 365, 2)} EUR/{T('dia')}", eur(cfg.om_eur_yr)])
    if cfg.insurance_eur_yr:
        rows.append([T("Seguro"), "365 " + T("dias"), f"{num(cfg.insurance_eur_yr / 365, 2)} EUR/{T('dia')}", eur(cfg.insurance_eur_yr)])
    if rows:
        rows.append([T("Opex do 1.º ano"), "", "", eur(m["Opex (EUR/ano)"])])
        table(doc, [T("Custo anual"), T("Quantidade"), T("Preço unitário"), T("Total")], rows,
              widths=[6.5, 3, 3.5, 3], total_last=True)
    rt = getattr(res, "rates", None)
    if rt is not None and len(rt):
        heading(doc, T("Preços aplicados por ano"), 2)
        ycols = [c for c in rt.columns if isinstance(c, (int, np.integer))]
        pick = sorted({ycols[0], ycols[min(4, len(ycols) - 1)], ycols[min(9, len(ycols) - 1)], ycols[-1]})
        table(doc, [T("Item"), T("Unidade")] + [str(y) for y in pick],
              [[T(x["Item"]), x["Unidade"]] + [num(x[y], 2) for y in pick] for _, x in rt.iterrows()],
              widths=[6, 2.5] + [2] * len(pick))
        caption(doc, T("Preços médios de mercado e custos aplicados, com escalada, ajustes e comissões. "
                       "A tabela completa, ano a ano, está no Excel (folha Preços por ano)."))
    if m.get("Augmentation e substituições (EUR)"):
        para(doc, T("Reposição de capacidade e substituições ao longo do projeto: {x}.").format(
            x=eur(m["Augmentation e substituições (EUR)"])))

    if r.annual is not None:
        heading(doc, T("Contas anuais"), 2)
        a = r.annual
        cols = ["Receitas líquidas face à base", "Opex", "EBITDA", "Capex", "Augmentation e substituições",
                "Valor residual", "Cashflow"]
        if fin:
            cols += ["Imposto (IRC)", "Juros", "Cashflow do acionista", "DSCR"]
        cols = [c for c in cols if c in a and (c in ("EBITDA", "Cashflow", "Capex") or a[c].fillna(0).abs().sum() > 0)]
        rows = []
        for y, row in a.iterrows():
            rows.append([str(y)] + [("" if _nan(row[c]) else num(row[c], 2)) if c == "DSCR" else num(row[c]) for c in cols])
        tot = [T("Total")] + ["" if c == "DSCR" else num(a[c].sum()) for c in cols]
        rows.append(tot)
        table(doc, [T("Ano")] + [T(c) for c in cols], rows, size=7 if len(cols) > 7 else 8, total_last=True)
        caption(doc, T("Valores em EUR, face à base. O ano {y} é o do investimento.").format(y=cfg.start_year - 1))

    if fin:
        heading(doc, T("Financiamento e impostos"), 2)
        kv_table(doc, [(T("Dívida (EUR)"), eur(m["Dívida (EUR)"])), (T("Taxa de juro"), pct(cfg.debt_rate, 2)),
                       (T("Prazo"), f"{cfg.debt_tenor} {T('anos')}"),
                       (T("Tipo de reembolso"), T("Prestação constante") if cfg.debt_kind == "anuidade" else T("Amortização constante")),
                       (T("Taxa de IRC"), pct(cfg.tax_rate)), (T("Amortização fiscal"), f"{cfg.dep_years} {T('anos')}"),
                       (T("VAL do projeto após impostos (EUR)"), eur(m["VAL do projeto após impostos (EUR)"])),
                       (T("TIR do projeto após impostos"), pct(m["TIR do projeto após impostos"])),
                       (T("TIR do acionista"), pct(m["TIR do acionista"])),
                       (T("VAL do acionista (EUR)"), eur(m["VAL do acionista (EUR)"])),
                       (T("DSCR mínimo"), num(m["DSCR mínimo"], 2)), (T("DSCR médio"), num(m["DSCR médio"], 2))])
    _page_break(doc)

    # ------------------------------------------------ 4. riscos
    heading(doc, T("4. Riscos e sensibilidades"), 1)
    if r.parts is not None:
        tor = sens.tornado(r.parts, sens_pct, capex_pct)
        para(doc, T("Cada fator varia sozinho, com o despacho do caso base. Os outros ficam como no caso base. "
                    "VAL do caso base: {n}.").format(n=eur(tor.attrs["base_npv"])))
        figure(doc, _tornado_chart(tor))
        rows = [[T(f), num(lo), num(hi), pct(tl), pct(th)] for f, lo, hi, tl, th in
                tor[["Fator", "VAL com fator a descer (EUR)", "VAL com fator a subir (EUR)",
                     "TIR com fator a descer", "TIR com fator a subir"]].itertuples(index=False)]
        table(doc, [T("Fator"), T("VAL a descer (EUR)"), T("VAL a subir (EUR)"), T("TIR a descer"), T("TIR a subir")],
              rows, widths=[6.5, 3, 3, 2, 2], size=8)
    if price_scen:
        heading(doc, T("Cenários com preços de anos anteriores (P90 / P50 / P10)"), 2)
        para(doc, T("Simula o 1.º ano com os preços de cada um dos últimos anos e sorteia, para cada ano do projeto, "
                    "um desses anos. P90 é o valor excedido em 90% dos casos (o mais prudente)."))
        table(doc, [T("Cenário"), T("VAL (EUR)"), T("TIR")],
              [[p_, num(price_scen[f"{p_} VAL (EUR)"]), pct(price_scen[f"{p_} TIR"])] for p_ in ("P90", "P50", "P10")],
              widths=[5, 5, 4])
        pa = price_scen.get("por_ano")
        if pa is not None and len(pa):
            table(doc, [T("Preços"), T("Ganho 1.º ano face à base (EUR)"), T("VAL se todos os anos fossem assim (EUR)"), T("TIR")],
                  [[T(a_), num(b_), num(c_), pct(d_)] for a_, b_, c_, d_ in pa.itertuples(index=False)],
                  widths=[4, 4, 5, 2.5], size=8)
    else:
        caption(doc, T("Os cenários de preços P90 / P50 / P10 entram no relatório quando são corridos na aplicação "
                       "antes de o descarregar."))

    # ------------------------------------------------ 5. variantes
    heading(doc, T("5. Comparação de variantes"), 1)
    rows = []
    for x in res.variants:
        mm = x.metrics
        rows.append([x.variant.name + (" ◄" if x.variant.name == vname else ""), num(mm["PV (kWp)"]), num(mm["BESS (kWh)"]),
                     num(mm["BESS (kW)"]), num(mm["Capex (EUR)"]), num(mm["Ganho 1.º ano face à base (EUR)"]),
                     num(mm["VAL (EUR)"]), pct(mm["TIR"]),
                     T("n.d.") if _nan(mm["Payback (anos)"]) else num(mm["Payback (anos)"], 1)])
    table(doc, [T("Variante"), T("PV (kWp)"), T("BESS (kWh)"), T("BESS (kW)"), T("Capex (EUR)"),
                T("Ganho 1.º ano (EUR)"), T("VAL (EUR)"), T("TIR"), T("Payback (anos)")], rows, size=7)
    _page_break(doc)

    # ------------------------------------------------ anexo
    heading(doc, T("Anexo: pressupostos e auditoria"), 1)
    heading(doc, T("Pressupostos de modelação"), 2)
    load_src = (T("Diagrama de carga carregado") if cfg.load_kw is not None else
                T("Sem consumo") if cfg.annual_load_mwh <= 0 else
                T("Perfil tipo de centro comercial") + f" ({num(cfg.annual_load_mwh)} MWh/{T('ano')})")
    kv_table(doc, [
        (T("Consumo do local"), load_src),
        (T("Tarifas de acesso"), f"ERSE TAR 2026, {cfg.voltage_level}" if cfg.voltage_level else T("Sem tarifas de acesso")),
        (T("Limite de importação (kW)"), num(cfg.import_limit_kw) if cfg.import_limit_kw < 1e6 else T("sem limite")),
        (T("Limite de exportação (kW)"), num(cfg.export_limit_kw) if cfg.export_limit_kw < 1e6 else T("sem limite")),
        (T("Período de preços"), f"{_fmt_date(cfg.prices_start)} – {_fmt_date(cfg.prices_end)}"),
        (T("Horizonte do despacho"), T("Semana (7 dias)") if cfg.horizon_days == 7 else T("Dia a dia")),
        (T("Previsão de preços"), T("Perfeita (limite superior económico)")),
        (T("Escalada anual de preços"), pct(cfg.price_escalation_yr, 1)),
        (T("Valor residual"), pct(cfg.residual_value_pct, 0)),
        (T("Simulação"), T("Rápida (1.º e último ano, restantes interpolados)") if cfg.fast else T("Completa (todos os anos)")),
    ])
    if cfg.afrr or cfg.mfrr:
        pairs = []
        if cfg.afrr:
            pairs += [(T("Taxa de ativação aFRR"), pct(cfg.afrr_act_rate, 0)),
                      (T("Horas com oferta aceite aFRR"), pct(cfg.afrr_acceptance, 0)),
                      (T("Ajuste dos preços de capacidade aFRR"), num(cfg.afrr_cap_scale, 2))]
        if cfg.mfrr:
            pairs += [(T("Ativação mFRR a subir / descer"), f"{pct(cfg.mfrr_up_act_rate, 0)} / {pct(cfg.mfrr_dn_act_rate, 0)}")]
        if cfg.bsp_fee_pct:
            pairs.append((T("Comissão do agregador (BSP)"), pct(cfg.bsp_fee_pct, 1)))
        kv_table(doc, pairs)
    if res.audit:
        heading(doc, T("Auditoria da execução"), 2)
        table(doc, [T("Verificação"), T("Valor")],
              [[T(k), T("Sim") if val is True else T("Não") if val is False else str(val)] for k, val in res.audit.items()],
              widths=[8.5, 7.5], size=8)
    heading(doc, T("Notas"), 2)
    for txt in [
        T("O despacho da bateria é otimizado com previsão perfeita dos preços, por isso os ganhos de mercado são um "
          "limite superior. Na operação real, com previsões, ficam tipicamente abaixo."),
        T("Os preços de mercado vêm do OMIE (diário e intradiário) e da ENTSO-E (aFRR e mFRR) para o período indicado, "
          "e repetem-se nos anos seguintes com a escalada definida."),
        T("Produção fotovoltaica estimada com dados PVGIS (Comissão Europeia) para a localização do projeto."),
    ]:
        doc.add_paragraph(txt, style="List Bullet")
    doc.save(buf)


# ---------------------------------------------------------------- guia rápido em Word

GUIDE_DIR = Path(__file__).resolve().parent.parent / "docs"


def guide_markdown() -> str:
    """Texto do guia rápido na língua ativa."""
    f = GUIDE_DIR / f"guia_{'en' if i18n.LANG == 'en' else 'pt'}.md"
    return f.read_text(encoding="utf-8") if f.exists() else ""


def _md_runs(p, text: str) -> None:
    import re
    for k, part in enumerate(re.split(r"\*\*(.+?)\*\*", text)):
        if part:
            p.add_run(part).bold = k % 2 == 1


def guide_docx(buf, md: str | None = None) -> None:
    """Converte o guia (Markdown simples: títulos, listas, negrito) num documento Word com o logótipo."""
    import re
    md = guide_markdown() if md is None else md
    doc = Document()
    sec = doc.sections[0]
    sec.page_height, sec.page_width = Cm(29.7), Cm(21.0)
    sec.left_margin = sec.right_margin = Cm(2.2)
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(10.5)
    doc.styles["Title"].font.color.rgb = DARK
    if LOGO.exists():
        doc.add_picture(str(LOGO), width=Cm(4.5))
    for line in md.splitlines():
        s = line.rstrip()
        if not s:
            continue
        if s.startswith("# "):
            heading(doc, s[2:], 0)
        elif s.startswith("## "):
            heading(doc, s[3:], 1)
        elif s.startswith("- "):
            _md_runs(doc.add_paragraph(style="List Bullet"), s[2:])
        elif re.match(r"^\d+\. ", s):
            _md_runs(doc.add_paragraph(style="List Number"), s.split(". ", 1)[1])
        else:
            _md_runs(doc.add_paragraph(), s)
    p = doc.add_paragraph()
    rr = p.add_run(f"GridForce v{VERSION} ({DATE})")
    rr.font.size, rr.font.color.rgb = Pt(8), MUTED
    doc.save(buf)
