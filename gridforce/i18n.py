"""Tradução da interface (português -> inglês).

O português é a língua de origem: os ficheiros de projeto, os nomes internos e as chaves dos
resultados ficam sempre em português. Só o que se mostra no ecrã (e nos Excel descarregados)
é traduzido, por isso trocar de língua não altera nenhum projeto guardado.
"""
from __future__ import annotations

import io
import re

import pandas as pd

LANG = "pt"


def set_lang(lang: str) -> None:
    global LANG
    LANG = "en" if str(lang).lower().startswith("en") else "pt"


def T(s):
    """Traduz um texto (ou devolve-o como está se não houver tradução ou se a língua for português)."""
    if not isinstance(s, str):
        return s
    if LANG == "pt":
        return PT.get(s, s)
    if s in EN:
        return EN[s]
    # "Nome: detalhe" (ex.: chaves de auditoria com o nome da variante)
    if ": " in s:
        a, b = s.split(": ", 1)
        if a in EN:
            return f"{EN[a]}: {b}"
    # "Fator ±20%" do gráfico de sensibilidades
    m = re.match(r"^(.*) (±\d+%)$", s)
    if m and m.group(1) in EN:
        return f"{EN[m.group(1)]} {m.group(2)}"
    # nomes de folhas Excel "Anual X" / "Despacho X"
    for pt, en in (("Anual ", "Annual "), ("Despacho ", "Dispatch ")):
        if s.startswith(pt):
            return en + s[len(pt):]
    # "Preços de 11/2025 a 10/2026"
    m = re.match(r"^(\d\d/\d{4}) a (\d\d/\d{4})$", s)
    if m:
        return f"{m.group(1)} to {m.group(2)}"
    return s


def TP(msg: str) -> str:
    """Mensagens de progresso do motor ("Variante: ano 2029")."""
    return msg if LANG == "pt" else msg.replace(": ano ", ": year ").replace("Preços de ", "Prices ").replace(
        "Cenários concluídos", "Scenarios done")


def TF(fmt: dict) -> dict:
    """Traduz as chaves de um dicionário de formatos de colunas."""
    return {T(k): v for k, v in fmt.items()}


def TD(df):
    """Cópia de uma tabela com colunas e índice traduzidos."""
    if LANG == "pt":
        return df
    out = df.copy()
    out.columns = [T(c) for c in out.columns]
    if not pd.api.types.is_numeric_dtype(out.index):
        out.index = [T(i) if isinstance(i, str) else i for i in out.index]
    return out


def translate_xlsx(data: bytes) -> bytes:
    """Traduz os textos e os nomes das folhas de um Excel gerado pela GridForce."""
    if LANG == "pt":
        return data
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(data))
    for ws in wb.worksheets:
        ws.title = T(ws.title)[:31]
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str):
                    c.value = T(c.value)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# Nomes mostrados em português diferentes do valor guardado nos projetos (o valor guardado não muda,
# para os projetos antigos continuarem a abrir)
PT = {
    "Perfil tipo de centro comercial": "Perfil tipo C&I",
}

