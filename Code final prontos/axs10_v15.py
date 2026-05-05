# -*- coding: utf-8 -*-
"""
AXS Energia Unidade 10 - Debenture AXS411 (Mezanino) - calculo PMT CDI + spread.

Objetivo
- Gerar uma saida de eventos no mesmo estilo do calculo da AXS 07.
- Calcular a debenture AXS 10 pela escritura/aditamento:
  sem atualizacao monetaria, 100% da Taxa DI + spread de 6,50% a.a. base 252,
  juros mensais no dia 15, primeira amortizacao em 15/01/2026 e vencimento em
  15/09/2036.
- Usar CDI historico do BCB/SGS serie 12 como taxa diaria em % a.d. A taxa e
  aplicada ao PU de calculo com defasagem operacional de 2 Dias Uteis, metodologia
  que reproduz o historico de PUs da Vortx existente na pasta.

Como rodar
    python axs10_v6_cdi_fluxo.py

Arquivos gerados
    controle_divida_axs10_v6_cdi_fluxo.csv
    controle_divida_axs10_v6_cdi_fluxo.xlsx

Observacao sobre datas futuras
- Para datas posteriores ao ultimo CDI divulgado pelo BCB, o script carrega a
  ultima Taxa DI disponivel e sinaliza isso na coluna Fonte_CDI. Isso evita
  imputar valores da Vortx como entrada.
"""

from __future__ import annotations

import csv
import json
import ssl
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP, getcontext
from pathlib import Path
from typing import Dict, Iterable, List, Tuple
from urllib.parse import urlencode
from urllib.request import Request, urlopen

getcontext().prec = 34

BASE_DIR = Path(__file__).resolve().parent

DATA_EMISSAO = date(2024, 9, 15)
DATA_INICIO_RENTABILIDADE = date(2024, 9, 30)
DATA_VENCIMENTO = date(2036, 9, 15)
DATA_LIMITE_INCORPORACAO = date(2026, 4, 25)

PERCENTUAL_CDI = Decimal("1.00000000")
SPREAD_AA = Decimal("0.06500000")
BASE_DU = Decimal("252")
QUANTIDADE = Decimal("57000")
PU_INICIAL = Decimal("1000.00000000")
DEFASAGEM_CDI_DU = 2

ARQUIVO_SAIDA = BASE_DIR / "controle_divida_axs10_v6_cdi_fluxo.csv"
ARQUIVO_SAIDA_XLSX = BASE_DIR / "controle_divida_axs10_v6_cdi_fluxo.xlsx"

