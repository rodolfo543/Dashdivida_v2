# -*- coding: utf-8 -*-
"""
AXS Energia Unidade 07 - Debenture AXSU11 - calculo PMT padrao ANBIMA com projecao Focus/BCB
Versao v15.

Objetivo
- Replicar o calculo dos eventos da debenture sem imputar valores calculados pela Vortx.
- Para meses futuros sem IPCA oficial no SIDRA/IBGE, projetar pelo Focus/BCB quando disponivel.
- Usa a escritura/aditamento: IPCA mensal, aniversario dia 15, juros 10,50% a.a. base 252,
  VNA/Juros/Amortizacao com 8 casas sem arredondamento e fator de juros com 9 casas
  com arredondamento.

Ajuste principal vs versoes anteriores
- Para o evento/aniversario do mes M, o NIk correto e o numero-indice do IPCA do mes M-1
  e o NIk-1 e o mes M-2.
  Ex.: evento 16/03/2026, aniversario 15/03/2026 -> NIk=2026-02 e NIk-1=2026-01.
- Esse deslocamento corrige o VNA base. Quando o VNA base esta errado, juros e amortizacao
  ficam diferentes pelo mesmo percentual, exatamente o sintoma observado.

Como rodar
    python axs07_v15_focus_bcb.py

Arquivos gerados
    controle_divida_axs07_v15_focus.csv

Dependencia opcional
    pip install python-bcb

Se python-bcb nao estiver instalado, o script tenta consultar o Focus via OData do BCB.
Se as consultas externas falharem, usa fallback local apenas para nao interromper a execucao.
"""

from __future__ import annotations

import csv
import json
import ssl
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP, getcontext
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.request import Request, urlopen
from urllib.parse import quote, urlencode
import importlib.util

getcontext().prec = 34

DATA_INICIO_RENTABILIDADE = date(2024, 4, 29)
TAXA_AA = Decimal("0.105")
QUANTIDADE = Decimal("75500")
PU_INICIAL = Decimal("1000.00000000")