EN = {
    # ambientes e versões
    "Palavra-passe": "Password", "Palavra-passe errada.": "Wrong password.",
    "AMBIENTE DE QUALIDADE (testes). Os resultados e projetos daqui não são os de Produção.":
        "QUALITY ENVIRONMENT (testing). Results and projects here are not the Production ones.",
    "Qualidade": "Quality", "Produção": "Production", "Histórico de versões": "Version history",
    # cabeçalho e biblioteca
    "Dimensionamento e simulação de PV e baterias em Portugal: autoconsumo, mercados diário e intradiário OMIE e serviços de sistema (aFRR, mFRR).":
        "Sizing and simulation of PV and batteries in Portugal: self-consumption, OMIE day-ahead and intraday markets and balancing services (aFRR, mFRR).",
    "Biblioteca de projetos": "Project library",
    "Projetos guardados e partilhados com a equipa. Não se perdem ao atualizar a página.":
        "Projects saved and shared with the team. They are kept when the page is refreshed.",
    "A biblioteca partilhada ainda não está ligada: os projetos guardados aqui só duram até a aplicação reiniciar.":
        "The shared library is not connected yet: projects saved here only last until the app restarts.",
    "Não foi possível ler a biblioteca: {e}": "Could not read the library: {e}",
    "A chave de acesso à biblioteca expira dentro de {d} dias. Crie uma nova no GitHub (GridForce biblioteca, Regenerate token) e atualize-a nos Secrets do Streamlit.":
        "The library access key expires in {d} days. Create a new one on GitHub (GridForce biblioteca, Regenerate token) and update it in the Streamlit Secrets.",
    "Projetos da biblioteca a abrir": "Library projects to open",
    "Selecionar todos": "Select all",
    "{fn}: não foi possível abrir ({e})": "{fn}: could not open ({e})",
    "Ou carregar ficheiros de projeto (.json) do computador": "Or upload project files (.json) from your computer",
    "{fn}: ficheiro inválido ({e})": "{fn}: invalid file ({e})",
    "Guardar {n} ficheiro(s) carregado(s) na biblioteca": "Save {n} uploaded file(s) to the library",
    "Guardado na biblioteca.": "Saved to the library.",
    "Não foi possível guardar: {e}": "Could not save: {e}",
    "Apagar da biblioteca": "Delete from library",
    "Apaga os projetos selecionados acima. Não se pode desfazer.": "Deletes the projects selected above. This cannot be undone.",
    "Apagar {n} projeto(s)": "Delete {n} project(s)",
    "Projeto a mostrar nos separadores": "Project shown in the tabs",
    "{n} projeto(s) carregado(s). Os separadores mostram: {p}.": "{n} project(s) loaded. The tabs show: {p}.",
    "Correr os {n} projetos": "Run the {n} projects",
    "A preparar...": "Preparing...",
    "{nm}: a simulação falhou ({e})": "{nm}: the simulation failed ({e})",
    "Concluído": "Done",
    "Resultados no separador 5.": "Results in tab 5.",
    # separadores
    "1. Local e consumo": "1. Site and load", "2. PV e bateria": "2. PV and battery",
    "3. Mercados, tarifas e finanças": "3. Markets, tariffs and finance", "4. Variantes": "4. Variants",
    "5. Resultados": "5. Results",
    "Passos do projeto": "Project steps",
    # separador 1
    "Nome do projeto": "Project name", "Latitude": "Latitude", "Longitude": "Longitude",
    "Consumo do local": "Site load", "Perfil tipo de centro comercial": "Typical C&I profile",
    "Carregar diagrama de carga (CSV)": "Upload load profile (CSV)",
    "Sem consumo (parque de produção e armazenamento)": "No load (generation and storage park)",
    "Consumo anual (MWh)": "Annual consumption (MWh)",
    "CSV com uma coluna de potência em kW (35 040 linhas de 15 min ou 8 760 horárias)":
        "CSV with one power column in kW (35,040 rows of 15 min or 8,760 hourly)",
    "A usar o diagrama de carga guardado no projeto ({x} MWh/ano).": "Using the load profile saved in the project ({x} MWh/year).",
    "{n} intervalos, {e} MWh/ano, ponta {p} kW": "{n} intervals, {e} MWh/year, peak {p} kW",
    "Limite de importação (kW, 0 = sem limite)": "Import limit (kW, 0 = no limit)",
    "Limite de injeção na rede (kW, 0 = sem limite)": "Export limit (kW, 0 = no limit)",
    # separador 2
    "PV": "PV", "Inclinação (°)": "Tilt (°)", "Azimute (°, 180 = sul)": "Azimuth (°, 180 = south)",
    "Perdas do sistema (%)": "System losses (%)", "Rácio DC/AC do inversor": "Inverter DC/AC ratio",
    "Degradação anual (%)": "Annual degradation (%)", "Capex PV (EUR/kWp)": "PV capex (EUR/kWp)",
    "Opex PV (EUR/kWp/ano)": "PV opex (EUR/kWp/year)", "Bateria": "Battery",
    "Eficiência round-trip (%)": "Round-trip efficiency (%)", "Janela de SOC (%)": "SOC window (%)",
    "Perda de capacidade anual (%)": "Annual capacity loss (%)",
    "Custo de desgaste (EUR/MWh descarregado)": "Wear cost (EUR/MWh discharged)",
    "Máximo de ciclos por dia (0 = sem limite)": "Maximum cycles per day (0 = no limit)",
    "Média por semana, contando também a energia das ativações aFRR/mFRR. Garantias típicas: 1 a 2 ciclos por dia.":
        "Weekly average, including aFRR/mFRR activation energy. Typical warranties: 1 to 2 cycles per day.",
    "Capex bateria (EUR/kWh)": "Battery capex (EUR/kWh)", "Opex bateria (EUR/kWh/ano)": "Battery opex (EUR/kWh/year)",
    "Mais parâmetros da bateria": "More battery parameters",
    "Eficiência de carga (%, 0 = usar a round-trip)": "Charge efficiency (%, 0 = use round-trip)",
    "Eficiência de descarga (%, 0 = usar a round-trip)": "Discharge efficiency (%, 0 = use round-trip)",
    "Disponibilidade técnica (%)": "Technical availability (%)",
    "Consumos auxiliares (kW por MW de bateria)": "Auxiliary consumption (kW per MW of battery)",
    "AVAC, controlo, transformador. Típico: 5 a 15 kW/MW.": "HVAC, controls, transformer. Typical: 5 to 15 kW/MW.",
    "Degradação, fim de vida e substituições": "Degradation, end of life and replacements",
    "Linear (% por ano)": "Linear (% per year)", "Por ciclos e calendário": "Cycles and calendar",
    "Modelo de degradação": "Degradation model",
    "Linear usa a 'Perda de capacidade anual'. Por ciclos soma a perda de calendário e a perda por ciclo equivalente, com os ciclos que a simulação faz.":
        "Linear uses the 'Annual capacity loss'. Cycles and calendar adds the calendar loss and the loss per equivalent cycle, using the cycles from the simulation.",
    "Perda por calendário (%/ano)": "Calendar loss (%/year)",
    "Perda por ciclo equivalente (%)": "Loss per equivalent cycle (%)",
    "Fim de vida (% da capacidade inicial)": "End of life (% of initial capacity)",
    "Repor capacidade no fim de vida (augmentation)": "Restore capacity at end of life (augmentation)",
    "Custo da reposição (EUR por kWh reposto)": "Augmentation cost (EUR per kWh restored)",
    "Ano de substituição do PCS (0 = não)": "PCS replacement year (0 = none)",
    "Custo da substituição do PCS (EUR/kW)": "PCS replacement cost (EUR/kW)",
    # separador 3
    "Mercados": "Markets", "Preços OMIE: últimos 12 meses até": "OMIE prices: 12 months up to",
    "Arbitragem no mercado diário (carregar da rede para vender)": "Day-ahead arbitrage (charge from the grid to sell)",
    "Banda de regulação secundária (aFRR)": "Secondary reserve (aFRR)",
    "Precisa da chave ENTSO-E (variável ENTSOE_TOKEN).": "Needs the ENTSO-E key (ENTSOE_TOKEN variable).",
    "Taxa de ativação aFRR (%)": "aFRR activation rate (%)", "Duração mínima da reserva (h)": "Minimum reserve duration (h)",
    "Ofertas aceites (%)": "Accepted bids (%)",
    "Percentagem das horas em que a oferta de reserva é aceite. A GridCog usa 50%.":
        "Share of hours in which the reserve bid is accepted. GridCog uses 50%.",
    "Ajuste dos preços de capacidade aFRR (%)": "aFRR capacity price adjustment (%)",
    "100% = preços da ENTSO-E dos últimos 12 meses. Ex.: 300% para usar preços 3 vezes maiores.":
        "100% = ENTSO-E prices of the last 12 months. E.g. 300% to use prices 3 times higher.",
    "Mercado intradiário contínuo": "Continuous intraday market",
    "A bateria compra e vende ao melhor preço entre o diário e o intradiário (OMIE).":
        "The battery buys and sells at the better price of day-ahead and intraday (OMIE).",
    "Vantagem do intradiário capturada (%)": "Intraday advantage captured (%)",
    "Com previsão perfeita, escolher sempre o melhor mercado sobrestima o ganho.":
        "With perfect foresight, always picking the best market overstates the gain.",
    "Reserva de substituição manual (mFRR)": "Manual frequency restoration reserve (mFRR)",
    "Só energia ativada, a preços da ENTSO-E. Precisa da chave ENTSOE_TOKEN.":
        "Activated energy only, at ENTSO-E prices. Needs the ENTSOE_TOKEN key.",
    "Ativação mFRR a subir (%)": "mFRR upward activation (%)", "Ativação mFRR a descer (%)": "mFRR downward activation (%)",
    "Tarifas": "Tariffs", "Nível de tensão (tarifa de acesso ERSE)": "Voltage level (ERSE network tariff)",
    "Sem tarifas de acesso": "No network tariffs",
    "Outros custos na compra (EUR/MWh)": "Other purchase costs (EUR/MWh)",
    "Margem do comercializador, CIEG, imposto especial de consumo, etc.": "Supplier margin, CIEG, excise duty, etc.",
    "Comissão na venda (EUR/MWh)": "Sales fee (EUR/MWh)", "Venda da energia PV injetada": "Sale of exported PV energy",
    "Mercado diário OMIE": "OMIE day-ahead market", "Preço fixo (PPA)": "Fixed price (PPA)",
    "Com preço fixo, a energia PV injetada diretamente é paga a esse preço; a bateria continua a vender no mercado.":
        "With a fixed price, PV energy exported directly is paid at that price; the battery still sells in the market.",
    "Preço fixo no 1.º ano (EUR/MWh)": "Fixed price in year 1 (EUR/MWh)",
    "Aumento anual do preço fixo (EUR/MWh por ano)": "Annual increase of the fixed price (EUR/MWh per year)",
    "Finanças": "Finance", "Ano de início": "Start year", "Duração (anos)": "Lifetime (years)",
    "Taxa de desconto (%)": "Discount rate (%)",
    "Modo rápido (simula 1.º e último ano e interpola)": "Fast mode (simulates first and last year and interpolates)",
    "Horizonte do despacho": "Dispatch horizon", "Semana (previsão perfeita)": "Week (perfect foresight)",
    "Dia a dia (mais realista)": "Day by day (more realistic)",
    "Dia a dia: a bateria só conhece os preços do dia seguinte, como no mercado diário real, e volta ao estado de carga inicial no fim de cada dia.":
        "Day by day: the battery only knows the next day's prices, as in the real day-ahead market, and returns to its initial state of charge at the end of each day.",
    "Outros custos do projeto": "Other project costs", "Capex adicional (EUR)": "Additional capex (EUR)",
    "Licenciamento, ligação à rede, desenvolvimento...": "Permitting, grid connection, development...",
    "O&M no 1.º ano (EUR/ano)": "O&M in year 1 (EUR/year)", "Crescimento anual do O&M (%)": "Annual O&M growth (%)",
    "Seguro no 1.º ano (EUR/ano)": "Insurance in year 1 (EUR/year)",
    "Variação anual do seguro (% do valor inicial)": "Annual insurance change (% of initial value)",
    "Linear. Ex.: -2 reduz o seguro 2% do valor inicial por ano.": "Linear. E.g. -2 lowers insurance by 2% of the initial value per year.",
    "Comissão do agregador/BSP (% das receitas de serviços de sistema)": "Aggregator/BSP fee (% of balancing revenue)",
    "Escalada anual dos preços de mercado (%)": "Annual market price escalation (%)",
    "Aplica-se a mercados, serviços de sistema e tarifas. O preço fixo (PPA) tem o seu próprio aumento.":
        "Applies to markets, balancing services and tariffs. The fixed price (PPA) has its own increase.",
    "Valor residual no fim (% do capex)": "Residual value at the end (% of capex)",
    "Financiamento e impostos": "Financing and taxes",
    "Com imposto e dívida a zero, o caso é antes de impostos e só com capital próprio (como a GridCog).":
        "With tax and debt at zero, the case is pre-tax and all-equity (as in GridCog).",
    "Imposto sobre lucros, IRC + derrama (%)": "Corporate income tax, IRC + municipal surcharge (%)",
    "Amortização fiscal do capex (anos)": "Tax depreciation of capex (years)", "Dívida (% do capex)": "Debt (% of capex)",
    "Taxa de juro da dívida (%)": "Debt interest rate (%)", "Prazo da dívida (anos)": "Debt tenor (years)",
    "Reembolso": "Repayment", "Prestação constante (anuidade)": "Constant instalment (annuity)",
    "Amortização constante": "Constant principal",
    "DSCR mínimo exigido (0 = sem limite)": "Minimum required DSCR (0 = no limit)",
    "Se definido, a dívida é reduzida até cada ano ter pelo menos este DSCR.":
        "If set, the debt is reduced until every year has at least this DSCR.",
    "Custo do capital próprio (%)": "Cost of equity (%)",
    # separador 4 e botões
    "Cada linha é uma variante a comparar. Adiciona ou apaga linhas à vontade. Se preencheres o capex total, substitui o cálculo por EUR/kWp e EUR/kWh.":
        "Each row is a variant to compare. Add or delete rows freely. If you fill in the total capex, it replaces the EUR/kWp and EUR/kWh calculation.",
    "Variante": "Variant", "Variante ": "Variant ", "Variante  ": "Variant  ", "Capex total (EUR)": "Total capex (EUR)",
    "Correr simulação": "Run simulation", "Guardar projeto na biblioteca": "Save project to library",
    "Guardado como {fn}. Se já existia com este nome, foi substituído.": "Saved as {fn}. If it already existed with this name, it was replaced.",
    "Descarregar projeto (.json)": "Download project (.json)",
    "A preparar dados de mercado e PV...": "Preparing market and PV data...", "A simulação falhou: {e}": "The simulation failed: {e}",
    # resultados
    "Carteira de projetos": "Project portfolio", "Projeto": "Project", "Capex total": "Total capex",
    "VAL total (NPV)": "Total NPV", "Ganho total 1.º ano": "Total year-1 gain",
    "Descarregar carteira (Excel)": "Download portfolio (Excel)",
    "Para ver gráficos e despacho de um projeto, escolhe-o em cima e carrega em Correr simulação.":
        "To see charts and dispatch for a project, pick it above and press Run simulation.",
    "Preenche os separadores 1 a 4 e carrega em **Correr simulação**.": "Fill in tabs 1 to 4 and press **Run simulation**.",
    "Melhor variante (maior VAL / NPV)": "Best variant (highest NPV)", "VAL (NPV)": "NPV",
    "Valor Atual Líquido, em inglês Net Present Value (NPV), à taxa de desconto do separador 3.":
        "Net Present Value at the discount rate in tab 3.",
    "TIR (IRR)": "IRR", "Payback": "Payback", "anos": "years", "n.d.": "n/a",
    "Resumo das variantes": "Variant summary", "Value stack, 1.º ano, face à base": "Value stack, year 1, vs baseline",
    "Fonte de valor": "Value stream", "Cashflow descontado acumulado": "Cumulative discounted cashflow",
    "Despacho num dia": "Dispatch on one day", "Dia": "Day", "Consumo": "Load", "PV usado": "PV used",
    "Bateria (+descarga / -carga)": "Battery (+discharge / -charge)",
    "Rede, mercado (+import / -export)": "Grid, market (+import / -export)",
    "Rede, PV a preço fixo": "Grid, PV at fixed price", "Reserva aFRR subir": "aFRR upward reserve",
    "Preço OMIE (EUR/MWh)": "OMIE price (EUR/MWh)", "Contas anuais": "Annual accounts",
    "Riscos e sensibilidades": "Risks and sensitivities",
    "Cada fator varia sozinho, com o despacho do caso base. Os outros ficam como no caso base.":
        "Each factor varies on its own, with the base-case dispatch. The others stay as in the base case.",
    "Variação de receitas e opex (%)": "Revenue and opex variation (%)", "Variação do capex (%)": "Capex variation (%)",
    "Fator a descer": "Factor down", "Fator a subir": "Factor up",
    "**Cenários com preços de anos anteriores (P90 / P50 / P10)**": "**Scenarios with prices from previous years (P90 / P50 / P10)**",
    "Simula o 1.º ano com os preços de cada um dos últimos anos e sorteia, para cada ano do projeto, um desses anos. P90 é o valor excedido em 90% dos casos (o mais prudente).":
        "Simulates year 1 with the prices of each of the last years and draws, for each project year, one of those years. P90 is the value exceeded in 90% of cases (the most prudent).",
    "Anos de preços a usar": "Price years to use", "Correr cenários de preços": "Run price scenarios",
    "A simular anos de preços...": "Simulating price years...", "Os cenários falharam: {e}": "The scenarios failed: {e}",
    "Sem dados para {x}": "No data for {x}", "Casos": "Cases",
    "Auditoria da execução": "Run audit", "Valor": "Value", "Energia no 1.º ano": "Energy in year 1", "Base": "Baseline",
    "Descarregar investment case (Excel)": "Download investment case (Excel)",
    # métricas
    "PV (kWp)": "PV (kWp)", "BESS (kWh)": "BESS (kWh)", "BESS (kW)": "BESS (kW)",
    "Capex (EUR)": "Capex (EUR)", "Opex (EUR/ano)": "Opex (EUR/year)", "VAL (EUR)": "NPV (EUR)", "TIR": "IRR",
    "Payback (anos)": "Payback (years)", "Ganho 1.º ano face à base (EUR)": "Year-1 gain vs baseline (EUR)",
    "Autoconsumo PV (%)": "PV self-consumption (%)", "Importação 1.º ano (MWh)": "Year-1 import (MWh)",
    "EBITDA 1.º ano (EUR)": "Year-1 EBITDA (EUR)",
    "Ganho 1.º ano por MW de bateria (EUR/MW)": "Year-1 gain per MW of battery (EUR/MW)",
    "Ciclos por dia (1.º ano)": "Cycles per day (year 1)", "LCOS (EUR/MWh descarregado)": "LCOS (EUR/MWh discharged)",
    "Estado de saúde no fim (%)": "End-of-life state of health (%)",
    "Augmentation e substituições (EUR)": "Augmentation and replacements (EUR)",
    "Custo nivelado do PV e bateria (EUR/MWh PV)": "Levelised cost of PV and battery (EUR/MWh PV)",
    "TIR do projeto após impostos": "Project IRR after tax",
    "VAL do projeto após impostos (EUR)": "Project NPV after tax (EUR)", "Dívida (EUR)": "Debt (EUR)",
    "TIR do acionista": "Equity IRR", "VAL do acionista (EUR)": "Equity NPV (EUR)",
    "DSCR mínimo": "Minimum DSCR", "DSCR médio": "Average DSCR",
    # contas anuais
    "Receitas líquidas face à base": "Net revenue vs baseline", "Opex": "Opex", "EBITDA": "EBITDA", "Capex": "Capex",
    "Augmentation e substituições": "Augmentation and replacements", "Valor residual": "Residual value",
    "Estado de saúde da bateria (%)": "Battery state of health (%)", "Ciclos equivalentes no ano": "Equivalent cycles in year",
    "Cashflow": "Cashflow", "Imposto (IRC)": "Income tax", "Juros": "Interest",
    "Amortização da dívida": "Debt principal", "DSCR": "DSCR", "Cashflow do acionista": "Equity cashflow",
    # fontes de valor
    "Mercado diário - venda (export)": "Day-ahead - sale (export)", "Mercado diário - compra (import)": "Day-ahead - purchase (import)",
    "Mercado intradiário - venda (export)": "Intraday - sale (export)",
    "Mercado intradiário - compra (import)": "Intraday - purchase (import)",
    "Venda PV a preço fixo (PPA)": "PV sale at fixed price (PPA)",
    "Tarifas de acesso - energia e potência em ponta": "Network tariffs - energy and peak power",
    "Tarifas de acesso - potência contratada": "Network tariffs - contracted power",
    "aFRR subir - capacidade": "aFRR up - capacity", "aFRR descer - capacidade": "aFRR down - capacity",
    "aFRR subir - ativação": "aFRR up - activation", "aFRR descer - ativação": "aFRR down - activation",
    "mFRR subir - ativação": "mFRR up - activation", "mFRR descer - ativação": "mFRR down - activation",
    # energia
    "Consumo (MWh)": "Load (MWh)", "PV disponível (MWh)": "PV available (MWh)", "PV usado (MWh)": "PV used (MWh)",
    "PV cortado (MWh)": "PV curtailed (MWh)", "PV direto para consumo (MWh)": "PV direct to load (MWh)",
    "Importação (MWh)": "Import (MWh)", "Exportação (MWh)": "Export (MWh)",
    "Exportação PV a preço fixo (MWh)": "PV export at fixed price (MWh)",
    "Carga bateria (MWh)": "Battery charge (MWh)", "Descarga bateria (MWh)": "Battery discharge (MWh)",
    "aFRR subir médio (MW)": "Average aFRR up (MW)", "aFRR descer médio (MW)": "Average aFRR down (MW)",
    "mFRR subir médio (MW)": "Average mFRR up (MW)", "mFRR descer médio (MW)": "Average mFRR down (MW)",
    # sensibilidades
    "Fator": "Factor", "VAL com fator a descer (EUR)": "NPV with factor down (EUR)",
    "VAL com fator a subir (EUR)": "NPV with factor up (EUR)", "TIR com fator a descer": "IRR with factor down",
    "TIR com fator a subir": "IRR with factor up", "Capex": "Capex", "Opex": "Opex",
    "Preços de energia (diário e intradiário)": "Energy prices (day-ahead and intraday)", "Preço do PPA": "PPA price",
    "Capacidade aFRR (saturação do mercado)": "aFRR capacity (market saturation)",
    "Ativações aFRR e mFRR": "aFRR and mFRR activations",
    "Preços": "Prices", "VAL se todos os anos fossem assim (EUR)": "NPV if every year were like this (EUR)",
    # auditoria
    "Versão do motor": "Engine version", "Data da execução": "Run date", "Período de preços": "Price period",
    "Hash preços mercado diário": "Day-ahead prices hash", "Hash preços intradiário": "Intraday prices hash",
    "Hash preços aFRR capacidade subir": "aFRR up capacity prices hash",
    "Hash preços mFRR ativação subir": "mFRR up activation prices hash", "Tarifas de acesso": "Network tariffs",
    "Previsão": "Foresight", "Balanço de energia, maior erro (kW)": "Energy balance, largest error (kW)",
    "Limites respeitados": "Limits respected",
    # Excel
    "Pressupostos": "Assumptions", "Resumo": "Summary", "Ano": "Year", "Cashflows por fonte": "Cashflows by stream",
    "Cashflows projeto": "Project cashflows", "Auditoria": "Audit", "Energia 1.º ano": "Energy year 1",
    "Base (sem ativos)": "Baseline (no assets)", "Carteira": "Portfolio", "Fontes de valor": "Value streams",
}

