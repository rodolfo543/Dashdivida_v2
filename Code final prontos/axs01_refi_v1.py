# -*- coding: utf-8 -*-
"""
AXS Energia Unidade 01 - Refi - Debentures AXSA11 / AXSA21 - IPCA.

Objetivo
- Calcular o fluxo da 1a emissao refinanciada da AXS 01 em duas series.
- Gerar historico diario de PU e fluxo de eventos com CSV e XLSX.
- Seguir a escritura de emissao e o 1o aditamento:
  Serie 1: IPCA + 9,3515% a.a.
  Serie 2: IPCA + 10,9659% a.a.

Arquivos gerados na pasta deste script:
    controle_divida_axs01_refi_v1_eventos.csv
    controle_divida_axs01_refi_v1_eventos.xlsx
    historico_pu_axs01_refi_v1_diario.csv
    historico_pu_axs01_refi_v1_diario.xlsx
    controle_divida_axs01_refi_v1_completo.xlsx

Observacao
- Para meses sem IPCA oficial no SIDRA/IBGE, o script usa o Focus/BCB.
- Se o Focus estiver indisponivel, usa 0,45% a.m. como fallback local.
"""

from __future__ import annotations

import csv
import json
import math
import re
import ssl
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP, getcontext
from pathlib import Path
from typing import Dict, Iterable, List, Tuple
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

getcontext().prec = 40

BASE_DIR = Path(__file__).resolve().parent

DATA_EMISSAO = date(2026, 2, 24)
DATA_INICIO_RENTABILIDADE = date(2026, 3, 13)
DATA_VENCIMENTO = date(2042, 2, 15)
PU_INICIAL = Decimal("1000.00000000")
BASE_DU = Decimal("252")
IPCA_PROJECAO_MENSAL_PADRAO = Decimal("0.0045")

ARQ_EVENTOS_CSV = BASE_DIR / "controle_divida_axs01_refi_v1_eventos.csv"
ARQ_EVENTOS_XLSX = BASE_DIR / "controle_divida_axs01_refi_v1_eventos.xlsx"
ARQ_DIARIO_CSV = BASE_DIR / "historico_pu_axs01_refi_v1_diario.csv"
ARQ_DIARIO_XLSX = BASE_DIR / "historico_pu_axs01_refi_v1_diario.xlsx"
ARQ_COMPLETO_XLSX = BASE_DIR / "controle_divida_axs01_refi_v1_completo.xlsx"


@dataclass(frozen=True)
class Serie:
    nome: str
    codigo_if: str
    isin: str
    quantidade: Decimal
    taxa_aa: Decimal
    perc_amort_key: str


SERIES = [
    Serie(
        nome="Debentures da Primeira Serie",
        codigo_if="AXSA11",
        isin="BRAXSADBS001",
        quantidade=Decimal("86000"),
        taxa_aa=Decimal("0.093515"),
        perc_amort_key="Perc_Amort_S1",
    ),
    Serie(
        nome="Debentures da Segunda Serie",
        codigo_if="AXSA21",
        isin="BRAXSADBS019",
        quantidade=Decimal("22800"),
        taxa_aa=Decimal("0.109659"),
        perc_amort_key="Perc_Amort_S2",
    ),
]