CRONOGRAMA_RAW = [
    ("2024-05-15", "0.1001"), ("2024-06-17", "0.1002"), ("2024-07-15", "0.1003"),
    ("2024-08-15", "0.1004"), ("2024-09-16", "0.1005"), ("2024-10-15", "0.1006"),
    ("2024-11-18", "0.1007"), ("2024-12-16", "0.1008"), ("2025-01-15", "0.1009"),
    ("2025-02-17", "0.1010"), ("2025-03-17", "0.1011"), ("2025-04-15", "0.7085"),
    ("2025-05-15", "0.7136"), ("2025-06-16", "0.7187"), ("2025-07-15", "0.7239"),
    ("2025-08-15", "0.7292"), ("2025-09-15", "0.7345"), ("2025-10-15", "0.7400"),
    ("2025-11-17", "0.7455"), ("2025-12-15", "0.7511"), ("2026-01-15", "0.7568"),
    ("2026-02-18", "0.7625"), ("2026-03-16", "0.7684"), ("2026-04-15", "0.7743"),
    ("2026-05-15", "1.0033"), ("2026-06-15", "1.0135"), ("2026-07-15", "1.0239"),
    ("2026-08-17", "1.0345"), ("2026-09-15", "1.0453"), ("2026-10-15", "1.0563"),
    ("2026-11-16", "1.0676"), ("2026-12-15", "1.0791"), ("2027-01-15", "1.0909"),
    ("2027-02-15", "1.1029"), ("2027-03-15", "1.1152"), ("2027-04-15", "1.1278"),
    ("2027-05-17", "1.1407"), ("2027-06-15", "1.1538"), ("2027-07-15", "1.1673"),
    ("2027-08-16", "1.1811"), ("2027-09-15", "1.1952"), ("2027-10-15", "1.2097"),
    ("2027-11-16", "1.2245"), ("2027-12-15", "1.3774"), ("2028-01-17", "1.3966"),
    ("2028-02-15", "1.4164"), ("2028-03-15", "1.4368"), ("2028-04-17", "1.4577"),
    ("2028-05-15", "1.4793"), ("2028-06-16", "1.5015"), ("2028-07-17", "1.5244"),
    ("2028-08-15", "1.5480"), ("2028-09-15", "1.5723"), ("2028-10-16", "1.5974"),
    ("2028-11-16", "1.6234"), ("2028-12-15", "1.6502"), ("2029-01-15", "1.6779"),
    ("2029-02-15", "1.7065"), ("2029-03-15", "1.7361"), ("2029-04-16", "1.7668"),
    ("2029-05-15", "1.7986"), ("2029-06-15", "1.8315"), ("2029-07-16", "1.8657"),
    ("2029-08-15", "1.9011"), ("2029-09-17", "1.9380"), ("2029-10-15", "1.9763"),
    ("2029-11-16", "2.0161"), ("2029-12-17", "2.0576"), ("2030-01-15", "2.1008"),
    ("2030-02-15", "2.1459"), ("2030-03-15", "2.1930"), ("2030-04-15", "2.2422"),
    ("2030-05-15", "2.2936"), ("2030-06-17", "2.3474"), ("2030-07-15", "2.4038"),
    ("2030-08-15", "2.4631"), ("2030-09-16", "2.5253"), ("2030-10-15", "2.5907"),
    ("2030-11-18", "2.6596"), ("2030-12-16", "2.7322"), ("2031-01-15", "2.8090"),
    ("2031-02-17", "2.8902"), ("2031-03-17", "2.9762"), ("2031-04-15", "3.0675"),
    ("2031-05-15", "3.1646"), ("2031-06-16", "3.2680"), ("2031-07-15", "3.3784"),
    ("2031-08-15", "3.4965"), ("2031-09-15", "3.6232"), ("2031-10-15", "3.7594"),
    ("2031-11-17", "3.9063"), ("2031-12-15", "4.0650"), ("2032-01-15", "4.2373"),
    ("2032-02-16", "4.4248"), ("2032-03-15", "4.6296"), ("2032-04-15", "4.8544"),
    ("2032-05-17", "5.1020"), ("2032-06-15", "5.3763"), ("2032-07-15", "5.6818"),
    ("2032-08-16", "9.0361"), ("2032-09-15", "9.9338"), ("2032-10-15", "11.0294"),
    ("2032-11-16", "12.3967"), ("2032-12-15", "7.5472"), ("2033-01-17", "8.1633"),
    ("2033-02-15", "8.8889"), ("2033-03-15", "9.7561"), ("2033-04-18", "10.8108"),
    ("2033-05-16", "12.1212"), ("2033-06-15", "13.7931"), ("2033-07-15", "16.0000"),
    ("2033-08-15", "19.0476"), ("2033-09-15", "14.7059"), ("2033-10-17", "17.2414"),
    ("2033-11-16", "20.8333"), ("2033-12-15", "26.3158"), ("2034-01-16", "35.7143"),
    ("2034-02-15", "55.5556"), ("2034-03-15", "100.0000"),
]
CRONOGRAMA = [(datetime.strptime(d, "%Y-%m-%d").date(), Decimal(p) / Decimal("100")) for d, p in CRONOGRAMA_RAW]

# Fallback oficial/conhecido para a fase que estamos auditando. Se o SIDRA estiver disponivel,
# ele sera usado no lugar destes valores.
IPCA_FALLBACK_VARIACAO_MENSAL = {
    "2024-02": Decimal("0.0083"), "2024-03": Decimal("0.0016"), "2024-04": Decimal("0.0038"),
    "2024-05": Decimal("0.0046"), "2024-06": Decimal("0.0021"), "2024-07": Decimal("0.0038"),
    "2024-08": Decimal("-0.0002"), "2024-09": Decimal("0.0044"), "2024-10": Decimal("0.0056"),
    "2024-11": Decimal("0.0039"), "2024-12": Decimal("0.0052"), "2025-01": Decimal("0.0016"),
    "2025-02": Decimal("0.0131"), "2025-03": Decimal("0.0056"), "2025-04": Decimal("0.0043"),
    "2025-05": Decimal("0.0026"), "2025-06": Decimal("0.0024"), "2025-07": Decimal("0.0026"),
    "2025-08": Decimal("-0.0011"), "2025-09": Decimal("0.0048"), "2025-10": Decimal("0.0009"),
    "2025-11": Decimal("0.0018"), "2025-12": Decimal("0.0033"), "2026-01": Decimal("0.0033"),
    "2026-02": Decimal("0.0070"), "2026-03": Decimal("0.0088"),
}
IPCA_PROJECAO_MENSAL_PADRAO = Decimal("0.0045")


def trunc_dec(x: Decimal, casas: int = 8) -> Decimal:
    return x.quantize(Decimal("1").scaleb(-casas), rounding=ROUND_DOWN)


