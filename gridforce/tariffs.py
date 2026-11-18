"""Tarifas de Acesso às Redes (ERSE) para clientes não residenciais em Portugal continental.

Fonte dos preços: ERSE, "s_tarifas_net_outubro-2026.xlsx", folha "Tarifas Acesso"
(https://www.erse.pt/media/wbxljhas/s_tarifas_net_outubro-2026.xlsx).
Fonte dos períodos: ERSE, Diretiva n.º 3/2026 e "ERSExplica - novos períodos horários"
(ciclo semanal único para MT, AT e MAT, em vigor a partir de 1 de abril de 2027).

Encargos modelados:
  - energia ativa por período horário (EUR/kWh);
  - potência em horas de ponta (EUR/kW/dia), sobre a potência média importada em
    horas de ponta no mês; convertida num custo equivalente por kWh importado em ponta,
    o que a torna linear e otimizável;
  - potência contratada (EUR/kW/dia), sobre a ponta máxima de importação do ano
    (calculada depois do despacho, não otimizada).
A energia reativa não é modelada.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

PONTA, CHEIAS, VAZIO, SUPER_VAZIO = "Ponta", "Cheias", "Vazio normal", "Super vazio"


@dataclass(frozen=True)
class AccessTariff:
    name: str
    energy_eur_kwh: dict
    peak_power_eur_kw_day: float
    contracted_power_eur_kw_day: float


# Tarifas em vigor (ERSE, outubro de 2026)
TAR_2026 = {
    "MAT": AccessTariff("MAT", {PONTA: 0.0073, CHEIAS: 0.0069, VAZIO: 0.0067, SUPER_VAZIO: 0.0063}, 0.0716, 0.0126),
    "AT": AccessTariff("AT", {PONTA: 0.0125, CHEIAS: 0.0115, VAZIO: 0.0102, SUPER_VAZIO: 0.0094}, 0.1515, 0.0089),
    "MT": AccessTariff("MT", {PONTA: 0.0203, CHEIAS: 0.0182, VAZIO: 0.0146, SUPER_VAZIO: 0.0129}, 0.2435, 0.0458),
    "BTE": AccessTariff("BTE", {PONTA: 0.0397, CHEIAS: 0.0353, VAZIO: 0.0285, SUPER_VAZIO: 0.0237}, 0.5521, 0.0563),
}

# Feriados nacionais de data fixa (tratados como domingo no ciclo semanal)
FIXED_HOLIDAYS = {(1, 1), (4, 25), (5, 1), (6, 10), (8, 15), (10, 5), (11, 1), (12, 1), (12, 8), (12, 25)}


def _hm(h: float, m: int = 0) -> float:
    return h + m / 60.0


def weekly_cycle_period(ts: pd.Timestamp) -> str:
    """Período horário do ciclo semanal (MT/AT/MAT), novos períodos ERSE 2027.

    ts em hora legal de Lisboa. Inverno/verão segue a hora legal (DST).
    """
    t = ts.hour + ts.minute / 60.0
    if _hm(2, 30) <= t < _hm(6, 30):
        return SUPER_VAZIO
    dow = ts.dayofweek
    if dow == 6 or (ts.month, ts.day) in FIXED_HOLIDAYS:
        return VAZIO
    if dow == 5:
        return CHEIAS if t >= 17 else VAZIO
    summer = bool(ts.dst())
    if t < 0.5:
        return CHEIAS
    if t < _hm(2, 30) or _hm(6, 30) <= t < _hm(7, 30):
        return VAZIO
    p0, p1 = ((_hm(19, 30), _hm(22, 30)) if summer else (17.0, 22.0))
    if p0 <= t < p1:
        return PONTA
    return CHEIAS


def periods(index: pd.DatetimeIndex) -> np.ndarray:
    local = index.tz_convert("Europe/Lisbon")
    return np.array([weekly_cycle_period(t) for t in local])


def import_adder_eur_mwh(index: pd.DatetimeIndex, tariff: AccessTariff, extra_eur_mwh: float = 0.0) -> np.ndarray:
    """Custo marginal de importar 1 MWh em cada intervalo (EUR/MWh), sem a energia de mercado.

    Inclui energia ativa por período + potência em horas de ponta convertida para EUR/MWh
    (preço diário x dias do mês / horas de ponta do mês) + extra (ex. margem do comercializador,
    CIEG, imposto especial de consumo).
    """
    per = periods(index)
    local = index.tz_convert("Europe/Lisbon")
    adder = np.array([tariff.energy_eur_kwh[p] for p in per]) * 1000.0
    month = local.tz_localize(None).to_period("M")
    df = pd.DataFrame({"m": month, "ponta": per == PONTA})
    ponta_hours = df.groupby("m").ponta.sum() * 0.25
    days = pd.Series({m: m.days_in_month for m in ponta_hours.index})
    peak_eur_mwh = (tariff.peak_power_eur_kw_day * days / ponta_hours).replace(np.inf, 0) * 1000.0
    adder = adder + np.where(per == PONTA, peak_eur_mwh.reindex(month).values, 0.0)
    return adder + extra_eur_mwh


def contracted_power_cost(import_kw: np.ndarray, tariff: AccessTariff, days: int = 365) -> float:
    return float(np.max(import_kw) * tariff.contracted_power_eur_kw_day * days)