# Anexo II da escritura. As quatro primeiras linhas da tabela nao geram pagamento;
# 15/08/2026, 15/02/2027 e 15/08/2027 sao datas de incorporacao de juros.
CRONOGRAMA_RAW = [
    ("2026-08-15", "0.0000", "0.0000", "INCORPORACAO"),
    ("2027-02-15", "0.0000", "0.0000", "INCORPORACAO"),
    ("2027-08-15", "0.0000", "0.0000", "INCORPORACAO"),
    ("2028-02-15", "0.6714", "4.8764", "PAGAMENTO"),
    ("2028-08-15", "0.4850", "4.9402", "PAGAMENTO"),
    ("2029-02-15", "0.4472", "5.3923", "PAGAMENTO"),
    ("2029-08-15", "0.3962", "5.8946", "PAGAMENTO"),
    ("2030-02-15", "0.3108", "6.4022", "PAGAMENTO"),
    ("2030-08-15", "0.2800", "7.1784", "PAGAMENTO"),
    ("2031-02-15", "0.2240", "8.0518", "PAGAMENTO"),
    ("2031-08-15", "0.1702", "9.1496", "PAGAMENTO"),
    ("2032-02-15", "3.0129", "1.8750", "PAGAMENTO"),
    ("2032-08-15", "3.1937", "1.9484", "PAGAMENTO"),
    ("2033-02-15", "3.4396", "2.0669", "PAGAMENTO"),
    ("2033-08-15", "3.8149", "2.2813", "PAGAMENTO"),
    ("2034-02-15", "4.1427", "2.4350", "PAGAMENTO"),
    ("2034-08-15", "4.6261", "2.6956", "PAGAMENTO"),
    ("2035-02-15", "4.7262", "2.6301", "PAGAMENTO"),
    ("2035-08-15", "4.8894", "2.5760", "PAGAMENTO"),
    ("2036-02-15", "5.3764", "2.7591", "PAGAMENTO"),
    ("2036-08-15", "6.0793", "3.0639", "PAGAMENTO"),
    ("2037-02-15", "6.7808", "3.3072", "PAGAMENTO"),
    ("2037-08-15", "7.7796", "3.6908", "PAGAMENTO"),
    ("2038-02-15", "9.5279", "5.7336", "PAGAMENTO"),
    ("2038-08-15", "11.2604", "6.5546", "PAGAMENTO"),
    ("2039-02-15", "13.3305", "7.3937", "PAGAMENTO"),
    ("2039-08-15", "16.4357", "8.5971", "PAGAMENTO"),
    ("2040-02-15", "20.6849", "9.9297", "PAGAMENTO"),
    ("2040-08-15", "27.8587", "11.8655", "PAGAMENTO"),
    ("2041-02-15", "40.6540", "14.2331", "PAGAMENTO"),
    ("2041-08-15", "73.1545", "17.8538", "PAGAMENTO"),
    ("2042-02-15", "100.0000", "100.0000", "PAGAMENTO"),
]


def trunc_dec(valor: Decimal, casas: int = 8) -> Decimal:
    return valor.quantize(Decimal("1").scaleb(-casas), rounding=ROUND_DOWN)


def round_dec(valor: Decimal, casas: int = 2) -> Decimal:
    return valor.quantize(Decimal("1").scaleb(-casas), rounding=ROUND_HALF_UP)


def trunc_float_dec(valor: float | Decimal, casas: int = 8) -> Decimal:
    escala = 10 ** casas
    truncado = math.floor(float(valor) * escala) / escala
    return Decimal(str(truncado)).quantize(Decimal("1").scaleb(-casas), rounding=ROUND_DOWN)


def data_ptbr(dt: date) -> str:
    return dt.strftime("%d/%m/%Y")


def periodo_yyyymm(dt: date) -> str:
    return f"{dt.year:04d}{dt.month:02d}"


def periodo_pt(periodo: str) -> str:
    return f"{periodo[:4]}-{periodo[4:]}"


def add_months_periodo(periodo: str, meses: int) -> str:
    ano = int(periodo[:4])
    mes = int(periodo[4:])
    total = ano * 12 + (mes - 1) + meses
    return f"{total // 12:04d}{total % 12 + 1:02d}"


def add_months_data(dt: date, meses: int) -> date:
    return datetime.strptime(add_months_periodo(periodo_yyyymm(dt), meses), "%Y%m").date()


def iter_periodos(inicio: str, fim: str) -> Iterable[str]:
    atual = inicio
    while atual <= fim:
        yield atual
        atual = add_months_periodo(atual, 1)


def easter_date(year: int) -> date:
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def feriados_nacionais(start_year: int = 2026, end_year: int = 2042) -> set[date]:
    feriados: set[date] = set()
    for ano in range(start_year, end_year + 1):
        pascoa = easter_date(ano)
        feriados.update({
            date(ano, 1, 1),
            pascoa - timedelta(days=48),
            pascoa - timedelta(days=47),
            pascoa - timedelta(days=2),
            date(ano, 4, 21),
            date(ano, 5, 1),
            pascoa + timedelta(days=60),
            date(ano, 9, 7),
            date(ano, 10, 12),
            date(ano, 11, 2),
            date(ano, 11, 15),
            date(ano, 11, 20),
            date(ano, 12, 25),
        })
    return feriados