# Relatório Word (gridforce/report.py)
EN.update({
    "RELATÓRIO DA SOLUÇÃO": "SOLUTION REPORT", "Índice": "Contents", "Localização": "Location",
    "Data do relatório": "Report date", "Preços de mercado": "Market prices", "Versão": "Version",
    "1. Resumo do projeto": "1. Project summary", "2. Energia": "2. Energy", "3. Análise comercial": "3. Commercial analysis",
    "4. Riscos e sensibilidades": "4. Risks and sensitivities", "5. Comparação de variantes": "5. Variant comparison",
    "Anexo: pressupostos e auditoria": "Appendix: assumptions and audit",
    "Os resultados vêm de uma simulação com previsão perfeita de preços (limite superior económico). "
    "Os valores \"face à base\" comparam o projeto com o mesmo local sem os novos ativos.":
        "Results come from a simulation with perfect price foresight (economic upper bound). "
        "Values \"vs baseline\" compare the project with the same site without the new assets.",
    "Este relatório apresenta a variante {v} do projeto {p}. No 1.º ano, o projeto melhora o resultado "
    "do local em {g} face à situação sem os novos ativos. Com um investimento de {c}, o VAL a {r} é de "
    "{n} e a TIR é de {i}.":
        "This report presents variant {v} of project {p}. In year 1 the project improves the site's result by {g} "
        "compared with the situation without the new assets. With an investment of {c}, the NPV at {r} is {n} "
        "and the IRR is {i}.",
    "Indicadores do projeto": "Project metrics", "Indicador": "Metric", "Taxa de desconto": "Discount rate",
    "Payback": "Payback", "Duração do projeto": "Project duration", "ano": "year", "por ano": "per year",
    "Indicadores de energia (1.º ano)": "Energy metrics (year 1)", "Independência da rede": "Grid independence",
    "Produção específica (kWh/kWp)": "Specific yield (kWh/kWp)", "Ativos": "Assets",
    "Sistema fotovoltaico": "Solar PV system", "Potência de pico (kWp)": "Peak power (kWp)",
    "Potência do inversor (kW AC)": "Inverter power (kW AC)", "Inclinação / azimute": "Tilt / azimuth",
    "Perdas do sistema": "System losses", "Degradação anual": "Annual degradation", "Venda do excedente": "Surplus sale",
    "Energia (kWh)": "Energy (kWh)", "Potência (kW)": "Power (kW)", "Duração (h)": "Duration (h)",
    "Eficiência de ida e volta": "Round-trip efficiency", "Estado de carga mínimo / máximo": "Minimum / maximum state of charge",
    "Degradação": "Degradation", "Por ciclos e calendário": "By cycles and calendar",
    "Limite de ciclos por dia": "Cycle limit per day", "sem limite": "no limit", "Mercados": "Markets",
    "Arbitragem no mercado diário": "Day-ahead arbitrage", "Mercado intradiário": "Intraday market",
    "aFRR": "aFRR", "mFRR": "mFRR",
    "Balanço de energia do 1.º ano": "Year-1 energy balance", "Grandeza": "Quantity", "Variação": "Change",
    "Perfil mensal de energia": "Monthly energy profile", "Energia por mês no 1.º ano, em MWh.": "Energy per month in year 1, in MWh.",
    "Perfil diário médio": "Average daily profile",
    "Potência média em cada hora do dia ao longo do 1.º ano, em kW.": "Average power at each hour of the day over year 1, in kW.",
    "Importação": "Import", "Exportação": "Export", "Dias úteis": "Weekdays", "Fins de semana": "Weekends", "Hora": "Hour",
    "kW (média)": "kW (average)", "Rede (+importação / -exportação)": "Grid (+import / -export)",
    "EUR no 1.º ano, face à base": "EUR in year 1, vs baseline",
    "Value stack do 1.º ano": "Year-1 value stack", "Fonte de valor (EUR)": "Value stream (EUR)", "Total": "Total",
    "Receitas com sinal positivo e custos com sinal negativo, em EUR, no 1.º ano.":
        "Revenues are positive and costs negative, in EUR, in year 1.",
    "Contributo de cada fonte de valor para o ganho do 1.º ano face à base.":
        "Contribution of each value stream to the year-1 gain vs baseline.",
    "Cashflow do projeto face à base, descontado à taxa de {r} e acumulado, para todas as variantes. "
    "A variante deste relatório está assinalada com ◄.":
        "Project cashflow vs baseline, discounted at {r} and cumulated, for all variants. "
        "The variant in this report is marked with ◄.",
    "Custos de investimento e de operação": "Investment and operating costs", "Componente": "Component",
    "Quantidade": "Units", "Preço unitário": "Unit price", "Capex total da variante (valor indicado)": "Variant total capex (as entered)",
    "Outros custos de investimento": "Other investment costs", "Custo anual": "Annual cost", "Opex PV": "PV opex",
    "Opex bateria": "Battery opex", "O&M fixo": "Fixed O&M", "Seguro": "Insurance", "Opex do 1.º ano": "Year-1 opex",
    "Reposição de capacidade e substituições ao longo do projeto: {x}.":
        "Capacity augmentation and replacements over the project: {x}.",
    "Valores em EUR, face à base. O ano {y} é o do investimento.": "Values in EUR, vs baseline. Year {y} is the investment year.",
    "Taxa de juro": "Interest rate", "Prazo": "Tenor", "Tipo de reembolso": "Repayment type",
    "Prestação constante": "Annuity (constant instalment)", "Amortização constante": "Constant principal",
    "Taxa de IRC": "Corporate tax rate", "Amortização fiscal": "Tax depreciation",
    "Cada fator varia sozinho, com o despacho do caso base. Os outros ficam como no caso base. VAL do caso base: {n}.":
        "Each factor varies on its own, with the base-case dispatch. The others stay as in the base case. Base-case NPV: {n}.",
    "VAL a descer (EUR)": "NPV, factor down (EUR)", "VAL a subir (EUR)": "NPV, factor up (EUR)",
    "TIR a descer": "IRR, factor down", "TIR a subir": "IRR, factor up", "Cenário": "Scenario",
    "Os cenários de preços P90 / P50 / P10 entram no relatório quando são corridos na aplicação antes de o descarregar.":
        "The P90 / P50 / P10 price scenarios are included when they are run in the app before downloading the report.",
    "Ganho 1.º ano (EUR)": "Year-1 gain (EUR)",
    "Pressupostos de modelação": "Modelling assumptions", "Diagrama de carga carregado": "Uploaded load profile",
    "Sem consumo": "No consumption", "Limite de importação (kW)": "Import limit (kW)",
    "Limite de exportação (kW)": "Export limit (kW)", "Período de preços": "Price period",
    "Semana (7 dias)": "Week (7 days)", "Dia a dia": "Day by day", "Previsão de preços": "Price forecast",
    "Perfeita (limite superior económico)": "Perfect (economic upper bound)", "Escalada anual de preços": "Annual price escalation",
    "Valor residual": "Residual value", "Simulação": "Simulation",
    "Rápida (1.º e último ano, restantes interpolados)": "Fast (first and last year, others interpolated)",
    "Completa (todos os anos)": "Full (every year)", "Taxa de ativação aFRR": "aFRR activation rate",
    "Horas com oferta aceite aFRR": "aFRR hours with accepted bid", "Ajuste dos preços de capacidade aFRR": "aFRR capacity price adjustment",
    "Ativação mFRR a subir / descer": "mFRR activation up / down", "Comissão do agregador (BSP)": "Aggregator (BSP) fee",
    "Verificação": "Check", "Sim": "Yes", "Não": "No", "Notas": "Notes",
    "O despacho da bateria é otimizado com previsão perfeita dos preços, por isso os ganhos de mercado são um "
    "limite superior. Na operação real, com previsões, ficam tipicamente abaixo.":
        "Battery dispatch is optimised with perfect price foresight, so market gains are an upper bound. "
        "In real operation, with forecasts, they are typically lower.",
    "Os preços de mercado vêm do OMIE (diário e intradiário) e da ENTSO-E (aFRR e mFRR) para o período indicado, "
    "e repetem-se nos anos seguintes com a escalada definida.":
        "Market prices come from OMIE (day-ahead and intraday) and ENTSO-E (aFRR and mFRR) for the stated period, "
        "and are repeated in later years with the chosen escalation.",
    "Produção fotovoltaica estimada com dados PVGIS (Comissão Europeia) para a localização do projeto.":
        "PV production estimated with PVGIS data (European Commission) for the project location.",
    "Descarregar relatório (Word)": "Download report (Word)", "Variante do relatório": "Report variant",
    "A preparar o relatório...": "Preparing the report...", "Relatório e exportação": "Report and export",
    "relatorio": "report", "Guia rápido": "Quick guide", "Descarregar guia (Word)": "Download guide (Word)",
    "GridForce_guia_rapido": "GridForce_quick_guide",
    "Novo projeto": "New project",
    "Limpa os separadores 1 a 4 para começar um projeto do zero. Os projetos da biblioteca não são alterados.":
        "Clears tabs 1 to 4 to start a project from scratch. Library projects are not changed.",
    "Projeto novo. Preenche os campos vazios (nome, localização, consumo, custos e variantes). "
    "Os outros campos têm valores típicos: confirma-os antes de correr.":
        "New project. Fill in the empty fields (name, location, consumption, costs and variants). "
        "The other fields hold typical values: check them before running.",
    "Falta preencher: {x}.": "Still to fill in: {x}.", "Variantes (separador 4)": "Variants (tab 4)",
    "Diagrama de carga (CSV)": "Load profile (CSV)",
    "O relatório Word inclui os cenários P90 / P50 / P10 se os correres antes para a mesma variante.":
        "The Word report includes the P90 / P50 / P10 scenarios if you run them first for the same variant.",
})

