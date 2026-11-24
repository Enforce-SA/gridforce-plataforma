"""Perfis de consumo tipo, usados quando não há diagrama de carga medido."""
from __future__ import annotations

import io

import numpy as np
import pandas as pd


def shopping_centre(index: pd.DatetimeIndex, annual_mwh: float) -> np.ndarray:
    """Perfil tipo de centro comercial (kW), escalado para annual_mwh.

    Pressupostos (a substituir por dados medidos quando existirem):
    - aberto todos os dias 09:00 a 23:00, base noturna de 35% da ponta;
    - rampas de 1 h na abertura e fecho;
    - climatização: +25% no pico do verão (julho/agosto) e +10% no inverno.
    """
    local = index.tz_convert("Europe/Lisbon")
    h = np.asarray(local.hour + local.minute / 60.0, dtype=float)
    open_frac = np.clip(np.minimum(h - 8.0, 23.0 - h), 0.0, 1.0)  # rampa 08-09 e 22-23
    base = 0.35 + 0.65 * open_frac
    doy = np.asarray(local.dayofyear, dtype=float)
    summer = np.exp(-((doy - 210) / 35.0) ** 2) * 0.25
    winter = (np.exp(-((doy - 15) / 30.0) ** 2) + np.exp(-((doy - 380) / 30.0) ** 2)) * 0.10
    hvac_daytime = 0.5 + 0.5 * open_frac
    shape = base * (1.0 + (summer + winter) * hvac_daytime)
    kwh = shape.sum() * 0.25
    return shape * (annual_mwh * 1000.0 / kwh)


# ---------------------------------------------------------------------------
# Leitura de diagramas de carga carregados pelo utilizador
# ---------------------------------------------------------------------------
QUARTERS = 35040  # 1 ano de intervalos de 15 min


def _to_number(s: pd.Series) -> pd.Series:
    """Converte texto em número aceitando vírgula ou ponto decimal e separadores de milhares."""
    t = s.astype(str).str.strip().str.replace(" ", "", regex=False).str.replace(" ", "", regex=False)
    both = t.str.contains(",", regex=False) & t.str.contains(".", regex=False)
    comma_last = t.str.rfind(",") > t.str.rfind(".")
    # "1.234,5" -> 1234.5 ; "1,234.5" -> 1234.5 ; "12,5" -> 12.5
    t = t.where(~(both & comma_last), t.str.replace(".", "", regex=False))
    t = t.where(~(both & ~comma_last), t.str.replace(",", "", regex=False))
    t = t.str.replace(",", ".", regex=False)
    return pd.to_numeric(t, errors="coerce")


def _sniff_sep(text: str) -> str:
    lines = [ln for ln in text.splitlines()[:50] if ln.strip()]
    for sep in (";", "\t"):
        if sum(ln.count(sep) for ln in lines) >= len(lines) // 2:
            return sep
    if sum(ln.count(",") for ln in lines) >= len(lines) // 2:
        return ","
    return ";"  # uma só coluna: o separador não interessa


def _resample_to_quarters(v: np.ndarray, notes: list[str]) -> np.ndarray:
    """Passa a série para 35 040 intervalos de 15 min, com tolerância a dias de mudança de hora e anos bissextos."""
    n = len(v)
    if abs(n - 8760) <= 48:          # horário (8 759/8 761 por mudança de hora, 8 784 bissexto)
        steps, per_h = 8760, 4
    elif abs(n - 17520) <= 96:       # meia hora
        steps, per_h = 17520, 2
    elif abs(n - QUARTERS) <= 192:   # 15 min
        steps, per_h = QUARTERS, 1
    else:
        raise ValueError(f"O ficheiro tem {n:,} valores; esperava cerca de 8 760 (horário) ou 35 040 (15 min).")
    if n != steps:
        if n > steps:
            v = v[:steps]
            notes.append(f"O ficheiro tinha {n - steps} intervalo(s) a mais (mudança de hora ou ano bissexto): "
                         f"foram ignorados os últimos.")
        else:
            v = np.concatenate([v, np.full(steps - n, np.nan)])
            notes.append(f"O ficheiro tinha {steps - n} intervalo(s) a menos (mudança de hora): foram acrescentados "
                         f"e preenchidos.")
    return np.repeat(v, per_h)