FERIADOS = feriados_nacionais()


def eh_dia_util(dt: date) -> bool:
    return dt.weekday() < 5 and dt not in FERIADOS


def proximo_dia_util(dt: date) -> date:
    out = dt
    while not eh_dia_util(out):
        out += timedelta(days=1)
    return out


def contar_dias_uteis(inicio: date, fim: date) -> int:
    count = 0
    atual = inicio
    while atual < fim:
        if eh_dia_util(atual):
            count += 1
        atual += timedelta(days=1)
    return count


def iter_dias_uteis_periodo(inicio: date, fim: date, incluir_inicio: bool) -> Iterable[date]:
    atual = inicio if incluir_inicio else inicio + timedelta(days=1)
    while atual <= fim:
        if eh_dia_util(atual):
            yield atual
        atual += timedelta(days=1)


def data_aniversario_mes(ano: int, mes: int) -> date:
    return proximo_dia_util(date(ano, mes, 15))


def aniversario_do_periodo(dt: date) -> Tuple[date, date, str]:
    mes_atual = date(dt.year, dt.month, 1)
    aniversario_atual = data_aniversario_mes(dt.year, dt.month)
    if dt >= aniversario_atual:
        prox_mes = add_months_data(mes_atual, 1)
        return aniversario_atual, data_aniversario_mes(prox_mes.year, prox_mes.month), periodo_yyyymm(mes_atual)

    mes_anterior = add_months_data(mes_atual, -1)
    return data_aniversario_mes(mes_anterior.year, mes_anterior.month), aniversario_atual, periodo_yyyymm(mes_anterior)


def obter_bytes_url(url: str, timeout: int = 45) -> bytes:
    ctx = ssl.create_default_context()
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=timeout, context=ctx) as resp:
        return resp.read()


def obter_json_url(url: str, timeout: int = 45) -> object:
    return json.loads(obter_bytes_url(url, timeout=timeout).decode("utf-8"))


def decimal_ptbr(valor: object) -> Decimal | None:
    if valor is None:
        return None
    txt = str(valor).strip().replace("%", "").replace(" ", "")
    if not txt or txt in {"...", "-", "--"}:
        return None
    if "," in txt and "." in txt:
        txt = txt.replace(".", "").replace(",", ".")
    else:
        txt = txt.replace(",", ".")
    try:
        return Decimal(txt)
    except Exception:
        return None


def parse_mes_referencia(valor: object) -> str | None:
    if valor is None:
        return None
    txt = str(valor).strip()
    if not txt:
        return None
    if len(txt) >= 7 and txt[4] == "-" and txt[:4].isdigit() and txt[5:7].isdigit():
        return txt[:4] + txt[5:7]
    if "/" in txt:
        partes = txt.split("/")
        if len(partes) >= 2 and partes[0].isdigit() and partes[1].isdigit():
            mes = int(partes[0])
            ano = int(partes[1])
            if ano < 100:
                ano += 2000
            if 1 <= mes <= 12:
                return f"{ano:04d}{mes:02d}"
    if len(txt) == 6 and txt.isdigit():
        return txt
    return None


def build_odata_url(recurso: str, params: Dict[str, str], usar_parenteses: bool = True) -> str:
    base = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata"
    sufixo = "()" if usar_parenteses and not recurso.endswith(")") else ""
    return f"{base}/{recurso}{sufixo}?{urlencode(params, quote_via=quote)}"