# Melhorias de 2026-11-23: licenciamento, O&M por dia, cenário base, cenários lado a lado, preços por ano, fluxos e emissões
EN.update({
    "Cenário (opcional)": "Scenario (optional)",
    "Ex.: Investment Grade ou Ultra Conservative. Ao correr vários projetos, os cenários aparecem lado a lado. "
    "Se ficar vazio, usa o texto entre parênteses no fim do nome do projeto.":
        "E.g. Investment Grade or Ultra Conservative. When several projects are run, scenarios are shown side by side. "
        "If left empty, the text in brackets at the end of the project name is used.",
    "Licenciamento e ligação à rede (EUR)": "Licensing and grid connection (EUR)",
    "Custo de investimento separado do equipamento: licenças, estudos, ramal e ligação à rede. Soma-se ao capex de cada variante.":
        "Investment cost separate from equipment: permits, studies, grid connection works. Added to each variant's capex.",
    "Outros custos de investimento: desenvolvimento, etc. Projetos antigos podem ter aqui o licenciamento e a "
    "ligação à rede (o resultado é o mesmo).":
        "Other investment costs: development, etc. Older projects may hold licensing and grid connection here "
        "(the result is the same).",
    "Unidade do O&M e do seguro": "O&M and insurance unit", "EUR/ano": "EUR/year", "EUR/dia": "EUR/day",
    "O&M no 1.º ano ({u})": "Year-1 O&M ({u})", "Seguro no 1.º ano ({u})": "Year-1 insurance ({u})",
    "Por ano: O&M {a} EUR, seguro {b} EUR.": "Per year: O&M {a} EUR, insurance {b} EUR.",
    "Fator de emissões da rede (g CO2/kWh)": "Grid emission factor (g CO2/kWh)",
    "Para calcular as emissões evitadas. A Enforce usa 470 g CO2/kWh para a indústria.":
        "Used for avoided emissions. Enforce uses 470 g CO2/kWh for industry.",
    "Para ver o valor da bateria, junta uma linha só com PV (BESS a 0) e compara-a com a de PV + bateria nos "
    "resultados, em \"Cenário base e valor incremental\".":
        "To see the battery's value, add a PV-only row (BESS at 0) and compare it with the PV + battery row in "
        "the results, under \"Baseline and incremental value\".",
    "Cenários lado a lado": "Scenarios side by side",
    "Para cada projeto conta a variante com maior VAL. A TIR do cenário é a dos cashflows de todos os parques somados.":
        "For each project the variant with the highest NPV counts. The scenario IRR is that of all parks' cashflows added up.",
    "Parque": "Park", "Parques": "Parks", "Cenário": "Scenario",
    "Emissões evitadas 1.º ano (t CO2)": "Year-1 avoided emissions (t CO2)",
    "Cenário base e valor incremental": "Baseline and incremental value",
    "O cenário base é o local sem PV nem bateria. Todos os resultados acima são o ganho face a esta base. Aqui "
    "podes comparar duas variantes entre si (ex.: PV + bateria face a só PV, para ver o valor da bateria) ou uma "
    "variante com a base.":
        "The baseline is the site without PV or battery. All results above are the gain over this baseline. Here you "
        "can compare two variants (e.g. PV + battery vs PV only, to see the battery's value) or a variant with the baseline.",
    "Base, 1.º ano (EUR)": "Baseline, year 1 (EUR)",
    "Neste projeto a base não tem custos nem receitas (sem consumo), por isso o valor face à base é o valor total dos ativos.":
        "In this project the baseline has no costs or revenues (no consumption), so the value vs baseline is the assets' total value.",
    "Cenário base (sem ativos)": "Baseline (no assets)", "Variante A": "Variant A", "Comparar com (B)": "Compare with (B)",
    "VAL de A face a B": "NPV of A vs B", "TIR incremental": "Incremental IRR", "Capex adicional de A": "Extra capex of A",
    "Ganho 1.º ano de A face a B": "Year-1 gain of A vs B", "**Cashflow relativo (A - B)**": "**Relative cashflow (A - B)**",
    "Diferença (A - B)": "Difference (A - B)", "Diferença descontada acumulada": "Cumulative discounted difference",
    "Diferença acumulada": "Cumulative difference", "Cashflow A": "Cashflow A", "Cashflow B": "Cashflow B",
    "**Value stack do 1.º ano: A - B**": "**Year-1 value stack: A - B**",
    "Cashflow relativo por ano": "Relative cashflow by year",
    "Preços aplicados por ano": "Rates applied by year",
    "Preços médios de mercado e custos usados em cada ano, já com escalada, ajuste aFRR e comissões. Serve para "
    "auditar os pressupostos.":
        "Average market prices and costs used each year, including escalation, aFRR adjustment and fees. For auditing the assumptions.",
    "Item": "Item", "Unidade": "Unit",
    "Mercado diário - preço médio": "Day-ahead market - average price",
    "Mercado intradiário - preço médio": "Intraday market - average price",
    "Tarifas e custos na compra - média": "Import tariffs and costs - average",
    "Comissão na venda": "Export fee",
    "aFRR descer - ativação (pago pelo agente)": "aFRR down - activation (paid by the agent)",
    "mFRR subir - capacidade": "mFRR up - capacity", "mFRR descer - capacidade": "mFRR down - capacity",
    "mFRR descer - ativação (pago pelo agente)": "mFRR down - activation (paid by the agent)",
    "EUR/kWp/ano": "EUR/kWp/year", "EUR/kWh/ano": "EUR/kWh/year",
    "Fluxos de energia entre ativos e emissões evitadas": "Inter-asset energy flows and avoided emissions",
    "Variante   ": "Variant", "MWh no 1.º ano": "MWh in year 1",
    "PV → consumo": "PV → load", "PV → bateria": "PV → battery", "PV → rede": "PV → grid",
    "Bateria → consumo": "Battery → load", "Bateria → rede": "Battery → grid", "Rede → consumo": "Grid → load",
    "Rede → bateria": "Grid → battery", "Rede": "Grid", "Consumo": "Load",
    "Emissões evitadas no 1.º ano": "Avoided emissions, year 1", "Emissões evitadas no projeto": "Avoided emissions, project life",
    "Face à base, com {f} g CO2/kWh.": "Vs baseline, at {f} g CO2/kWh.",
    "Fluxos de energia 1.º ano": "Energy flows year 1", "Emissões evitadas": "Avoided emissions",
    "Preços por ano": "Rates by year", "Cenários": "Scenarios", "Cenários por parque": "Scenarios by park",
    "Cashflows por cenário": "Cashflows by scenario",
    "Energia da rede evitada (MWh)": "Grid energy avoided (MWh)", "Emissões evitadas (t CO2)": "Avoided emissions (t CO2)",
    "Equipamento (PV e bateria)": "Equipment (PV and battery)", "Licenciamento e ligação à rede": "Licensing and grid connection",
    "Fluxos de energia entre ativos": "Inter-asset energy flows", "Fluxo": "Flow", "dias": "days", "dia": "day",
    "Emissões evitadas face à base: {a} t CO2 no 1.º ano e {b} t CO2 ao longo do projeto (fator da rede {f} g CO2/kWh).":
        "Avoided emissions vs baseline: {a} t CO2 in year 1 and {b} t CO2 over the project (grid factor {f} g CO2/kWh).",
    "Preços médios de mercado e custos aplicados, com escalada, ajustes e comissões. A tabela completa, ano a ano, "
    "está no Excel (folha Preços por ano).":
        "Average market prices and costs applied, with escalation, adjustments and fees. The full year-by-year table "
        "is in the Excel file (sheet Rates by year).",
})