def round_dec(x: Decimal, casas: int = 2) -> Decimal:
    return x.quantize(Decimal("1").scaleb(-casas), rounding=ROUND_HALF_UP)


def add_months(dt: date, months: int) -> date:
    y = dt.year + (dt.month - 1 + months) // 12
    m = (dt.month - 1 + months) % 12 + 1
    return date(y, m, 1)


def mes_str(dt: date) -> str:
    return f"{dt.year:04d}-{dt.month:02d}"


def aniversario(data_pagto: date) -> date:
    return date(data_pagto.year, data_pagto.month, 15)


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


def feriados_nacionais(start_year: int = 2024, end_year: int = 2034) -> set[date]:
    fs: set[date] = set()
    for y in range(start_year, end_year + 1):
        pascoa = easter_date(y)
        fs.update({
            date(y, 1, 1),
            pascoa - timedelta(days=48),  # Carnaval segunda
            pascoa - timedelta(days=47),  # Carnaval terca
            pascoa - timedelta(days=2),   # Sexta-feira santa
            date(y, 4, 21),
            date(y, 5, 1),
            pascoa + timedelta(days=60),  # Corpus Christi
            date(y, 9, 7),
            date(y, 10, 12),
            date(y, 11, 2),
            date(y, 11, 15),
            date(y, 11, 20),
            date(y, 12, 25),
        })
    return fs


FERIADOS = feriados_nacionais()


def eh_dia_util(dt: date) -> bool:
    return dt.weekday() < 5 and dt not in FERIADOS


def dias_uteis(inicio: date, fim: date) -> int:
    """Conta dias uteis em [inicio, fim), conforme convencao de juros."""
    count = 0
    dt = inicio
    while dt < fim:
        if eh_dia_util(dt):
            count += 1
        dt += timedelta(days=1)
    return count


def periodo_final_sidra() -> str:
    max_aniv = max(aniversario(d) for d, _ in CRONOGRAMA)
    fim = add_months(max_aniv, 1)
    return f"{fim.year:04d}{fim.month:02d}"


def indices_fallback() -> Dict[str, Decimal]:
    idx = Decimal("7000.0000000000000")
    indices: Dict[str, Decimal] = {}
    for m in sorted(IPCA_FALLBACK_VARIACAO_MENSAL):
        idx = idx * (Decimal("1") + IPCA_FALLBACK_VARIACAO_MENSAL[m])
        indices[m] = idx
    return indices


def obter_ipca_numero_indice_sidra() -> Tuple[Dict[str, Decimal], str]:
    """Busca numero-indice IPCA no SIDRA. Se falhar, usa fallback local."""
    fim = periodo_final_sidra()
    url = f"https://apisidra.ibge.gov.br/values/t/1737/n1/all/v/2266/p/202402-{fim}?formato=json"
    try:
        ctx = ssl.create_default_context()
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=12, context=ctx) as resp:
            dados = json.loads(resp.read().decode("utf-8"))
        indices: Dict[str, Decimal] = {}
        for item in dados[1:]:
            periodo = str(item.get("D3C", ""))
            valor = str(item.get("V", "")).replace(",", ".")
            if len(periodo) == 6 and valor not in ("", "...", "-"):
                indices[f"{periodo[:4]}-{periodo[4:]}"] = Decimal(valor)
        if not indices:
            raise RuntimeError("SIDRA retornou vazio ou layout inesperado")
        return indices, f"SIDRA/IBGE Tabela 1737 v/2266 | {url}"
    except Exception as exc:
        return indices_fallback(), f"FALLBACK local por variacao mensal IPCA; motivo: {exc}"




def decimal_ptbr(valor: object) -> Decimal | None:
    if valor is None:
        return None
    txt = str(valor).strip().replace("%", "").replace(" ", "")
    if not txt or txt in ("...", "-", "--"):
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
    """Converte DataReferencia do Focus para AAAA-MM."""
    if valor is None:
        return None
    txt = str(valor).strip()
    if not txt:
        return None
    if len(txt) >= 7 and txt[4] == "-" and txt[:4].isdigit() and txt[5:7].isdigit():
        return txt[:7]
    if "/" in txt:
        partes = txt.split("/")
        if len(partes) >= 2 and partes[0].isdigit() and partes[1].isdigit():
            mes = int(partes[0])
            ano = int(partes[1])
            if ano < 100:
                ano += 2000
            if 1 <= mes <= 12:
                return f"{ano:04d}-{mes:02d}"
    if len(txt) == 6 and txt.isdigit():
        return f"{txt[:4]}-{txt[4:]}"
    return None