def obter_focus_odata_mensal() -> Tuple[Dict[str, Decimal], str]:
    recursos = ["ExpectativaMercadoMensais", "ExpectativasMercadoMensais"]
    params = {
        "$top": "10000",
        "$format": "json",
        "$select": "Indicador,Data,DataReferencia,Mediana",
        "$filter": "Indicador eq 'IPCA'",
        "$orderby": "Data desc",
    }
    erros: List[str] = []
    for recurso in recursos:
        for usar_parenteses in (True, False):
            try:
                url = build_odata_url(recurso, params, usar_parenteses=usar_parenteses)
                dados = obter_json_url(url, timeout=30)
                itens = dados.get("value", []) if isinstance(dados, dict) else []
                out: Dict[str, Tuple[str, Decimal]] = {}
                for item in itens:
                    if str(item.get("Indicador", "")).upper() != "IPCA":
                        continue
                    mes = parse_mes_referencia(item.get("DataReferencia"))
                    med = decimal_ptbr(item.get("Mediana"))
                    if not mes or med is None:
                        continue
                    taxa = med / Decimal("100") if abs(med) > Decimal("0.05") else med
                    data_pub = str(item.get("Data", ""))
                    if mes not in out or data_pub > out[mes][0]:
                        out[mes] = (data_pub, taxa)
                if out:
                    nome = recurso + ("()" if usar_parenteses else "")
                    return {m: v[1] for m, v in out.items()}, f"Focus/BCB mensal via OData {nome}"
                erros.append(f"{recurso}: sem registros")
            except Exception as exc:
                erros.append(f"{recurso}: {exc}")
    return {}, "Focus/BCB mensal OData indisponivel: " + " | ".join(erros[:4])


def obter_focus_odata_anual() -> Tuple[Dict[int, Decimal], str]:
    recursos = ["ExpectativasMercadoAnuais", "ExpectativaMercadoAnuais"]
    params = {
        "$top": "10000",
        "$format": "json",
        "$select": "Indicador,Data,DataReferencia,Mediana",
        "$filter": "Indicador eq 'IPCA'",
        "$orderby": "Data desc",
    }
    erros: List[str] = []
    for recurso in recursos:
        for usar_parenteses in (True, False):
            try:
                url = build_odata_url(recurso, params, usar_parenteses=usar_parenteses)
                dados = obter_json_url(url, timeout=30)
                itens = dados.get("value", []) if isinstance(dados, dict) else []
                out: Dict[int, Tuple[str, Decimal]] = {}
                for item in itens:
                    if str(item.get("Indicador", "")).upper() != "IPCA":
                        continue
                    ref = str(item.get("DataReferencia", "")).strip()
                    if not ref.isdigit():
                        continue
                    ano = int(ref)
                    med = decimal_ptbr(item.get("Mediana"))
                    if med is None:
                        continue
                    taxa = med / Decimal("100") if abs(med) > Decimal("0.05") else med
                    data_pub = str(item.get("Data", ""))
                    if ano not in out or data_pub > out[ano][0]:
                        out[ano] = (data_pub, taxa)
                if out:
                    nome = recurso + ("()" if usar_parenteses else "")
                    return {a: v[1] for a, v in out.items()}, f"Focus/BCB anual via OData {nome}"
                erros.append(f"{recurso}: sem registros")
            except Exception as exc:
                erros.append(f"{recurso}: {exc}")
    return {}, "Focus/BCB anual OData indisponivel: " + " | ".join(erros[:4])


def taxa_mensal_por_focus(
    periodo: str,
    focus_mensal: Dict[str, Decimal],
    focus_anual: Dict[int, Decimal],
) -> Tuple[Decimal, str]:
    if periodo in focus_mensal:
        return focus_mensal[periodo], "Focus/BCB mensal"
    ano = int(periodo[:4])
    if ano in focus_anual:
        taxa = (Decimal("1") + focus_anual[ano]) ** (Decimal("1") / Decimal("12")) - Decimal("1")
        return taxa, "Focus/BCB anual convertido para taxa mensal equivalente"
    return IPCA_PROJECAO_MENSAL_PADRAO, "fallback local padrao"


def obter_ipca_sidra(periodo_inicial: str, periodo_final: str) -> Tuple[Dict[str, Decimal], str]:
    url = (
        "https://apisidra.ibge.gov.br/values/"
        f"t/1737/n1/all/v/2266/p/{periodo_inicial}-{periodo_final}?formato=json"
    )
    dados = obter_json_url(url, timeout=60)
    if not isinstance(dados, list) or len(dados) <= 1:
        raise RuntimeError("SIDRA retornou vazio.")
    indices: Dict[str, Decimal] = {}
    for item in dados[1:]:
        if not isinstance(item, dict):
            continue
        periodo = str(item.get("D3C", ""))
        valor = str(item.get("V", "")).replace(",", ".")
        if len(periodo) == 6 and valor not in {"", "...", "-"}:
            indices[periodo] = Decimal(valor)
    if not indices:
        raise RuntimeError("SIDRA sem valores validos.")
    return indices, f"IBGE SIDRA tabela 1737 variavel 2266 | {url}"


