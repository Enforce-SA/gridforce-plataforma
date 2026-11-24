"""Perfis de consumo tipo, usados quando não há diagrama de carga medido."""
from __future__ import annotations

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
    num = raw.apply(_to_number)
    # coluna de valores: a última que é quase toda numérica (colunas de data/hora ficam de fora)
    share = num.notna().mean()
    cands = [c for c in num.columns if share[c] >= 0.5]
    if not cands:
        raise ValueError("Não encontrei nenhuma coluna com números no ficheiro.")
    col = cands[-1]
    v = num[col]
    # linhas de cabeçalho no topo (texto) saem
    first = v.first_valid_index()
    head = raw.iloc[:first]
    v = v.iloc[first:].to_numpy(float)
    # linhas finais vazias ou de totais em texto saem
    while len(v) and np.isnan(v[-1]):
        v = v[:-1]
    notes: list[str] = []
    if len(head):
        notes.append(f"{len(head)} linha(s) de cabeçalho ignorada(s).")
    v = normalize_load(v, notes)
    return v, notes