def obter_json_url(url: str, timeout: int = 20) -> object:
    ctx = ssl.create_default_context()
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=timeout, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8"))


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


def obter_focus_python_bcb() -> Tuple[Dict[str, Decimal], Dict[int, Decimal], str]:
    """Tenta usar a biblioteca python-bcb. Se nao estiver instalada, retorna vazio."""
    try:
        if importlib.util.find_spec("bcb") is None:
            return {}, {}, "python-bcb nao instalado"
        from bcb import Expectativas  # type: ignore
        em = Expectativas()
    except Exception as exc:
        return {}, {}, f"python-bcb indisponivel: {exc}"

    mensagens: List[str] = []
    mensal: Dict[str, Decimal] = {}
    anual: Dict[int, Decimal] = {}

    try:
        ep = em.get_endpoint("ExpectativaMercadoMensais")
        df = (
            ep.query()
            .filter(ep.Indicador == "IPCA")
            .select(ep.Indicador, ep.Data, ep.DataReferencia, ep.Mediana)
            .orderby(ep.Data.desc())
            .limit(20000)
            .collect()
        )
        temp: Dict[str, Tuple[str, Decimal]] = {}
        for item in df.to_dict("records"):
            mes = parse_mes_referencia(item.get("DataReferencia"))
            med = decimal_ptbr(item.get("Mediana"))
            if not mes or med is None:
                continue
            taxa = med / Decimal("100") if abs(med) > Decimal("0.05") else med
            data_pub = str(item.get("Data", ""))
            if mes not in temp or data_pub > temp[mes][0]:
                temp[mes] = (data_pub, taxa)
        mensal = {m: v[1] for m, v in temp.items()}
        mensagens.append(f"python-bcb mensal: {len(mensal)} meses")
    except Exception as exc:
        mensagens.append(f"python-bcb mensal falhou: {exc}")

    try:
        ep = em.get_endpoint("ExpectativasMercadoAnuais")
        df = (
            ep.query()
            .filter(ep.Indicador == "IPCA")
            .select(ep.Indicador, ep.Data, ep.DataReferencia, ep.Mediana)
            .orderby(ep.Data.desc())
            .limit(20000)
            .collect()
        )
        temp2: Dict[int, Tuple[str, Decimal]] = {}
        for item in df.to_dict("records"):
            ref = str(item.get("DataReferencia", "")).strip()
            med = decimal_ptbr(item.get("Mediana"))
            if not ref.isdigit() or med is None:
                continue
            ano = int(ref)
            taxa = med / Decimal("100") if abs(med) > Decimal("0.05") else med
            data_pub = str(item.get("Data", ""))
            if ano not in temp2 or data_pub > temp2[ano][0]:
                temp2[ano] = (data_pub, taxa)
        anual = {a: v[1] for a, v in temp2.items()}
        mensagens.append(f"python-bcb anual: {len(anual)} anos")
    except Exception as exc:
        mensagens.append(f"python-bcb anual falhou: {exc}")

    return mensal, anual, " | ".join(mensagens)


def obter_focus_ipca() -> Tuple[Dict[str, Decimal], Dict[int, Decimal], str]:
    mensal, anual, fonte_py = obter_focus_python_bcb()
    fontes = [fonte_py]
    if not mensal:
        mensal, fonte_m = obter_focus_odata_mensal()
        fontes.append(fonte_m)
    if not anual:
        anual, fonte_a = obter_focus_odata_anual()
        fontes.append(fonte_a)
    return mensal, anual, " ; ".join(fontes)


def taxa_mensal_por_focus(mes: str, focus_mensal: Dict[str, Decimal], focus_anual: Dict[int, Decimal]) -> Tuple[Decimal, str]:
    if mes in focus_mensal:
        return focus_mensal[mes], "Focus/BCB mensal"
    ano = int(mes[:4])
    if ano in focus_anual:
        taxa = (Decimal("1") + focus_anual[ano]) ** (Decimal("1") / Decimal("12")) - Decimal("1")
        return taxa, "Focus/BCB anual convertido para taxa mensal equivalente"
    return IPCA_PROJECAO_MENSAL_PADRAO, "fallback local padrao"