def preparar_indices_ipca(periodo_inicial: str, periodo_final: str) -> Tuple[Dict[str, Decimal], Dict[str, str], str]:
    indices, fonte_sidra = obter_ipca_sidra(periodo_inicial, periodo_final)
    fontes = {p: "IBGE/SIDRA numero-indice IPCA" for p in indices}
    focus_mensal, fonte_focus_mensal = obter_focus_odata_mensal()
    focus_anual, fonte_focus_anual = obter_focus_odata_anual()

    ultimo = max(indices)
    ultimo_indice = indices[ultimo]
    for periodo in iter_periodos(add_months_periodo(ultimo, 1), periodo_final):
        taxa, fonte = taxa_mensal_por_focus(periodo, focus_mensal, focus_anual)
        ultimo_indice = trunc_dec(ultimo_indice * (Decimal("1") + taxa), 13)
        indices[periodo] = ultimo_indice
        fontes[periodo] = f"{fonte} | {fonte_focus_mensal} | {fonte_focus_anual}"

    return indices, fontes, fonte_sidra


def fator_ipca_periodo(
    inicio: date,
    fim: date,
    indices: Dict[str, Decimal],
    fontes: Dict[str, str],
) -> Tuple[Decimal, int, str, str, Decimal, Decimal, str]:
    if fim <= inicio:
        return Decimal("1.00000000"), 0, "", "", Decimal("0"), Decimal("0"), ""

    acumulado = Decimal("1.0000000000000000")
    du_total = 0
    ultimo_nik = ""
    ultimo_nik_1 = ""
    ultimo_ni = Decimal("0")
    ultimo_ni_1 = Decimal("0")
    fontes_usadas: set[str] = set()

    cursor = inicio
    while cursor < fim:
        ult_aniv, prox_aniv, mes_nik = aniversario_do_periodo(cursor)
        seg_fim = min(fim, prox_aniv)
        du_seg = contar_dias_uteis(cursor, seg_fim)
        dut = contar_dias_uteis(ult_aniv, prox_aniv)
        mes_nik_1 = add_months_periodo(mes_nik, -1)
        if mes_nik not in indices or mes_nik_1 not in indices:
            raise RuntimeError(f"IPCA ausente para {mes_nik}/{mes_nik_1}.")
        if du_seg > 0:
            razao = trunc_dec(indices[mes_nik] / indices[mes_nik_1], 8)
            fator_seg = trunc_float_dec(math.pow(float(razao), du_seg / dut), 8)
            acumulado = trunc_dec(acumulado * fator_seg, 16)
            du_total += du_seg
            fontes_usadas.add(fontes.get(mes_nik, ""))
            fontes_usadas.add(fontes.get(mes_nik_1, ""))
        ultimo_nik = mes_nik
        ultimo_nik_1 = mes_nik_1
        ultimo_ni = indices[mes_nik]
        ultimo_ni_1 = indices[mes_nik_1]
        cursor = seg_fim

    return (
        trunc_dec(acumulado, 8),
        du_total,
        ultimo_nik,
        ultimo_nik_1,
        ultimo_ni,
        ultimo_ni_1,
        " | ".join(sorted(x for x in fontes_usadas if x)),
    )


def fator_juros(taxa_aa: Decimal, inicio: date, fim: date, data_evento: date) -> Tuple[Decimal, int, int, int]:
    dp = contar_dias_uteis(inicio, fim)
    dt = contar_dias_uteis(inicio, data_evento)
    n = dt
    if dp == 0 or dt == 0:
        return Decimal("1.000000000"), n, dt, dp
    fator_periodo = (Decimal("1") + taxa_aa) ** (Decimal(n) / BASE_DU)
    fator = fator_periodo ** (Decimal(dp) / Decimal(dt))
    return round_dec(fator, 9), n, dt, dp