# Gravar como (2026-11-23)
EN.update({
    "Gravar como...": "Save as...",
    "Grava uma cópia com outro nome (nova versão ou projeto novo). O projeto original fica como estava.":
        "Saves a copy under another name (new version or new project). The original project stays as it was.",
    "Novo nome do projeto": "New project name", "Projeto": "Project",
    "Já existe um projeto com este nome: substituir": "A project with this name already exists: replace it",
    "Já existe um projeto com este nome. Escolhe outro nome ou confirma a substituição.":
        "A project with this name already exists. Choose another name or confirm the replacement.",
    "Gravar com este nome": "Save with this name",
    "Gravado como {fn}. Os separadores mostram agora este projeto.": "Saved as {fn}. The tabs now show this project.",
})

# Capex das variantes e potência de pico (2026-11-23)
EN.update({
    "Cada linha é uma variante a comparar. Adiciona ou apaga linhas à vontade. O capex do equipamento é opcional: se o "
    "preencheres, substitui o cálculo por EUR/kWp e EUR/kWh. O licenciamento, a ligação à rede e o capex adicional "
    "(separador 3) somam-se a este valor.":
        "Each row is a variant to compare. Add or delete rows freely. Equipment capex is optional: if you fill it in, it "
        "replaces the EUR/kWp and EUR/kWh calculation. Licensing, grid connection and additional capex (tab 3) are added to it.",
    "Capex do equipamento (EUR, opcional)": "Equipment capex (EUR, optional)",
    "PV e bateria. Se ficar vazio, é calculado com os EUR/kWp e EUR/kWh do separador 2.":
        "PV and battery. If empty, it is calculated with the EUR/kWp and EUR/kWh of tab 2.",
    "**Capex total usado na simulação**": "**Total capex used in the simulation**",
    "Capex do equipamento (EUR)": "Equipment capex (EUR)", "Origem": "Source",
    "indicado na tabela": "entered in the table", "calculado por EUR/kWp e EUR/kWh": "calculated from EUR/kWp and EUR/kWh",
    "Capex total do projeto (EUR)": "Total project capex (EUR)",
    "Potência de pico PV (kWp)": "PV peak power (kWp)", "Potência AC do inversor (kW)": "Inverter AC power (kW)",
    "A potência de pico é definida por variante, no separador 4. Potência AC = kWp / rácio DC/AC.":
        "Peak power is set per variant, in tab 4. AC power = kWp / DC/AC ratio.",
})
EN.update({
    "Atenção: {v} tem o capex do equipamento preenchido na tabela, por isso os valores de Capex PV (EUR/kWp) e Capex "
    "bateria (EUR/kWh) do separador 2 não estão a ser usados. Para usar os EUR/kWp e EUR/kWh, apaga o valor da coluna "
    "\"Capex do equipamento\".":
        "Note: {v} has equipment capex entered in the table, so the PV capex (EUR/kWp) and battery capex (EUR/kWh) of "
        "tab 2 are not used. To use EUR/kWp and EUR/kWh, clear the \"Equipment capex\" cell.",
    "Há variantes com o capex do equipamento indicado no separador 4: para essas, os EUR/kWp e EUR/kWh daqui não contam.":
        "Some variants have equipment capex entered in tab 4: for those, the EUR/kWp and EUR/kWh here are not used.",
})