def fill_gaps(v, notes: list[str] | None = None) -> np.ndarray:
    """Preenche valores em falta por interpolação (e pelo vizinho nas pontas) e avisa quantos eram."""
    v = np.asarray(v, dtype=float)
    miss = int(np.isnan(v).sum())
    if miss and notes is not None:
        share = miss / max(len(v), 1) * 100
        notes.append(f"{miss:,} de {len(v):,} intervalos estavam vazios ({share:.1f}%) e foram preenchidos por "
                     f"interpolação a partir dos valores vizinhos." + (" Convém confirmar o ficheiro: é muita falta."
                                                                       if share > 5 else ""))
    if miss == len(v):
        raise ValueError("O diagrama de carga não tem nenhum valor numérico.")
    if miss:
        v = pd.Series(v).interpolate(limit_direction="both").to_numpy()
    return v


def normalize_load(v, notes: list[str] | None = None) -> np.ndarray:
    """Série guardada num projeto (horária ou de 15 min, eventualmente com falhas) -> 35 040 valores sem falhas."""
    notes = [] if notes is None else notes
    v = np.asarray(v, dtype=float)
    if len(v) != QUARTERS:
        v = _resample_to_quarters(v, notes)
    return fill_gaps(v, notes)


def _known_length(n: int) -> bool:
    return abs(n - 8760) <= 48 or abs(n - 17520) <= 96 or abs(n - QUARTERS) <= 192