def eventos_cronograma() -> List[Dict[str, object]]:
    linhas = []
    for data_txt, p1, p2, tipo in CRONOGRAMA_RAW:
        data_civil = datetime.strptime(data_txt, "%Y-%m-%d").date()
        data_pagto = proximo_dia_util(data_civil)
        linhas.append({
            "Data_Ref": data_ptbr(data_civil),
            "Data_Pgto": data_ptbr(data_pagto),
            "Data_Civil": data_civil,
            "Data_Evento": data_pagto,
            "Perc_Amort_S1": Decimal(p1) / Decimal("100"),
            "Perc_Amort_S2": Decimal(p2) / Decimal("100"),
            "Tipo_Evento": tipo,
        })
    return linhas


CRONOGRAMA = eventos_cronograma()


def calcular_serie(
    serie: Serie,
    indices: Dict[str, Decimal],
    fontes: Dict[str, str],
) -> Tuple[List[Dict[str, object]], List[Dict[str, object]]]:
    eventos: List[Dict[str, object]] = []
    diario: List[Dict[str, object]] = []
    saldo_base = PU_INICIAL
    inicio_periodo = DATA_INICIO_RENTABILIDADE

    for idx, evento in enumerate(CRONOGRAMA):
        data_evento = evento["Data_Evento"]  # type: ignore[assignment]
        perc_amort = evento[serie.perc_amort_key]  # type: ignore[index]
        tipo_evento = str(evento["Tipo_Evento"])
        incluir_inicio = idx == 0

        linha_evento: Dict[str, object] | None = None
        for data_calc in iter_dias_uteis_periodo(inicio_periodo, data_evento, incluir_inicio):
            fator_c, du_ipca, nik, nik_1, ni, ni_1, fonte_ipca = fator_ipca_periodo(
                inicio_periodo, data_calc, indices, fontes
            )
            fator_j, n_juros, dt_juros, dp_juros = fator_juros(
                serie.taxa_aa, inicio_periodo, data_calc, data_evento
            )
            vna = trunc_dec(saldo_base * fator_c, 8)
            juros = trunc_dec(vna * (fator_j - Decimal("1")), 8) if dp_juros else Decimal("0.00000000")
            eh_evento = data_calc == data_evento
            incorpora = eh_evento and tipo_evento == "INCORPORACAO"
            paga = eh_evento and tipo_evento == "PAGAMENTO"

            amort = trunc_dec(vna * perc_amort, 8) if paga else Decimal("0.00000000")
            if paga and data_evento == CRONOGRAMA[-1]["Data_Evento"]:
                amort = vna
            juros_pago = juros if paga else Decimal("0.00000000")
            juros_capitalizado = juros if incorpora else Decimal("0.00000000")
            saldo_pos = trunc_dec(vna + juros_capitalizado - amort, 8) if eh_evento else Decimal("0.00000000")
            pu_cheio = trunc_dec(vna + juros, 8)
            pu_vazio = saldo_pos if eh_evento else pu_cheio
            total = trunc_dec(juros_pago + amort, 8)

            diario.append({
                "Serie": serie.nome,
                "Codigo_IF": serie.codigo_if,
                "ISIN": serie.isin,
                "Data": data_ptbr(data_calc),
                "Data_ISO": data_calc.isoformat(),
                "Data_Inicio_Periodo": data_ptbr(inicio_periodo),
                "Data_Proximo_Evento": data_ptbr(data_evento),
                "Tipo_Evento": tipo_evento if eh_evento else "",
                "DU_IPCA": du_ipca,
                "DU_Juros": dp_juros,
                "DT_Juros": dt_juros,
                "N_Juros": n_juros,
                "Mes_NIk": nik,
                "Mes_NIk_1": nik_1,
                "NIk": ni,
                "NIk_1": ni_1,
                "Fator_C_IPCA": fator_c,
                "Taxa_Juros_aa": serie.taxa_aa,
                "Fator_Juros": fator_j,
                "Valor_Nominal": vna,
                "Valor_dos_Juros": juros,
                "PU_Cheio": pu_cheio,
                "PU_Vazio": pu_vazio,
                "Juros_%": round_dec(juros, 2) if eh_evento else Decimal("0.00"),
                "Amortizacao": amort,
                "Juros_Pago": juros_pago,
                "Juros_Capitalizado": juros_capitalizado,
                "Total": total,
                "Saldo_Pos_Evento": saldo_pos if eh_evento else "",
                "Fonte_IPCA": fonte_ipca,
            })

            if eh_evento:
                juros_rs = round_dec(juros_pago * serie.quantidade, 2)
                juros_cap_rs = round_dec(juros_capitalizado * serie.quantidade, 2)
                amort_rs = round_dec(amort * serie.quantidade, 2)
                linha_evento = {
                    "Serie": serie.nome,
                    "Codigo_IF": serie.codigo_if,
                    "ISIN": serie.isin,
                    "Data_Ref": evento["Data_Ref"],
                    "Data_Pgto": data_ptbr(data_evento),
                    "Tipo_Evento": tipo_evento,
                    "DU_IPCA": du_ipca,
                    "DU_Juros": dp_juros,
                    "DT_Juros": dt_juros,
                    "N_Juros": n_juros,
                    "Mes_NIk": nik,
                    "Mes_NIk_1": nik_1,
                    "NIk": ni,
                    "NIk_1": ni_1,
                    "Fator_C_IPCA": fator_c,
                    "Taxa_Juros_aa": serie.taxa_aa,
                    "Fator_Juros": fator_j,
                    "Perc_Amort": perc_amort,
                    "PU_VNa_Ini": saldo_base,
                    "PU_VNa_Atualizado": vna,
                    "PU_Juros": juros,
                    "PU_Juros_Pago": juros_pago,
                    "PU_Juros_Capitalizado": juros_capitalizado,
                    "PU_Amort": amort,
                    "PU_Total": total,
                    "PU_VNa_Fim": saldo_pos,
                    "Juros_R$": juros_rs,
                    "Juros_Capitalizado_R$": juros_cap_rs,
                    "Amort_R$": amort_rs,
                    "PMT_Total": round_dec(juros_rs + amort_rs, 2),
                    "Saldo_Devedor_R$": round_dec(saldo_pos * serie.quantidade, 2),
                    "Fonte_IPCA": fonte_ipca,
                }

        if linha_evento is None:
            raise RuntimeError(f"Evento nao calculado para {serie.codigo_if} em {data_ptbr(data_evento)}.")
        eventos.append(linha_evento)
        saldo_base = linha_evento["PU_VNa_Fim"]  # type: ignore[assignment]
        inicio_periodo = data_evento

    return eventos, diario