# Anexo IV do 1o Aditamento a Escritura de Emissao.
# Campos: data, % do saldo do VNU a ser amortizado, paga juros remuneratorios.
CRONOGRAMA_RAW = [
    ("2024-10-15", "0.0000", "SIM"), ("2024-11-15", "0.0000", "SIM"),
    ("2024-12-15", "0.0000", "SIM"), ("2025-01-15", "0.0000", "SIM"),
    ("2025-02-15", "0.0000", "SIM"), ("2025-03-15", "0.0000", "SIM"),
    ("2025-04-15", "0.0000", "SIM"), ("2025-05-15", "0.0000", "SIM"),
    ("2025-06-15", "0.0000", "SIM"), ("2025-07-15", "0.0000", "SIM"),
    ("2025-08-15", "0.0000", "SIM"), ("2025-09-15", "0.0000", "SIM"),
    ("2025-10-15", "0.0000", "SIM"), ("2025-11-15", "0.0000", "SIM"),
    ("2025-12-15", "0.0000", "SIM"), ("2026-01-15", "1.5510", "SIM"),
    ("2026-02-15", "2.6749", "SIM"), ("2026-03-15", "2.7952", "SIM"),
    ("2026-04-15", "2.3156", "SIM"), ("2026-05-15", "3.7122", "SIM"),
    ("2026-06-15", "0.2090", "SIM"), ("2026-07-15", "0.3671", "SIM"),
    ("2026-08-15", "0.9117", "SIM"), ("2026-09-15", "1.3940", "SIM"),
    ("2026-10-15", "1.0744", "SIM"), ("2026-11-15", "1.8862", "SIM"),
    ("2026-12-15", "1.6017", "SIM"), ("2027-01-15", "1.4218", "SIM"),
    ("2027-02-15", "1.3081", "SIM"), ("2027-03-15", "2.0087", "SIM"),
    ("2027-04-15", "1.7702", "SIM"), ("2027-05-15", "1.8723", "SIM"),
    ("2027-06-15", "8.6666", "SIM"), ("2027-07-15", "1.9521", "SIM"),
    ("2027-08-15", "1.9883", "SIM"), ("2027-09-15", "2.1784", "SIM"),
    ("2027-10-15", "2.3273", "SIM"), ("2027-11-15", "2.6724", "SIM"),
    ("2027-12-15", "3.3078", "SIM"), ("2028-01-15", "2.5396", "SIM"),
    ("2028-02-15", "2.5988", "SIM"), ("2028-03-15", "2.8187", "SIM"),
    ("2028-04-15", "2.5305", "SIM"), ("2028-05-15", "2.6909", "SIM"),
    ("2028-06-15", "2.5110", "SIM"), ("2028-07-15", "2.7120", "SIM"),
    ("2028-08-15", "2.7788", "SIM"), ("2028-09-15", "3.0491", "SIM"),
    ("2028-10-15", "2.6392", "SIM"), ("2028-11-15", "3.0616", "SIM"),
    ("2028-12-15", "3.3940", "SIM"), ("2029-01-15", "2.8847", "SIM"),
    ("2029-02-15", "2.9639", "SIM"), ("2029-03-15", "3.2419", "SIM"),
    ("2029-04-15", "2.8997", "SIM"), ("2029-05-15", "3.1064", "SIM"),
    ("2029-06-15", "2.8806", "SIM"), ("2029-07-15", "3.1318", "SIM"),
    ("2029-08-15", "3.2261", "SIM"), ("2029-09-15", "3.5835", "SIM"),
    ("2029-10-15", "2.4980", "SIM"), ("2029-11-15", "2.9917", "SIM"),
    ("2029-12-15", "3.1512", "SIM"), ("2030-01-15", "2.7167", "SIM"),
    ("2030-02-15", "2.7939", "SIM"), ("2030-03-15", "3.1117", "SIM"),
    ("2030-04-15", "2.6474", "SIM"), ("2030-05-15", "2.8134", "SIM"),
    ("2030-06-15", "2.3584", "SIM"), ("2030-07-15", "2.5640", "SIM"),
    ("2030-08-15", "2.6420", "SIM"), ("2030-09-15", "3.0077", "SIM"),
    ("2030-10-15", "2.9989", "SIM"), ("2030-11-15", "3.5991", "SIM"),
    ("2030-12-15", "3.8527", "SIM"), ("2031-01-15", "1.4493", "SIM"),
    ("2031-02-15", "1.4706", "SIM"), ("2031-03-15", "1.4925", "SIM"),
    ("2031-04-15", "1.5152", "SIM"), ("2031-05-15", "1.5385", "SIM"),
    ("2031-06-15", "1.5625", "SIM"), ("2031-07-15", "1.5873", "SIM"),
    ("2031-08-15", "1.6129", "SIM"), ("2031-09-15", "1.6393", "SIM"),
    ("2031-10-15", "1.6667", "SIM"), ("2031-11-15", "1.6949", "SIM"),
    ("2031-12-15", "1.7241", "SIM"), ("2032-01-15", "1.7544", "SIM"),
    ("2032-02-15", "1.7857", "SIM"), ("2032-03-15", "1.8182", "SIM"),
    ("2032-04-15", "1.8519", "SIM"), ("2032-05-15", "1.8868", "SIM"),
    ("2032-06-15", "1.9231", "SIM"), ("2032-07-15", "1.9608", "SIM"),
    ("2032-08-15", "2.0000", "SIM"), ("2032-09-15", "2.0408", "SIM"),
    ("2032-10-15", "2.0833", "SIM"), ("2032-11-15", "2.1277", "SIM"),
    ("2032-12-15", "2.1739", "SIM"), ("2033-01-15", "2.2222", "SIM"),
    ("2033-02-15", "2.2727", "SIM"), ("2033-03-15", "2.3256", "SIM"),
    ("2033-04-15", "2.3810", "SIM"), ("2033-05-15", "2.4390", "SIM"),
    ("2033-06-15", "2.5000", "SIM"), ("2033-07-15", "2.5641", "SIM"),
    ("2033-08-15", "2.6316", "SIM"), ("2033-09-15", "2.7027", "SIM"),
    ("2033-10-15", "2.7778", "SIM"), ("2033-11-15", "2.8571", "SIM"),
    ("2033-12-15", "2.9412", "SIM"), ("2034-01-15", "3.0303", "SIM"),
    ("2034-02-15", "3.1250", "SIM"), ("2034-03-15", "3.2258", "SIM"),
    ("2034-04-15", "3.3333", "SIM"), ("2034-05-15", "3.4483", "SIM"),
    ("2034-06-15", "3.5714", "SIM"), ("2034-07-15", "3.7037", "SIM"),
    ("2034-08-15", "3.8462", "SIM"), ("2034-09-15", "4.0000", "SIM"),
    ("2034-10-15", "4.1667", "SIM"), ("2034-11-15", "4.3478", "SIM"),
    ("2034-12-15", "4.5455", "SIM"), ("2035-01-15", "4.7619", "SIM"),
    ("2035-02-15", "5.0000", "SIM"), ("2035-03-15", "5.2632", "SIM"),
    ("2035-04-15", "5.5556", "SIM"), ("2035-05-15", "5.8824", "SIM"),
    ("2035-06-15", "6.2500", "SIM"), ("2035-07-15", "6.6667", "SIM"),
    ("2035-08-15", "7.1429", "SIM"), ("2035-09-15", "7.6923", "SIM"),
    ("2035-10-15", "8.3333", "SIM"), ("2035-11-15", "9.0909", "SIM"),
    ("2035-12-15", "10.0000", "SIM"), ("2036-01-15", "11.1111", "SIM"),
    ("2036-02-15", "12.5000", "SIM"), ("2036-03-15", "14.2857", "SIM"),
    ("2036-04-15", "16.6667", "SIM"), ("2036-05-15", "20.0000", "SIM"),
    ("2036-06-15", "25.0000", "SIM"), ("2036-07-15", "33.3333", "SIM"),
    ("2036-08-15", "50.0000", "SIM"), ("2036-09-15", "100.0000", "SIM"),
]