# Modo do capex do equipamento (2026-11-23)
EN.update({
    "Capex do equipamento (PV e bateria)": "Equipment capex (PV and battery)",
    "Calculado por EUR/kWp e EUR/kWh": "Calculated from EUR/kWp and EUR/kWh",
    "Valor fixo por variante": "Fixed value per variant",
    "Calculado: kWp x EUR/kWp + kWh x EUR/kWh, com os valores deste separador. Valor fixo: escreves o capex do "
    "equipamento de cada variante no separador 4.":
        "Calculated: kWp x EUR/kWp + kWh x EUR/kWh, with the values in this tab. Fixed value: you enter each "
        "variant's equipment capex in tab 4.",
    "Não conta: o capex está como valor fixo por variante (separador 4).":
        "Not used: capex is set as a fixed value per variant (tab 4).",
    "Cada linha é uma variante a comparar. Adiciona ou apaga linhas à vontade.":
        "Each row is a variant to compare. Add or delete rows freely.",
    "Capex do equipamento: valor fixo por variante. Escreve-o na última coluna. Para usar EUR/kWp e EUR/kWh, muda a "
    "opção no separador 2. O licenciamento e o capex adicional (separador 3) somam-se.":
        "Equipment capex: fixed value per variant. Enter it in the last column. To use EUR/kWp and EUR/kWh, change the "
        "option in tab 2. Licensing and additional capex (tab 3) are added.",
    "Capex do equipamento calculado com os EUR/kWp e EUR/kWh do separador 2 (vê o quadro em baixo). Para escrever um "
    "valor fixo por variante, muda a opção no separador 2.":
        "Equipment capex calculated from the EUR/kWp and EUR/kWh of tab 2 (see the table below). To enter a fixed value "
        "per variant, change the option in tab 2.",
    "PV e bateria, por variante.": "PV and battery, per variant.",
    "Falta o capex do equipamento de: {v}.": "Equipment capex missing for: {v}.",
    "Capex do equipamento (separador 4)": "Equipment capex (tab 4)",
})
EN.update({
    "Com PPA, todo o PV injetado diretamente na rede é vendido ao preço fixo. \"Mercado diário - venda\" é a energia que "
    "a bateria descarrega e vende no mercado (carregada com PV ou com energia da rede), nas horas de preço mais alto.":
        "With a PPA, all PV fed directly into the grid is sold at the fixed price. \"Day-ahead - sale\" is the energy the "
        "battery discharges and sells on the market (charged from PV or from the grid), in the highest-price hours.",
})