def caminho_alternativo(caminho: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return caminho.with_name(f"{caminho.stem}_{timestamp}{caminho.suffix}")


def salvar_com_fallback(funcao_salvar, caminho: Path, *args) -> Tuple[Path, bool]:
    try:
        funcao_salvar(*args, caminho)
        return caminho, False
    except PermissionError:
        alternativo = caminho_alternativo(caminho)
        funcao_salvar(*args, alternativo)
        return alternativo, True


def decimal_para_csv(valor: object) -> object:
    if isinstance(valor, Decimal):
        return format(valor, "f").replace(".", ",")
    return valor


def decimal_para_excel(valor: object) -> object:
    if isinstance(valor, Decimal):
        return float(valor)
    return valor


def salvar_csv(linhas: List[Dict[str, object]], caminho: Path) -> None:
    if not linhas:
        raise RuntimeError(f"Nenhuma linha para salvar em {caminho.name}.")
    caminho.parent.mkdir(parents=True, exist_ok=True)
    campos = list(linhas[0].keys())
    with caminho.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=campos, delimiter=";")
        writer.writeheader()
        for linha in linhas:
            writer.writerow({k: decimal_para_csv(v) for k, v in linha.items()})


def salvar_xlsx(linhas: List[Dict[str, object]], caminho: Path) -> None:
    if not linhas:
        raise RuntimeError(f"Nenhuma linha para salvar em {caminho.name}.")
    import pandas as pd

    caminho.parent.mkdir(parents=True, exist_ok=True)
    dados = [{k: decimal_para_excel(v) for k, v in linha.items()} for linha in linhas]
    pd.DataFrame(dados).to_excel(caminho, index=False)