CRONOGRAMA = [
    (datetime.strptime(d, "%Y-%m-%d").date(), Decimal(p) / Decimal("100"), j.upper() == "SIM")
    for d, p, j in CRONOGRAMA_RAW
]


def trunc_dec(x: Decimal, casas: int = 8) -> Decimal:
    return x.quantize(Decimal("1").scaleb(-casas), rounding=ROUND_DOWN)


def round_dec(x: Decimal, casas: int = 2) -> Decimal:
    return x.quantize(Decimal("1").scaleb(-casas), rounding=ROUND_HALF_UP)


def data_ptbr(dt: date) -> str:
    return dt.strftime("%d/%m/%Y")


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


def feriados_nacionais(start_year: int = 2024, end_year: int = 2036) -> set[date]:
    fs: set[date] = set()
    for y in range(start_year, end_year + 1):
        pascoa = easter_date(y)
        fs.update({
            date(y, 1, 1),
            pascoa - timedelta(days=48),
            pascoa - timedelta(days=47),
            pascoa - timedelta(days=2),
            date(y, 4, 21),
            date(y, 5, 1),
            pascoa + timedelta(days=60),
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


def proximo_dia_util(dt: date) -> date:
    out = dt
    while not eh_dia_util(out):
        out += timedelta(days=1)
    return out


def dia_util_anterior(dt: date) -> date:
    out = dt - timedelta(days=1)
    while not eh_dia_util(out):
        out -= timedelta(days=1)
    return out


def iter_dias_uteis_periodo(inicio: date, fim: date) -> Iterable[date]:
    """Itera os DUs do calculo em (inicio, fim], padrao observado no PU Vortx."""
    dt = inicio + timedelta(days=1)
    while dt <= fim:
        if eh_dia_util(dt):
            yield dt
        dt += timedelta(days=1)


def obter_json_url(url: str, timeout: int = 45) -> object:
    ctx = ssl.create_default_context()
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=timeout, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8"))


def obter_cdi_sgs12(data_inicial: date, data_final: date) -> Tuple[Dict[date, Decimal], str]:
    params = {
        "formato": "json",
        "dataInicial": data_inicial.strftime("%d/%m/%Y"),
        "dataFinal": data_final.strftime("%d/%m/%Y"),
    }
    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados?{urlencode(params)}"
    dados = obter_json_url(url)
    if not isinstance(dados, list):
        raise RuntimeError(f"BCB/SGS retornou layout inesperado: {type(dados).__name__}")

    out: Dict[date, Decimal] = {}
    for item in dados:
        if not isinstance(item, dict):
            continue
        if "data" not in item or "valor" not in item:
            continue
        dt = datetime.strptime(str(item["data"]), "%d/%m/%Y").date()
        out[dt] = Decimal(str(item["valor"]).replace(",", ".")) / Decimal("100")

    if not out:
        raise RuntimeError("BCB/SGS 12 retornou vazio.")

    return out, f"BCB SGS 12 | {url}"


def taxa_cdi_para_data_calculo(data_calculo: date, cdi: Dict[date, Decimal]) -> Tuple[date, Decimal, str]:
    ref = data_calculo
    for _ in range(DEFASAGEM_CDI_DU):
        ref = dia_util_anterior(ref)
    if ref in cdi:
        return ref, cdi[ref], f"BCB/SGS12 diario com defasagem de {DEFASAGEM_CDI_DU} DUs"

    datas_anteriores = [dt for dt in cdi if dt <= ref]
    if datas_anteriores:
        ultima = max(datas_anteriores)
        return ultima, cdi[ultima], "ultima Taxa DI disponivel carregada"

    raise RuntimeError(f"CDI SGS 12 nao encontrado ate {data_ptbr(ref)}.")


def fator_di_periodo(inicio: date, fim: date, cdi: Dict[date, Decimal]) -> Tuple[Decimal, int, str, date | None, date | None]:
    acc = Decimal("1.0000000000000000")
    du = 0
    fontes: set[str] = set()
    primeira_ref: date | None = None
    ultima_ref: date | None = None

    for data_calc in iter_dias_uteis_periodo(inicio, fim):
        ref_cdi, taxa_dia, fonte = taxa_cdi_para_data_calculo(data_calc, cdi)
        tdik = round_dec(Decimal("1") + (taxa_dia * PERCENTUAL_CDI), 8)
        acc = trunc_dec(acc * tdik, 16)
        du += 1
        fontes.add(fonte)
        primeira_ref = ref_cdi if primeira_ref is None else min(primeira_ref, ref_cdi)
        ultima_ref = ref_cdi if ultima_ref is None else max(ultima_ref, ref_cdi)

    return round_dec(acc, 8), du, " + ".join(sorted(fontes)), primeira_ref, ultima_ref


def fator_spread_periodo(du: int) -> Decimal:
    bruto = (Decimal("1") + SPREAD_AA) ** (Decimal(du) / BASE_DU)
    return round_dec(bruto, 9)


def caminho_alternativo(caminho: str | Path) -> Path:
    path = Path(caminho)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return path.with_name(f"{path.stem}_{timestamp}{path.suffix}")


def salvar_com_fallback(funcao_salvar, linhas: List[Dict[str, object]], caminho: str | Path) -> Tuple[Path, bool]:
    path = Path(caminho)
    try:
        funcao_salvar(linhas, path)
        return path, False
    except PermissionError:
        alternativa = caminho_alternativo(path)
        funcao_salvar(linhas, alternativa)
        return alternativa, True


def houve_incorporacao_ate(data_pagto: date) -> bool:
    return data_pagto <= DATA_LIMITE_INCORPORACAO


def calcular_fluxo() -> Tuple[List[Dict[str, object]], str]:
    data_fim_cdi = max(date.today(), DATA_INICIO_RENTABILIDADE)
    cdi, fonte_base = obter_cdi_sgs12(DATA_INICIO_RENTABILIDADE - timedelta(days=10), data_fim_cdi)

    saldo_pu = trunc_dec(PU_INICIAL, 8)
    data_ref_juros = DATA_INICIO_RENTABILIDADE
    linhas: List[Dict[str, object]] = []

    for idx, (data_ref, perc_amort, paga_juros) in enumerate(CRONOGRAMA, start=1):
        data_pagto = proximo_dia_util(data_ref)
        pu_vna_ini = trunc_dec(saldo_pu, 8)
        incorpora_periodo = houve_incorporacao_ate(data_pagto)

        fator_di, du, fonte_cdi, primeira_ref, ultima_ref = fator_di_periodo(data_ref_juros, data_pagto, cdi)
        fator_spread = fator_spread_periodo(du)
        fator_juros = round_dec(fator_di * fator_spread, 9)

        pu_juros = trunc_dec(pu_vna_ini * (fator_juros - Decimal("1")), 8)
        paga_juros_efetivo = paga_juros and not incorpora_periodo
        pu_juros_pago = pu_juros if paga_juros_efetivo else Decimal("0.00000000")
        pu_juros_capitalizado = pu_juros if incorpora_periodo or not paga_juros else Decimal("0.00000000")
        pu_vna_atualizado = trunc_dec(pu_vna_ini + pu_juros_capitalizado, 8)

        pu_amort = Decimal("0.00000000") if incorpora_periodo else trunc_dec(pu_vna_atualizado * perc_amort, 8)
        if idx == len(CRONOGRAMA) and not incorpora_periodo:
            pu_amort = pu_vna_atualizado
        pu_vna_fim = trunc_dec(pu_vna_atualizado - pu_amort, 8)

        juros_rs = round_dec(pu_juros_pago * QUANTIDADE, 2)
        amort_rs = round_dec(pu_amort * QUANTIDADE, 2)
        pmt_rs = round_dec(juros_rs + amort_rs, 2)
        saldo_rs = round_dec(pu_vna_fim * QUANTIDADE, 2)

        linhas.append({
            "Data_Ref": data_ref.strftime("%d/%m/%Y"),
            "Data_Pgto": data_pagto.strftime("%d/%m/%Y"),
            "DU_Juros": du,
            "Data_Inicio_Periodo": data_ref_juros.strftime("%d/%m/%Y"),
            "Primeira_Data_Ref_CDI": primeira_ref.strftime("%d/%m/%Y") if primeira_ref else "",
            "Ultima_Data_Ref_CDI": ultima_ref.strftime("%d/%m/%Y") if ultima_ref else "",
            "Percentual_CDI": PERCENTUAL_CDI,
            "Spread_aa": SPREAD_AA,
            "Fator_DI": fator_di,
            "Fator_Spread": fator_spread,
            "Fator_Juros": fator_juros,
            "Paga_Juros_Contrato": "SIM" if paga_juros else "NAO",
            "Incorpora_Ate_Data": "SIM" if incorpora_periodo else "NAO",
            "Perc_Amort": perc_amort,
            "PU_VNa_Ini": pu_vna_ini,
            "PU_VNa_Atualizado": pu_vna_atualizado,
            "PU_Juros": pu_juros,
            "PU_Juros_Pago": pu_juros_pago,
            "PU_Juros_Capitalizado": pu_juros_capitalizado,
            "PU_Amort": pu_amort,
            "PU_Total": trunc_dec(pu_juros_pago + pu_amort, 8),
            "PU_VNa_Fim": pu_vna_fim,
            "Juros_R$": juros_rs,
            "Juros_Capitalizado_R$": round_dec(pu_juros_capitalizado * QUANTIDADE, 2),
            "Amort_R$": amort_rs,
            "PMT_Total": pmt_rs,
            "Saldo_Devedor_R$": saldo_rs,
            "Fonte_CDI": f"{fonte_base} | {fonte_cdi}",
        })

        saldo_pu = pu_vna_fim
        data_ref_juros = data_pagto

    return linhas, fonte_base


def salvar_csv(linhas: List[Dict[str, object]], caminho: str | Path) -> None:
    if not linhas:
        raise RuntimeError("Nenhuma linha calculada.")
    campos = list(linhas[0].keys())
    path = Path(caminho)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=campos, delimiter=";")
        w.writeheader()
        for row in linhas:
            out: Dict[str, object] = {}
            for k, v in row.items():
                out[k] = format(v, "f").replace(".", ",") if isinstance(v, Decimal) else v
            w.writerow(out)


def salvar_xlsx(linhas: List[Dict[str, object]], caminho: str | Path) -> None:
    import pandas as pd
    if not linhas:
        raise RuntimeError("Nenhuma linha calculada.")
    path = Path(caminho)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    linhas_export = []
    for row in linhas:
        out: Dict[str, object] = {}
        for k, v in row.items():
            if isinstance(v, Decimal):
                out[k] = float(v)
            else:
                out[k] = v
        linhas_export.append(out)
    
    df = pd.DataFrame(linhas_export)
    df.to_excel(path, index=False)


def imprimir_linha(data_txt: str, linhas: List[Dict[str, object]]) -> None:
    linha = next((x for x in linhas if x["Data_Pgto"] == data_txt), None)
    if not linha:
        print(f"\nLinha {data_txt}: nao calculada.")
        return
    print(f"\nLinha {data_txt}:")
    campos = [
        "Data_Ref", "Data_Pgto", "DU_Juros", "Data_Inicio_Periodo", "Fator_DI",
        "Fator_Spread", "Fator_Juros", "PU_VNa_Ini", "PU_Juros", "PU_Amort",
        "Juros_R$", "Amort_R$", "PMT_Total", "Saldo_Devedor_R$",
    ]
    for k in campos:
        valor = linha[k]
        if isinstance(valor, Decimal):
            valor = format(valor, "f")
        print(f"{k}: {valor}")


def main() -> None:
    linhas, fonte = calcular_fluxo()
    csv_gerado, csv_fallback = salvar_com_fallback(salvar_csv, linhas, ARQUIVO_SAIDA)
    xlsx_gerado, xlsx_fallback = salvar_com_fallback(salvar_xlsx, linhas, ARQUIVO_SAIDA_XLSX)

    print("Fonte CDI historica:", fonte)
    if csv_fallback:
        print(f"CSV padrao estava aberto/bloqueado. Arquivo alternativo gerado: {csv_gerado}")
    else:
        print(f"CSV gerado: {csv_gerado}")
    if xlsx_fallback:
        print(f"XLSX padrao estava aberto/bloqueado. Arquivo alternativo gerado: {xlsx_gerado}")
    else:
        print(f"XLSX gerado: {xlsx_gerado}")
    imprimir_linha("15/10/2024", linhas)
    imprimir_linha("15/04/2026", linhas)
    imprimir_linha("15/09/2036", linhas)


if __name__ == "__main__":
    main()