def _parse_table(raw: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
    """Tabela lida (texto, sem cabeçalho) -> 35 040 valores de 15 min e avisos. Comum a CSV e Excel."""
    raw = raw.dropna(how="all").reset_index(drop=True)
    if raw.empty:
        raise ValueError("O ficheiro está vazio.")
    num = raw.apply(_to_number)
    # coluna de valores: a última que é quase toda numérica (colunas de data/hora ficam de fora)
    share = num.notna().mean()
    cands = [c for c in num.columns if share[c] >= 0.5]
    if not cands:
        raise ValueError("Não encontrei nenhuma coluna com números no ficheiro. Se usou o modelo, confirme que "
                         "preencheu a coluna de consumo.")
    col = cands[-1]
    v = num[col]
    # linhas de cabeçalho no topo (texto) saem
    first = v.first_valid_index()
    head = raw.iloc[:first]
    v = v.iloc[first:].to_numpy(float)
    full = len(v)
    # linhas finais vazias ou de totais em texto saem
    while len(v) and np.isnan(v[-1]):
        v = v[:-1]
    if len(v) < full and not _known_length(len(v)) and _known_length(full):
        raise ValueError(f"Só {int(np.isfinite(v).sum()):,} de {full:,} intervalos têm valor: as últimas "
                         f"{full - len(v):,} linhas estão por preencher. Complete a coluna de consumo até ao fim.")
    notes: list[str] = []
    if len(head) > 1:  # uma linha de títulos é o normal; mais do que isso merece aviso
        notes.append(f"{len(head)} linha(s) de cabeçalho ignorada(s).")
    neg = int((v < 0).sum())
    if neg:
        notes.append(f"{neg:,} valor(es) negativo(s) no consumo. O consumo deve ser positivo: confirme se o ficheiro "
                     f"não traz injeção na rede ou um sinal trocado.")
    v = normalize_load(v, notes)
    return v, notes


def parse_load_csv(data: bytes) -> tuple[np.ndarray, list[str]]:
    """Lê um CSV de diagrama de carga (kW) e devolve 35 040 valores de 15 min e uma lista de avisos.

    Aceita: separador ; , ou tabulação; vírgula ou ponto decimal; com ou sem cabeçalho; colunas de data/hora
    antes do valor (usa a última coluna numérica); dados horários, de 30 min ou de 15 min; dias de mudança de hora.
    """
    text = None
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    sep = _sniff_sep(text)
    raw = pd.read_csv(pd.io.common.StringIO(text), sep=sep, header=None, dtype=str, engine="python",
                      skip_blank_lines=True)
    return _parse_table(raw)


TEMPLATE_SHEETS = ("Consumo", "Consumption")


def parse_load_xlsx(data: bytes) -> tuple[np.ndarray, list[str]]:
    """Lê um Excel (.xlsx) de diagrama de carga, em particular o modelo da GridForce.

    Usa a folha "Consumo" (ou "Consumption") se existir; senão a folha com mais valores numéricos.
    """
    try:
        sheets = pd.read_excel(io.BytesIO(data), sheet_name=None, header=None, engine="openpyxl")
    except Exception as e:  # ficheiro corrompido, protegido por palavra-passe ou não é Excel
        raise ValueError("Não consegui abrir o ficheiro Excel. Confirme que é um .xlsx sem palavra-passe.") from e
    named = [k for k in sheets if k.strip().lower() in {s.lower() for s in TEMPLATE_SHEETS}]
    if named:
        raw = sheets[named[0]]
    else:
        raw = max(sheets.values(), key=lambda d: int(d.apply(pd.to_numeric, errors="coerce").notna().sum().max())
                  if not d.empty else 0)
    # tudo passa a texto: números com ponto decimal; datas e horas ficam como texto não numérico
    def _cell(x):
        if x is None or (isinstance(x, float) and np.isnan(x)):
            return ""
        if isinstance(x, (int, float, np.number)) and not isinstance(x, bool):
            return repr(float(x))
        return str(x)
    raw = raw.apply(lambda c: c.map(_cell)).replace("", np.nan)
    return _parse_table(raw)


def parse_load_file(name: str, data: bytes) -> tuple[np.ndarray, list[str]]:
    """Escolhe o leitor pelo nome do ficheiro (.xlsx ou .csv)."""
    if name.lower().endswith((".xlsx", ".xlsm")) or data[:2] == b"PK":
        return parse_load_xlsx(data)
    return parse_load_csv(data)


def load_template_xlsx(lab: dict, step_min: int = 60, year: int = 2025) -> bytes:
    """Modelo Excel para preencher: 8 760 horas (step_min=60) ou 35 040 quartos de hora (step_min=15) com data e hora já escritas, coluna de consumo e instruções.

    `lab` traz os textos já traduzidos (chaves: sheet, sheet_help, date, hour, value, dv_error, total, help_title,
    help). Os valores são potência média no intervalo (kW), como no resto da aplicação.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    ws = wb.active
    ws.title = lab["sheet"]
    head_fill = PatternFill("solid", fgColor="1F4E79")
    in_fill = PatternFill("solid", fgColor="FFF2CC")
    for j, h in enumerate((lab["date"], lab["hour"], lab["value"]), start=1):
        c = ws.cell(row=1, column=j, value=h)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = head_fill
        c.alignment = Alignment(horizontal="center", wrap_text=True)
    start = pd.Timestamp(year=year, month=1, day=1)
    n = 8760 * 60 // step_min
    for i in range(n):
        t = start + pd.Timedelta(minutes=i * step_min)
        t2 = t + pd.Timedelta(minutes=step_min)
        r = i + 2
        d = ws.cell(row=r, column=1, value=t.to_pydatetime().date())
        d.number_format = "DD/MM/YYYY"
        ws.cell(row=r, column=2, value=f"{t:%H:%M}-{t2:%H:%M}")
        ws.cell(row=r, column=3).fill = in_fill
        ws.cell(row=r, column=3).number_format = "#,##0.00"
    dv = DataValidation(type="decimal", operator="greaterThanOrEqual", formula1="0", allow_blank=True,
                        showErrorMessage=True, errorTitle=lab["value"], error=lab["dv_error"])
    ws.add_data_validation(dv)
    dv.add(f"C2:C{n + 1}")
    ws.column_dimensions["A"].width = 13
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 22
    ws.row_dimensions[1].height = 32
    ws.freeze_panes = "A2"

    hs = wb.create_sheet(lab["sheet_help"])
    hs.column_dimensions["A"].width = 110
    hs.cell(row=1, column=1, value=lab["help_title"]).font = Font(bold=True, size=14)
    r = 3
    for line in lab["help"]:
        c = hs.cell(row=r, column=1, value=line)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        r += 1
    r += 1
    hs.cell(row=r, column=1, value=lab["total"]).font = Font(bold=True)
    c = hs.cell(row=r + 1, column=1, value=f"=SUM('{lab['sheet']}'!C2:C{n + 1})*{step_min / 60}/1000")
    c.number_format = "#,##0.0"
    c.alignment = Alignment(horizontal="left")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