def preencher_indices_futuros(indices: Dict[str, Decimal]) -> Tuple[Dict[str, Decimal], Dict[str, str]]:
    """Completa meses ainda nao divulgados usando Focus/BCB.

    Regra:
    1) Mantem numero-indice oficial do SIDRA/IBGE quando existir.
    2) Para meses futuros, usa expectativa Focus mensal do BCB quando disponivel.
    3) Se nao houver mensal, usa expectativa Focus anual convertida para taxa mensal equivalente.
    4) Se tudo falhar, usa IPCA_PROJECAO_MENSAL_PADRAO.
    """
    out = dict(indices)
    fontes = {m: "SIDRA/IBGE ou fallback oficial" for m in out}
    focus_mensal, focus_anual, fonte_focus = obter_focus_ipca()

    ultimo_mes = max(out)
    ultimo_indice = out[ultimo_mes]
    mes_atual = add_months(date(int(ultimo_mes[:4]), int(ultimo_mes[5:7]), 1), 1)
    fim = mes_str(add_months(max(aniversario(d) for d, _ in CRONOGRAMA), -1))

    while mes_str(mes_atual) <= fim:
        m = mes_str(mes_atual)
        # Se houver valor oficial/conhecido no fallback local, ele prevalece sobre Focus.
        if m in IPCA_FALLBACK_VARIACAO_MENSAL:
            taxa = IPCA_FALLBACK_VARIACAO_MENSAL[m]
            fonte_taxa = "fallback oficial/conhecido local"
        else:
            taxa, fonte_taxa = taxa_mensal_por_focus(m, focus_mensal, focus_anual)
        ultimo_indice = ultimo_indice * (Decimal("1") + taxa)
        out[m] = ultimo_indice
        fontes[m] = f"{fonte_taxa} | {fonte_focus}"
        mes_atual = add_months(mes_atual, 1)
    return out, fontes

def fator_ipca(indices: Dict[str, Decimal], data_aniv: date) -> Tuple[Decimal, str, str, Decimal, Decimal]:
    """Fator IPCA mensal correto para a Data de Aniversario.

    Para o aniversario do mes M, usa NIk=M-1 e NIk-1=M-2.
    """
    mes_nik = mes_str(add_months(data_aniv, -1))
    mes_nik_1 = mes_str(add_months(data_aniv, -2))
    if mes_nik not in indices or mes_nik_1 not in indices:
        raise RuntimeError(f"IPCA necessario nao disponivel: NIk={mes_nik}, NIk_1={mes_nik_1}.")
    ni_k = indices[mes_nik]
    ni_k_1 = indices[mes_nik_1]
    fator = trunc_dec(ni_k / ni_k_1, 8)
    return fator, mes_nik, mes_nik_1, ni_k, ni_k_1


def fator_ipca_prorata(indices: Dict[str, Decimal], data_aniv: date, inicio: date) -> Tuple[Decimal, str, str, Decimal, Decimal, int, int]:
    """Fator IPCA pro rata usado somente no primeiro periodo, da integralizacao ao primeiro aniversario."""
    fator_cheio, mes_nik, mes_nik_1, ni_k, ni_k_1 = fator_ipca(indices, data_aniv)
    prev_m = add_months(data_aniv, -1)
    inicio_aniv = date(prev_m.year, prev_m.month, 15)
    dup = dias_uteis(inicio, data_aniv)
    dut = dias_uteis(inicio_aniv, data_aniv)
    bruto = Decimal(str(float(ni_k / ni_k_1) ** (dup / dut)))
    return trunc_dec(bruto, 8), mes_nik, mes_nik_1, ni_k, ni_k_1, dup, dut


def fator_juros_252(du: int) -> Decimal:
    bruto = Decimal(str((1.0 + float(TAXA_AA)) ** (du / 252.0)))
    return bruto.quantize(Decimal("0.000000001"), rounding=ROUND_HALF_UP)