EN.update({
    "Montagem PV": "PV mounting", "Fixo": "Fixed",
    "Seguidor de 1 eixo horizontal (eixo N-S, roda E-O)": "Single-axis tracker, horizontal (N-S axis, tracks E-W)",
    "Seguidor de 1 eixo inclinado (eixo N-S)": "Single-axis tracker, inclined (N-S axis)",
    "Seguidor de 2 eixos": "Dual-axis tracker",
    "Fixo ou com seguidor. O perfil de produção vem do PVGIS para o tipo escolhido. "
    "Nos seguidores o azimute não conta; no de eixo horizontal e no de 2 eixos a "
    "inclinação também não; no de eixo inclinado a inclinação é a do eixo. "
    "O PVGIS não considera backtracking nem sombreamento entre filas.":
        "Fixed or tracking. The production profile comes from PVGIS for the chosen type. "
        "For trackers the azimuth is ignored; for the horizontal-axis and dual-axis trackers the tilt is ignored too; "
        "for the inclined-axis tracker the tilt is the axis tilt. PVGIS does not model backtracking or row-to-row shading.",
    "BESS (h)": "BESS (h)", "Duração da bateria em horas à potência nominal.": "Battery duration in hours at rated power.",
    "Capacidade de armazenamento = potência (kW) x duração (h). Calculada.":
        "Storage capacity = power (kW) x duration (h). Calculated.",
    "Potência da bateria (kW)": "Battery power (kW)", "Duração (h)": "Duration (h)",
    "Capacidade de armazenamento": "Storage capacity",
    "Capacidade = potência x duração. O tamanho da bateria é de cada variante: também se pode mudar "
    "na tabela do separador 4 (põe 0 kW para uma variante só com PV).":
        "Capacity = power x duration. The battery size belongs to each variant: it can also be changed in the "
        "table in tab 4 (set 0 kW for a PV-only variant).",
})