def parametros_saida(fonte_ipca: str) -> List[Dict[str, object]]:
    linhas = []
    for serie in SERIES:
        linhas.append({
            "Serie": serie.nome,
            "Codigo_IF": serie.codigo_if,
            "ISIN": serie.isin,
            "Quantidade": serie.quantidade,
            "PU_Inicial": PU_INICIAL,
            "Data_Emissao": data_ptbr(DATA_EMISSAO),
            "Data_Inicio_Rentabilidade": data_ptbr(DATA_INICIO_RENTABILIDADE),
            "Data_Vencimento": data_ptbr(DATA_VENCIMENTO),
            "Remuneracao": f"IPCA + {serie.taxa_aa * Decimal('100')}% a.a.",
            "Base_DU": BASE_DU,
            "Fonte_IPCA": fonte_ipca,
        })
    return linhas


def cronograma_saida() -> List[Dict[str, object]]:
    linhas = []
    for row in CRONOGRAMA:
        linhas.append({
            "Data_Ref": row["Data_Ref"],
            "Data_Pgto": row["Data_Pgto"],
            "Tipo_Evento": row["Tipo_Evento"],
            "Perc_Amort_S1": row["Perc_Amort_S1"],
            "Perc_Amort_S2": row["Perc_Amort_S2"],
        })
    return linhas


def salvar_workbook(
    eventos: List[Dict[str, object]],
    diario: List[Dict[str, object]],
    parametros: List[Dict[str, object]],
    cronograma: List[Dict[str, object]],
    caminho: Path,
) -> None:
    import pandas as pd

    caminho.parent.mkdir(parents=True, exist_ok=True)

    def to_df(linhas: List[Dict[str, object]]) -> "pd.DataFrame":
        return pd.DataFrame([{k: decimal_para_excel(v) for k, v in linha.items()} for linha in linhas])

    with pd.ExcelWriter(caminho, engine="openpyxl") as writer:
        to_df(eventos).to_excel(writer, sheet_name="Eventos", index=False)
        to_df(diario).to_excel(writer, sheet_name="Historico_PU", index=False)
        to_df(parametros).to_excel(writer, sheet_name="Parametros", index=False)
        to_df(cronograma).to_excel(writer, sheet_name="Cronograma", index=False)


def main() -> None:
    periodo_inicial = "202601"
    periodo_final = "204202"
    indices_ipca, fontes_ipca, fonte_ipca = preparar_indices_ipca(periodo_inicial, periodo_final)

    eventos: List[Dict[str, object]] = []
    diario: List[Dict[str, object]] = []
    for serie in SERIES:
        eventos_serie, diario_serie = calcular_serie(serie, indices_ipca, fontes_ipca)
        eventos.extend(eventos_serie)
        diario.extend(diario_serie)

    parametros = parametros_saida(fonte_ipca)
    cronograma = cronograma_saida()

    saidas: List[Tuple[Path, bool]] = []
    for caminho, linhas in [
        (ARQ_EVENTOS_CSV, eventos),
        (ARQ_DIARIO_CSV, diario),
        (ARQ_EVENTOS_XLSX, eventos),
        (ARQ_DIARIO_XLSX, diario),
    ]:
        func = salvar_csv if caminho.suffix.lower() == ".csv" else salvar_xlsx
        gerado, fallback = salvar_com_fallback(func, caminho, linhas)
        saidas.append((gerado, fallback))

    gerado, fallback = salvar_com_fallback(
        salvar_workbook, ARQ_COMPLETO_XLSX, eventos, diario, parametros, cronograma
    )
    saidas.append((gerado, fallback))

    print("Fonte IPCA:", fonte_ipca)
    print("Arquivos gerados:")
    for caminho, fallback in saidas:
        aviso = " (alternativo; padrao estava aberto)" if fallback else ""
        print(f"- {caminho}{aviso}")

    print("\nPrimeiros eventos por serie:")
    for linha in eventos[:6]:
        print(
            f"{linha['Codigo_IF']} {linha['Data_Pgto']} {linha['Tipo_Evento']} | "
            f"VNA {linha['PU_VNa_Atualizado']} | Juros {linha['PU_Juros']} | "
            f"Amort {linha['PU_Amort']} | Saldo {linha['PU_VNa_Fim']}"
        )


if __name__ == "__main__":
    main()