def calcular_fluxo() -> Tuple[List[Dict[str, object]], str]:
    indices, fonte = obter_ipca_numero_indice_sidra()
    indices, fonte_mes = preencher_indices_futuros(indices)

    saldo_pu = trunc_dec(PU_INICIAL, 8)
    data_ref_juros = DATA_INICIO_RENTABILIDADE
    linhas: List[Dict[str, object]] = []

    for data_pagto, perc_amort in CRONOGRAMA:
        data_aniv = aniversario(data_pagto)
        pu_vna_ini = trunc_dec(saldo_pu, 8)
        
        if data_pagto == CRONOGRAMA[0][0]:
            fator_c, mes_nik, mes_nik_1, ni_k, ni_k_1, dup_ipca, dut_ipca = fator_ipca_prorata(indices, data_aniv, DATA_INICIO_RENTABILIDADE)
        else:
            fator_c, mes_nik, mes_nik_1, ni_k, ni_k_1 = fator_ipca(indices, data_aniv)
            prev_m = add_months(data_aniv, -1)
            prev_aniv = date(prev_m.year, prev_m.month, 15)
            dup_ipca, dut_ipca = dias_uteis(prev_aniv, data_aniv), dias_uteis(prev_aniv, data_aniv)

        du = dias_uteis(data_ref_juros, data_pagto)
        fj = fator_juros_252(du)

        pu_vna_atualizado = trunc_dec(pu_vna_ini * fator_c, 8)
        pu_juros = trunc_dec(pu_vna_atualizado * (fj - Decimal("1")), 8)
        pu_amort = trunc_dec(pu_vna_atualizado * perc_amort, 8)
        pu_vna_fim = trunc_dec(pu_vna_atualizado - pu_amort, 8)

        juros_rs = round_dec(pu_juros * QUANTIDADE, 2)
        amort_rs = round_dec(pu_amort * QUANTIDADE, 2)
        pmt_rs = round_dec(juros_rs + amort_rs, 2)
        saldo_rs = round_dec(pu_vna_fim * QUANTIDADE, 2)

        linhas.append({
            "Data_Ref": data_aniv.strftime("%d/%m/%Y"),
            "Data_Pgto": data_pagto.strftime("%d/%m/%Y"),
            "DU_Juros": du,
            "Mes_NIk": mes_nik,
            "Mes_NIk_1": mes_nik_1,
            "NIk": ni_k,
            "NIk_1": ni_k_1,
            "Fonte_NIk": fonte_mes.get(mes_nik, ""),
            "DUP_IPCA": dup_ipca,
            "DUT_IPCA": dut_ipca,
            "Fator_C_IPCA": fator_c,
            "IPCA_Mes_Implicito": fator_c - Decimal("1"),
            "Fator_Juros": fj,
            "Perc_Amort": perc_amort,
            "PU_VNa_Ini": pu_vna_ini,
            "PU_VNa_Atualizado": pu_vna_atualizado,
            "PU_Juros": pu_juros,
            "PU_Amort": pu_amort,
            "PU_Total": trunc_dec(pu_juros + pu_amort, 8),
            "PU_VNa_Fim": pu_vna_fim,
            "Juros_R$": juros_rs,
            "Amort_R$": amort_rs,
            "PMT_Total": pmt_rs,
            "Saldo_Devedor_R$": saldo_rs,
        })

        saldo_pu = pu_vna_fim
        data_ref_juros = data_pagto

    return linhas, fonte


def salvar_csv(linhas: List[Dict[str, object]], caminho: str) -> None:
    if not linhas:
        raise RuntimeError("Nenhuma linha calculada.")
    campos = list(linhas[0].keys())
    with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=campos, delimiter=";")
        w.writeheader()
        for row in linhas:
            out: Dict[str, object] = {}
            for k, v in row.items():
                out[k] = str(v).replace(".", ",") if isinstance(v, Decimal) else v
            w.writerow(out)



def imprimir_linha(data_txt: str, linhas: List[Dict[str, object]]) -> None:
    linha = next((x for x in linhas if x["Data_Pgto"] == data_txt), None)
    if not linha:
        print(f"\nLinha {data_txt}: nao calculada.")
        return
    print(f"\nLinha {data_txt}:")
    campos = [
        "Data_Ref", "Data_Pgto", "DU_Juros", "Mes_NIk", "Mes_NIk_1", "Fator_C_IPCA",
        "Fator_Juros", "PU_VNa_Atualizado", "PU_Juros", "PU_Amort", "Juros_R$",
        "Amort_R$", "PMT_Total", "Saldo_Devedor_R$",
    ]
    for k in campos:
        print(f"{k}: {linha[k]}")


def main() -> None:
    linhas, fonte = calcular_fluxo()
    arquivo_saida = "controle_divida_axs07_v15_focus.csv"
    salvar_csv(linhas, arquivo_saida)

    print("Fonte IPCA oficial/historica:", fonte)
    print(f"Arquivo gerado: {arquivo_saida}")
    imprimir_linha("16/03/2026", linhas)
    imprimir_linha("15/04/2026", linhas)
    imprimir_linha("15/03/2034", linhas)


if __name__ == "__main__":
    main()
