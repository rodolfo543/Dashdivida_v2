from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse


DASH_DIR = Path(__file__).resolve().parent
PROJECT_DIR = DASH_DIR
PORTFOLIO_ID = "geral"
AXS02_DEFAULT_VARIANT = "total"


@dataclass(frozen=True)
class OperationConfig:
    id: str
    label: str
    full_name: str
    badge: str
    category: str
    indexer: str
    description: str
    issuer: str
    script_path: Path
    loader: Callable[[Any], dict[str, Any]]
    code_if: str = ""
    isin: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


def load_module(module_name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Nao foi possivel carregar o modulo: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def decimal_to_float(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, dict):
        return {key: decimal_to_float(item) for key, item in value.items()}
    if isinstance(value, list):
        return [decimal_to_float(item) for item in value]
    return value


def number_or_none(value: Any) -> float | None:
    if value in ("", None):
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def text_or_default(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, (date, datetime)):
        return value.strftime("%d/%m/%Y")
    return str(value)


def parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for pattern in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


def first_number(*values: Any) -> float | None:
    for value in values:
        number = number_or_none(value)
        if number is not None:
            return number
    return None


def slug_component(value: Any) -> str:
    text = text_or_default(value).strip().upper()
    if "DEB" in text:
        return "deb"
    if "CRI" in text:
        return "cri"
    return ""


def pretty_component(value: str) -> str:
    return {"cri": "CRI", "deb": "Debenture", "total": "Total"}.get(value, value or "-")


def normalize_base_row(row: dict[str, Any]) -> dict[str, Any]:
    component = slug_component(row.get("Instrumento"))
    payment = first_number(
        row.get("PMT_Total"),
        row.get("Total"),
        row.get("PU_Total"),
        row.get("PU_Total_Pago"),
    ) or 0.0
    interest = first_number(row.get("Juros_R$"), row.get("Valor_dos_Juros")) or 0.0
    amortization = first_number(row.get("Amort_R$"), row.get("Amortizacao")) or 0.0
    balance = first_number(row.get("Saldo_Devedor_R$"), row.get("Valor_Nominal"))
    principal = first_number(
        row.get("VNa_Atualizado_R$"),
        (balance + amortization) if balance is not None else None,
        balance,
    )
    pu_vazio = first_number(row.get("PU_Vazio"), row.get("PU_VNa_Atualizado"), row.get("PU_VNa_Fim"), row.get("Valor_Nominal"))
    pu_juros = first_number(row.get("PU_Juros"), row.get("Valor_dos_Juros")) or 0.0
    pu_amort = first_number(row.get("PU_Amort"), row.get("Amortizacao")) or 0.0
    pu_total = first_number(row.get("PU_Total"), row.get("PU_Total_Pago"), row.get("Total"))
    pu_cheio = first_number(row.get("PU_Cheio"), (pu_vazio + pu_juros) if pu_vazio is not None else None)
    parsed_date = parse_date(row.get("Data_Pgto") or row.get("Data") or row.get("Data_Ref"))

    return {
        "date": text_or_default(row.get("Data_Pgto") or row.get("Data") or row.get("Data_Ref"), "-"),
        "label": text_or_default(row.get("Evento") or row.get("Tipo") or row.get("Instrumento"), "Fluxo"),
        "component": component,
        "component_label": pretty_component(component),
        "payment": payment,
        "interest": interest,
        "amortization": amortization,
        "balance": balance or 0.0,
        "principal": principal or 0.0,
        "pu_cheio": pu_cheio,
        "pu_vazio": pu_vazio,
        "pu_juros": pu_juros,
        "pu_amort": pu_amort,
        "pu_total": pu_total,
        "parsed_date": parsed_date,
        "sort_key": text_or_default(row.get("Codigo_IF") or row.get("ISIN") or row.get("Instrumento") or ""),
        "raw": decimal_to_float(row),
    }


def finalize_series(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items.sort(key=lambda item: (item["parsed_date"] or date.max, item["date"], item.get("sort_key", ""), item["label"]))
    total_interest = 0.0
    total_amortization = 0.0
    finalized: list[dict[str, Any]] = []
    for item in items:
        total_interest += item["interest"]
        total_amortization += item["amortization"]
        final_item = dict(item)
        final_item["total_interest_running"] = total_interest
        final_item["total_amortization_running"] = total_amortization
        finalized.append(final_item)
    return finalized


def normalize_series(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return finalize_series([normalize_base_row(row) for row in rows])


def get_current_row(series: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not series:
        return None
    today = datetime.now().date()
    past = [item for item in series if item["parsed_date"] and item["parsed_date"] <= today]
    if past:
        return past[-1]
    future = [item for item in series if item["parsed_date"]]
    if future:
        return future[0]
    return series[-1]


def build_summary(series: list[dict[str, Any]]) -> dict[str, Any]:
    current_row = get_current_row(series)
    next_item = None
    today = datetime.now().date()
    for item in series:
        if item["parsed_date"] and item["parsed_date"] >= today:
            next_item = item
            break
    return {
        "current_balance": current_row["balance"] if current_row else None,
        "current_principal": current_row["principal"] if current_row else None,
        "current_pu_cheio": current_row["pu_cheio"] if current_row else None,
        "current_pu_vazio": current_row["pu_vazio"] if current_row else None,
        "current_pu_juros": current_row["pu_juros"] if current_row else None,
        "current_pu_amort": current_row["pu_amort"] if current_row else None,
        "current_payment": current_row["payment"] if current_row else None,
        "total_interest": sum(item["interest"] for item in series),
        "total_amortization": sum(item["amortization"] for item in series),
        "event_count": len(series),
        "next_payment_date": next_item["date"] if next_item else None,
        "next_payment_amount": next_item["payment"] if next_item else None,
        "last_event_date": current_row["date"] if current_row else None,
        "final_balance": series[-1]["balance"] if series else None,
    }


def build_timeline(series: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
    today = datetime.now().date()
    upcoming: list[dict[str, Any]] = []
    for item in series:
        if item["parsed_date"] and item["parsed_date"] >= today:
            upcoming.append(item)
        if len(upcoming) == limit:
            break
    return upcoming or series[:limit]


def derive_quantity(module: Any) -> float | None:
    if hasattr(module, "QUANTIDADE"):
        return number_or_none(getattr(module, "QUANTIDADE"))
    if hasattr(module, "QUANTIDADE_EQUIVALENTE"):
        return number_or_none(getattr(module, "QUANTIDADE_EQUIVALENTE"))
    if hasattr(module, "INSTRUMENTOS"):
        total = 0.0
        for instrument in getattr(module, "INSTRUMENTOS"):
            total += number_or_none(getattr(instrument, "quantidade", None)) or 0.0
        return total or None
    return None


def derive_volume(module: Any) -> float | None:
    if hasattr(module, "VALOR_TOTAL_INICIAL"):
        return number_or_none(getattr(module, "VALOR_TOTAL_INICIAL"))
    quantity = derive_quantity(module)
    pu = number_or_none(getattr(module, "PU_INICIAL", None))
    if quantity is not None and pu is not None:
        return quantity * pu
    return None


def metadata_value(config: OperationConfig, key: str, fallback: Any = None) -> Any:
    return config.metadata.get(key, fallback)


def build_fields(config: OperationConfig, payload: dict[str, Any], module: Any | None) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    summary = payload["summary"]
    identity_fields = [
        {"label": "Codigo IF", "value": config.code_if or metadata_value(config, "code_if", "-")},
        {"label": "Codigo ISIN", "value": config.isin or metadata_value(config, "isin", "-")},
        {"label": "Emissor", "value": metadata_value(config, "issuer", config.issuer)},
    ]

    issue_date = metadata_value(config, "issue_date", text_or_default(getattr(module, "DATA_EMISSAO", None), "-"))
    start_date = metadata_value(config, "start_date", text_or_default(getattr(module, "DATA_INICIO_RENTABILIDADE", None), "-"))
    maturity_date = metadata_value(config, "maturity_date", text_or_default(getattr(module, "DATA_VENCIMENTO", None), "-"))
    quantity = metadata_value(config, "quantity_emitted", derive_quantity(module) if module else None)
    volume = metadata_value(config, "volume_emitted", derive_volume(module) if module else None)
    pu_issue = metadata_value(config, "pu_issue", number_or_none(getattr(module, "PU_INICIAL", None)) if module and hasattr(module, "PU_INICIAL") else None)

    overview_fields = [
        {"label": "Remuneracao", "value": metadata_value(config, "remuneration_label", config.indexer)},
        {"label": "Volume emitido", "value": str(volume) if volume is not None else "-"},
        {"label": "Quantidade emitida", "value": str(quantity) if quantity is not None else "-"},
        {"label": "PU de emissao", "value": str(pu_issue) if pu_issue is not None else "-"},
        {"label": "Data de emissao", "value": issue_date},
        {"label": "Inicio da rentabilidade", "value": start_date},
        {"label": "Data de vencimento", "value": maturity_date},
        {"label": "Pagamento de juros", "value": metadata_value(config, "payment_frequency", "-")},
        {"label": "Amortizacao", "value": metadata_value(config, "amortization_frequency", "-")},
        {"label": "Distribuicao", "value": metadata_value(config, "distribution", "-")},
        {"label": "Tipo de risco", "value": metadata_value(config, "risk_type", "-")},
        {"label": "Garantias", "value": metadata_value(config, "guarantees", "-")},
        {"label": "Saldo atual", "value": str(summary["current_balance"]) if summary["current_balance"] is not None else "-"},
        {"label": "Proximo PMT", "value": str(summary["next_payment_amount"]) if summary["next_payment_amount"] is not None else "-"},
    ]

    pu_fields = [
        {"label": "PU cheio", "value": str(summary["current_pu_cheio"]) if summary["current_pu_cheio"] is not None else "-"},
        {"label": "PU vazio", "value": str(summary["current_pu_vazio"]) if summary["current_pu_vazio"] is not None else "-"},
        {"label": "PU juros", "value": str(summary["current_pu_juros"]) if summary["current_pu_juros"] is not None else "-"},
        {"label": "PU amortizacao", "value": str(summary["current_pu_amort"]) if summary["current_pu_amort"] is not None else "-"},
        {"label": "Principal atualizado", "value": str(summary["current_principal"]) if summary["current_principal"] is not None else "-"},
        {"label": "PMT da linha atual", "value": str(summary["current_payment"]) if summary["current_payment"] is not None else "-"},
    ]
    return identity_fields, overview_fields, pu_fields


def build_operation_view(config: OperationConfig, payload: dict[str, Any], module: Any | None) -> dict[str, Any]:
    identity_fields, overview_fields, pu_fields = build_fields(config, payload, module)
    operation = {
        "id": config.id,
        "label": config.label,
        "full_name": config.full_name,
        "badge": config.badge,
        "category": config.category,
        "indexer": config.indexer,
        "description": config.description,
        "issuer": metadata_value(config, "issuer", config.issuer),
        "script_path": str(config.script_path),
        "identity_fields": identity_fields,
        "overview_fields": overview_fields,
        "pu_fields": pu_fields,
    }
    return {
        "operation": operation,
        "series": payload["series"],
        "table_series": payload.get("table_series", payload["series"]),
        "summary": payload["summary"],
        "timeline": payload["timeline"],
        "meta": payload["meta"],
    }


def load_axs_standard(module: Any, primary_source_label: str, secondary_source_label: str | None = None) -> dict[str, Any]:
    if not hasattr(module, "calcular_fluxo"):
        raise RuntimeError("Modulo sem calcular_fluxo().")
    result = module.calcular_fluxo()
    if len(result) == 2:
        rows, primary_source = result
        meta = {"primary_source": f"{primary_source_label}: {primary_source}"}
    elif len(result) == 3:
        rows, primary_source, secondary_source = result
        meta = {
            "primary_source": f"{primary_source_label}: {primary_source}",
            "secondary_source": f"{secondary_source_label or 'Fonte complementar'}: {secondary_source}",
        }
    else:
        raise RuntimeError("Retorno inesperado do calculo.")

    series = normalize_series(rows)
    return {
        "module_ref": module,
        "series": series,
        "table_series": series,
        "summary": build_summary(series),
        "timeline": build_timeline(series),
        "meta": meta,
    }


def load_axs_internal_formula(module: Any, primary_source_label: str) -> dict[str, Any]:
    required = ("obter_ipca_numero_indice_sidra", "preencher_indices_futuros", "calcular_fluxo")
    for attr in required:
        if not hasattr(module, attr):
            raise RuntimeError(f"Modulo sem {attr}().")

    indices, primary_source = module.obter_ipca_numero_indice_sidra()
    indices, fonte_mes = module.preencher_indices_futuros(indices)
    rows = module.calcular_fluxo(indices, fonte_mes)
    series = normalize_series(rows)
    return {
        "module_ref": module,
        "series": series,
        "table_series": series,
        "summary": build_summary(series),
        "timeline": build_timeline(series),
        "meta": {
            "primary_source": f"{primary_source_label}: {primary_source}",
            "secondary_source": "Projecoes futuras preenchidas pelo proprio modulo com Focus/BCB ou fallback local.",
        },
    }


def aggregate_variant_series(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered_rows = sorted(rows, key=lambda item: (item["parsed_date"] or date.max, item["component"], item["label"]))
    balances: dict[str, float] = {}
    principals: dict[str, float] = {}
    grouped: list[dict[str, Any]] = []
    current_date: date | None = None
    bucket: list[dict[str, Any]] = []

    def flush_bucket() -> None:
        nonlocal bucket
        if not bucket or current_date is None:
            return
        for item in bucket:
            if item["component"]:
                balances[item["component"]] = item["balance"]
                principals[item["component"]] = item["principal"]
        grouped.append({
            "date": current_date.strftime("%d/%m/%Y"),
            "label": "Total CRI + Debenture",
            "component": "total",
            "component_label": "Total",
            "payment": sum(item["payment"] for item in bucket),
            "interest": sum(item["interest"] for item in bucket),
            "amortization": sum(item["amortization"] for item in bucket),
            "balance": sum(balances.values()),
            "principal": sum(principals.values()),
            "pu_cheio": sum((item["pu_cheio"] or 0.0) for item in bucket) or None,
            "pu_vazio": sum((item["pu_vazio"] or 0.0) for item in bucket) or None,
            "pu_juros": sum((item["pu_juros"] or 0.0) for item in bucket) or None,
            "pu_amort": sum((item["pu_amort"] or 0.0) for item in bucket) or None,
            "pu_total": sum((item["pu_total"] or 0.0) for item in bucket) or None,
            "parsed_date": current_date,
            "sort_key": "0-total",
            "raw": {"component_count": len(bucket)},
        })
        bucket = []

    for row in ordered_rows:
        row_date = row["parsed_date"]
        if current_date is None:
            current_date = row_date
        if row_date != current_date:
            flush_bucket()
            current_date = row_date
        bucket.append(row)
    flush_bucket()
    return finalize_series(grouped)


def make_variant_payload(series: list[dict[str, Any]], table_series: list[dict[str, Any]], operation_overrides: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "series": series,
        "table_series": table_series,
        "summary": build_summary(series),
        "timeline": build_timeline(series),
        "operation_overrides": operation_overrides,
        "meta": meta,
    }


def load_axs02(module: Any) -> dict[str, Any]:
    menor_mes_ipca = "202210"
    maior_mes_ipca = max(module.meses_ipca(module.DATA_VENCIMENTO, inst.lag_ipca_meses)[0] for inst in module.INSTRUMENTOS)
    indices_ipca, fontes_ipca, fonte_ipca = module.preparar_indices_ipca(menor_mes_ipca, maior_mes_ipca)
    eventos: list[dict[str, Any]] = []
    for instrumento in module.INSTRUMENTOS:
        eventos_inst, _ = module.calcular_instrumento(instrumento, indices_ipca, fontes_ipca)
        eventos.extend(eventos_inst)

    detailed_rows = normalize_series(eventos)
    cri_rows = [row for row in detailed_rows if row["component"] == "cri"]
    deb_rows = [row for row in detailed_rows if row["component"] == "deb"]
    total_rows = aggregate_variant_series(detailed_rows)
    base_meta = {
        "primary_source": f"Fonte IPCA: {fonte_ipca}",
        "notes": "AXS 02 permite visualizar total consolidado, CRI isolado ou Debenture isolada.",
    }

    return {
        "module_ref": module,
        "series": total_rows,
        "table_series": detailed_rows,
        "summary": build_summary(total_rows),
        "timeline": build_timeline(total_rows),
        "meta": base_meta,
        "variant_options": [
            {"id": "total", "label": "Total"},
            {"id": "cri", "label": "CRI"},
            {"id": "deb", "label": "Debenture"},
        ],
        "variants": {
            "total": make_variant_payload(
                total_rows,
                detailed_rows,
                {
                    "full_name": "AXS 02 - Consolidado CRI + Debenture",
                    "badge": "Portfolio",
                    "description": "Visao somada dos fluxos do CRI e da Debenture da AXS 02.",
                    "issuer": "OPEA SECURITIZADORA S.A. / AXS ENERGIA UNIDADE 02 S.A.",
                    "metadata": {
                        "issue_date": "23/12/2022",
                        "maturity_date": "15/12/2036",
                        "quantity_emitted": "85000",
                        "volume_emitted": "85000000",
                        "pu_issue": "1000",
                        "payment_frequency": "Mensal",
                        "amortization_frequency": "Mensal",
                        "distribution": "CRI ICVM 476 / Debenture ICVM 476",
                        "risk_type": "Estrutura mista",
                        "guarantees": "Consolidado do CRI e da Debenture da AXS 02.",
                        "remuneration_label": "IPCA + 11%",
                        "code_if": "22L1467623 / AXSD11",
                        "isin": "BRRBRACRIG06 / BRAXSDDBS005",
                    },
                },
                base_meta,
            ),
            "cri": make_variant_payload(
                cri_rows,
                cri_rows,
                {
                    "full_name": "AXS II - Emissao 46 / Serie UNICA",
                    "badge": "CRI",
                    "description": "Visualizacao isolada do CRI da operacao AXS 02.",
                    "issuer": "OPEA SECURITIZADORA S.A.",
                    "metadata": {
                        "issue_date": "23/12/2022",
                        "maturity_date": "15/12/2036",
                        "quantity_emitted": "45000",
                        "volume_emitted": "45000000",
                        "pu_issue": "1000",
                        "payment_frequency": "Mensal",
                        "amortization_frequency": "Mensal",
                        "distribution": "ICVM 476",
                        "risk_type": "Pulverizado",
                        "guarantees": "Alienacao Fiduciaria de Acoes, Alienacao Fiduciaria de Maquinas, Alienacao Fiduciaria de Outros, Cessao Fiduciaria de Direitos Creditorios, Fianca",
                        "remuneration_label": "IPCA + 11%",
                        "code_if": "22L1467623",
                        "isin": "BRRBRACRIG06",
                    },
                },
                base_meta,
            ),
            "deb": make_variant_payload(
                deb_rows,
                deb_rows,
                {
                    "full_name": "AXS 02 - Emissao 1 / Serie UNICA",
                    "badge": "DEB",
                    "description": "Visualizacao isolada da Debenture da operacao AXS 02.",
                    "issuer": "AXS ENERGIA UNIDADE 02 S.A.",
                    "metadata": {
                        "issue_date": "23/12/2022",
                        "maturity_date": "15/12/2036",
                        "quantity_emitted": "40000",
                        "volume_emitted": "40000000",
                        "pu_issue": "1000",
                        "payment_frequency": "Mensal",
                        "amortization_frequency": "Mensal",
                        "distribution": "ICVM 476",
                        "risk_type": "-",
                        "guarantees": "Sem Garantias",
                        "remuneration_label": "IPCA + 11%",
                        "code_if": "AXSD11",
                        "isin": "BRAXSDDBS005",
                    },
                },
                base_meta,
            ),
        },
    }


def build_comparison_rows(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for payload in payloads:
        rows.append({
            "id": payload["operation"]["id"],
            "label": payload["operation"]["label"],
            "full_name": payload["operation"]["full_name"],
            "current_balance": payload["summary"]["current_balance"] or 0.0,
            "next_payment_amount": payload["summary"]["next_payment_amount"] or 0.0,
            "total_interest": payload["summary"]["total_interest"] or 0.0,
            "total_amortization": payload["summary"]["total_amortization"] or 0.0,
            "event_count": payload["summary"]["event_count"] or 0,
            "indexer": payload["operation"]["indexer"],
            "badge": payload["operation"]["badge"],
        })
    rows.sort(key=lambda item: item["current_balance"], reverse=True)
    return rows


def build_portfolio_series(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    all_dates = sorted({
        item["parsed_date"]
        for payload in payloads
        for item in payload["series"]
        if item["parsed_date"] is not None
    })
    pointers = {payload["operation"]["id"]: 0 for payload in payloads}
    balances = {payload["operation"]["id"]: 0.0 for payload in payloads}
    series_by_operation = {payload["operation"]["id"]: payload["series"] for payload in payloads}
    consolidated: list[dict[str, Any]] = []

    for current_date in all_dates:
        payment = 0.0
        interest = 0.0
        amortization = 0.0
        principal = 0.0
        pu_cheio = 0.0
        pu_vazio = 0.0
        for payload in payloads:
            op_id = payload["operation"]["id"]
            series = series_by_operation[op_id]
            while pointers[op_id] < len(series):
                item = series[pointers[op_id]]
                if item["parsed_date"] is None or item["parsed_date"] > current_date:
                    break
                balances[op_id] = item["balance"] or balances[op_id]
                if item["parsed_date"] == current_date:
                    payment += item["payment"]
                    interest += item["interest"]
                    amortization += item["amortization"]
                    principal += item["principal"]
                    pu_cheio += item["pu_cheio"] or 0.0
                    pu_vazio += item["pu_vazio"] or 0.0
                pointers[op_id] += 1
        consolidated.append({
            "date": current_date.strftime("%d/%m/%Y"),
            "label": "Carteira consolidada",
            "component": "total",
            "component_label": "Total",
            "payment": payment,
            "interest": interest,
            "amortization": amortization,
            "balance": sum(balances.values()),
            "principal": principal,
            "pu_cheio": pu_cheio or None,
            "pu_vazio": pu_vazio or None,
            "pu_juros": None,
            "pu_amort": None,
            "pu_total": None,
            "parsed_date": current_date,
            "sort_key": "0-total",
            "raw": {},
        })
    return finalize_series(consolidated)


def comparison_payload(operation_id: str) -> dict[str, Any]:
    payload = deepcopy(compute_operation(operation_id))
    return apply_variant(payload, AXS02_DEFAULT_VARIANT)


OPERATIONS: dict[str, OperationConfig] = {
    "axs02": OperationConfig(
        id="axs02",
        label="AXS 02",
        full_name="AXS 02 - Consolidado CRI + Debenture",
        badge="Portfolio",
        category="CRI + Debenture",
        indexer="IPCA + 11%",
        description="Visao consolidada dos eventos da operacao AXS 02.",
        issuer="OPEA SECURITIZADORA S.A. / AXS ENERGIA UNIDADE 02 S.A.",
        script_path=PROJECT_DIR / "Code final prontos" / "axs02_v1.py",
        loader=load_axs02,
        metadata={
            "issue_date": "23/12/2022",
            "maturity_date": "15/12/2036",
            "quantity_emitted": "85000",
            "volume_emitted": "85000000",
            "pu_issue": "1000",
            "payment_frequency": "Mensal",
            "amortization_frequency": "Mensal",
            "distribution": "CRI ICVM 476 / Debenture ICVM 476",
            "risk_type": "Estrutura mista",
            "guarantees": "Consolidado do CRI e da Debenture da AXS 02.",
            "remuneration_label": "IPCA + 11%",
            "code_if": "22L1467623 / AXSD11",
            "isin": "BRRBRACRIG06 / BRAXSDDBS005",
        },
    ),
    "axs03": OperationConfig(
        id="axs03",
        label="AXS 03",
        full_name="AXS III - Emissao 78 / Serie UNICA",
        badge="CRI",
        category="CRI",
        indexer="IPCA + 11%",
        description="Fluxo em valor total do CRI AXS 03 com projecao Focus/BCB.",
        issuer="OPEA SECURITIZADORA S.A.",
        code_if="22K1397969",
        isin="BRRBRACRIFA9",
        script_path=PROJECT_DIR / "Code final prontos" / "axs03_cri_v4.py",
        loader=lambda module: load_axs_standard(module, "Fonte IPCA", "Fonte Focus"),
        metadata={
            "payment_frequency": "Mensal",
            "amortization_frequency": "Mensal",
            "distribution": "Res CVM 160",
            "risk_type": "Pulverizado",
            "remuneration_label": "IPCA + 11%",
        },
    ),
    "axs04": OperationConfig(
        id="axs04",
        label="AXS 04",
        full_name="AXS 4 - Emissao 139 / Serie UNICA",
        badge="CRI",
        category="CRI",
        indexer="IPCA + 11%",
        description="Fluxo em valor total do CRI AXS 04 com visao executiva.",
        issuer="OPEA SECURITIZADORA S.A.",
        code_if="23F0046476",
        isin="BRRBRACRIHB3",
        script_path=PROJECT_DIR / "Code final prontos" / "axs04_v2.py",
        loader=lambda module: load_axs_standard(module, "Fonte IPCA", "Fonte Focus"),
        metadata={
            "issue_date": "15/06/2023",
            "maturity_date": "15/07/2037",
            "quantity_emitted": "144000",
            "volume_emitted": "144000000",
            "pu_issue": "1000",
            "payment_frequency": "Mensal",
            "amortization_frequency": "Mensal",
            "distribution": "Res CVM 160",
            "risk_type": "Pulverizado",
            "guarantees": "Alienacao Fiduciaria de Quotas, Alienacao Fiduciaria de Maquinas, Alienacao Fiduciaria de Outros, Cessao Fiduciaria de Direitos Creditorios, Fianca",
            "remuneration_label": "IPCA + 11%",
        },
    ),
    "axs05": OperationConfig(
        id="axs05",
        label="AXS 05",
        full_name="AXS 05 - 2a Emissao / 2 Series",
        badge="DEB",
        category="Debenture",
        indexer="IPCA + 9,47% / 10,97%",
        description="Consolidado das duas series da AXS 05, com fluxo agregado da emissao.",
        issuer="AXS ENERGIA UNIDADE 05 S.A.",
        code_if="AXSC12 / AXSC22",
        isin="BRAXSCDBS015 / BRAXSCDBS023",
        script_path=PROJECT_DIR / "Code final prontos" / "axs05_v1.py",
        loader=lambda module: load_axs_standard(module, "Fonte IPCA"),
        metadata={
            "issue_date": "24/02/2026",
            "maturity_date": "15/02/2042",
            "quantity_emitted": "86200",
            "volume_emitted": "86200000",
            "pu_issue": "1000",
            "payment_frequency": "Semestral",
            "amortization_frequency": "Semestral",
            "distribution": "Res CVM 160",
            "risk_type": "Duas series",
            "guarantees": "Conforme documentos da emissao.",
            "remuneration_label": "IPCA + 9,4659% / 10,9659%",
        },
    ),
    "axs06": OperationConfig(
        id="axs06",
        label="AXS 06",
        full_name="AXS 06 - Emissao 2 / Serie UNICA",
        badge="DEB",
        category="Debenture",
        indexer="IPCA + 10,38%",
        description="Debenture AXSE12 com incorporacoes iniciais e amortizacao semestral longa.",
        issuer="AXS ENERGIA UNIDADE 06 S.A.",
        code_if="AXSE12",
        isin="BRAXSEDBS029",
        script_path=PROJECT_DIR / "Code final prontos" / "axs06_v1.py",
        loader=lambda module: load_axs_internal_formula(module, "Fonte IPCA"),
        metadata={
            "issue_date": "06/03/2026",
            "maturity_date": "15/03/2043",
            "quantity_emitted": "30000",
            "volume_emitted": "30000000",
            "pu_issue": "1000",
            "payment_frequency": "Semestral",
            "amortization_frequency": "Semestral",
            "distribution": "Res CVM 160",
            "risk_type": "Corporativo",
            "guarantees": "Conforme documentos da emissao.",
            "remuneration_label": "IPCA + 10.3849%",
        },
    ),
    "axs07": OperationConfig(
        id="axs07",
        label="AXS 07",
        full_name="AXS VII - Emissao 1 / Serie UNICA",
        badge="DEB",
        category="Debenture",
        indexer="IPCA + 10,50%",
        description="Debenture AXSU11 com curva completa de juros, PMT e saldo.",
        issuer="AXS ENERGIA UNIDADE 07 S.A.",
        code_if="AXSU11",
        isin="BRAXSUDBS009",
        script_path=PROJECT_DIR / "Code final prontos" / "axs07_v17.py",
        loader=lambda module: load_axs_standard(module, "Fonte IPCA"),
        metadata={
            "issue_date": "15/03/2024",
            "maturity_date": "15/03/2034",
            "quantity_emitted": "75500",
            "volume_emitted": "75500000",
            "pu_issue": "1000",
            "payment_frequency": "Mensal",
            "amortization_frequency": "Mensal",
            "distribution": "Res CVM 160",
            "risk_type": "Corporativo",
            "guarantees": "Alienacao Fiduciaria de Acoes, Alienacao Fiduciaria de Imovel, Cessao Fiduciaria de Direitos Creditorios, Fianca",
            "remuneration_label": "IPCA + 10.5%",
        },
    ),
    "axs08": OperationConfig(
        id="axs08",
        label="AXS 08",
        full_name="AXS 08 - Emissao 1 / Serie UNICA",
        badge="DEB",
        category="Debenture",
        indexer="IPCA + 11%",
        description="Debenture AXS811 com juros semestrais e amortizacao longa.",
        issuer="AXS ENERGIA UNIDADE 08 LTDA.",
        code_if="AXS811",
        isin="BRAXS8DBS007",
        script_path=PROJECT_DIR / "Code final prontos" / "axs08_v2.py",
        loader=lambda module: load_axs_standard(module, "Fonte IPCA"),
        metadata={
            "issue_date": "01/07/2024",
            "maturity_date": "15/06/2038",
            "quantity_emitted": "120000",
            "volume_emitted": "120000000",
            "pu_issue": "1000",
            "payment_frequency": "Semestral",
            "amortization_frequency": "Anual",
            "distribution": "Res CVM 160",
            "risk_type": "-",
            "guarantees": "Alienacao Fiduciaria de Acoes, Alienacao Fiduciaria de Maquinas, Alienacao Fiduciaria de Direitos Creditorios",
            "remuneration_label": "IPCA + 11%",
        },
    ),
    "axs09": OperationConfig(
        id="axs09",
        label="AXS 09",
        full_name="AXS ENERGIA 09 - Emissao 1 / Serie UNICA",
        badge="DEB",
        category="Debenture",
        indexer="IPCA + 10,98%",
        description="Debenture AXS 09 com capitalizacoes iniciais e pagamentos semestrais.",
        issuer="AXS ENERGIA UNIDADE 09 S.A.",
        code_if="AXS911",
        isin="BRAXS9DBS005",
        script_path=PROJECT_DIR / "Code final prontos" / "axs09_v1.py",
        loader=lambda module: load_axs_standard(module, "Fonte IPCA"),
        metadata={
            "issue_date": "20/09/2024",
            "maturity_date": "15/09/2038",
            "quantity_emitted": "93000",
            "volume_emitted": "93000000",
            "pu_issue": "1000",
            "payment_frequency": "Semestral",
            "amortization_frequency": "Semestral",
            "distribution": "Res CVM 160",
            "risk_type": "-",
            "guarantees": "Alienacao Fiduciaria de Acoes, Alienacao Fiduciaria de Maquinas, Alienacao Fiduciaria de Direitos Creditorios",
            "remuneration_label": "IPCA + 10.98%",
        },
    ),
    "axs10": OperationConfig(
        id="axs10",
        label="AXS 10",
        full_name="AXS ENERGIA 10 - Emissao 1 / Serie UNICA",
        badge="DEB",
        category="Debenture",
        indexer="CDI + 6,50%",
        description="Debenture mezanino indexada ao CDI com foco em spread e cronograma.",
        issuer="AXS ENERGIA UNIDADE 10 S.A.",
        code_if="AXS411",
        isin="BRAXS4DBS006",
        script_path=PROJECT_DIR / "Code final prontos" / "axs10_v15.py",
        loader=lambda module: load_axs_standard(module, "Fonte CDI"),
        metadata={
            "issue_date": "15/09/2024",
            "maturity_date": "15/09/2036",
            "quantity_emitted": "57000",
            "volume_emitted": "57000000",
            "pu_issue": "1000",
            "payment_frequency": "Mensal",
            "amortization_frequency": "Mensal",
            "distribution": "Res CVM 160",
            "risk_type": "-",
            "guarantees": "Conforme documentos da emissao.",
            "remuneration_label": "CDI + 6.5%",
        },
    ),
    "axs11": OperationConfig(
        id="axs11",
        label="AXS 11",
        full_name="AXS 11 - Emissao 1 / Serie UNICA",
        badge="DEB",
        category="Debenture",
        indexer="IPCA + 10,74%",
        description="Debenture AXSI11 com tres incorporacoes iniciais e amortizacao semestral.",
        issuer="AXS ENERGIA UNIDADE 11 S.A.",
        code_if="AXSI11",
        isin="BRAXSIDBS004",
        script_path=PROJECT_DIR / "Code final prontos" / "axs11_v1.py",
        loader=lambda module: load_axs_internal_formula(module, "Fonte IPCA"),
        metadata={
            "issue_date": "15/09/2025",
            "maturity_date": "15/09/2041",
            "quantity_emitted": "170000",
            "volume_emitted": "170000000",
            "pu_issue": "1000",
            "payment_frequency": "Semestral",
            "amortization_frequency": "Semestral",
            "distribution": "Res CVM 160",
            "risk_type": "Garantia real",
            "guarantees": "Garantia real e garantia adicional fidejussoria.",
            "remuneration_label": "IPCA + 10.7385%",
        },
    ),
}


def build_portfolio_payload() -> dict[str, Any]:
    payloads = [comparison_payload(operation_id) for operation_id in OPERATIONS]
    comparison = build_comparison_rows(payloads)
    series = build_portfolio_series(payloads)
    summary = build_summary(series)
    total_volume = sum(item["current_balance"] for item in comparison)
    operation = {
        "id": PORTFOLIO_ID,
        "label": "Visao Geral",
        "full_name": "Carteira consolidada de dividas - AXS Energia",
        "badge": "Carteira",
        "category": "Analise geral",
        "indexer": "Multiplos indexadores",
        "description": "Consolidado das emissoes para leitura executiva da carteira.",
        "issuer": "AXS Energia",
        "script_path": "Consolidado a partir dos scripts individuais",
        "identity_fields": [
            {"label": "Emissoes ativas", "value": str(len(payloads))},
            {"label": "Tipos", "value": "CRI e Debenture"},
            {"label": "Escopo", "value": "Todas as emissoes mapeadas"},
        ],
        "overview_fields": [
            {"label": "Saldo consolidado", "value": str(summary["current_balance"]) if summary["current_balance"] is not None else "-"},
            {"label": "Proximo PMT da carteira", "value": str(summary["next_payment_amount"]) if summary["next_payment_amount"] is not None else "-"},
            {"label": "Data do proximo PMT", "value": summary["next_payment_date"] or "-"},
            {"label": "Juros acumulados", "value": str(summary["total_interest"])},
            {"label": "Amortizacao acumulada", "value": str(summary["total_amortization"])},
            {"label": "Saldo somado das emissoes", "value": str(total_volume)},
        ],
        "pu_fields": [
            {"label": "Emissao com maior saldo", "value": comparison[0]["label"] if comparison else "-"},
            {"label": "Maior saldo atual", "value": str(comparison[0]["current_balance"]) if comparison else "-"},
            {"label": "Maior juros acumulados", "value": str(max((item["total_interest"] for item in comparison), default=0.0))},
            {"label": "Maior amortizacao acumulada", "value": str(max((item["total_amortization"] for item in comparison), default=0.0))},
        ],
    }
    return {
        "operation": operation,
        "series": series,
        "table_series": series,
        "summary": summary,
        "timeline": build_timeline(series),
        "meta": {
            "primary_source": "Consolidado gerado a partir dos scripts individuais de calculo.",
            "notes": "A visao geral soma eventos, saldos e metricas das operacoes individuais.",
        },
        "comparison": comparison,
        "variant_options": [],
        "selected_variant": "",
        "generated_at": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
    }


@lru_cache(maxsize=None)
def compute_operation(operation_id: str) -> dict[str, Any]:
    if operation_id not in OPERATIONS:
        raise KeyError(operation_id)
    config = OPERATIONS[operation_id]
    module_name = f"codexdash_{operation_id}"
    module = load_module(module_name, config.script_path)
    base_payload = config.loader(module)
    if "variants" in base_payload:
        payload = {
            "operation": build_operation_view(config, base_payload, module)["operation"],
            "series": base_payload["series"],
            "table_series": base_payload.get("table_series", base_payload["series"]),
            "summary": base_payload["summary"],
            "timeline": base_payload["timeline"],
            "meta": base_payload["meta"],
            "variant_options": base_payload["variant_options"],
            "variants": {},
        }
        for variant_id, variant_payload in base_payload["variants"].items():
            merged_config = OperationConfig(
                id=config.id,
                label=config.label,
                full_name=variant_payload["operation_overrides"].get("full_name", config.full_name),
                badge=variant_payload["operation_overrides"].get("badge", config.badge),
                category=config.category,
                indexer=config.indexer,
                description=variant_payload["operation_overrides"].get("description", config.description),
                issuer=variant_payload["operation_overrides"].get("issuer", config.issuer),
                script_path=config.script_path,
                loader=config.loader,
                code_if=variant_payload["operation_overrides"].get("metadata", {}).get("code_if", config.code_if),
                isin=variant_payload["operation_overrides"].get("metadata", {}).get("isin", config.isin),
                metadata={**config.metadata, **variant_payload["operation_overrides"].get("metadata", {})},
            )
            payload["variants"][variant_id] = build_operation_view(merged_config, variant_payload, module)
        payload["selected_variant"] = AXS02_DEFAULT_VARIANT
    else:
        payload = build_operation_view(config, base_payload, module)
        payload["variant_options"] = []
        payload["variants"] = {}
        payload["selected_variant"] = ""

    payload["comparison"] = []
    payload["generated_at"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    return payload


def apply_variant(payload: dict[str, Any], variant_id: str) -> dict[str, Any]:
    if not payload.get("variants"):
        return payload
    selected = payload["variants"].get(variant_id) or payload["variants"][AXS02_DEFAULT_VARIANT]
    merged = deepcopy(payload)
    merged["operation"] = selected["operation"]
    merged["series"] = selected["series"]
    merged["table_series"] = selected["table_series"]
    merged["summary"] = selected["summary"]
    merged["timeline"] = selected["timeline"]
    merged["meta"] = selected["meta"]
    merged["selected_variant"] = variant_id if variant_id in payload["variants"] else AXS02_DEFAULT_VARIANT
    return merged


def get_payload(operation_id: str, variant_id: str | None = None) -> dict[str, Any]:
    if operation_id == PORTFOLIO_ID:
        return build_portfolio_payload()
    payload = deepcopy(compute_operation(operation_id))
    payload = apply_variant(payload, variant_id or AXS02_DEFAULT_VARIANT)
    payload["comparison"] = build_comparison_rows([comparison_payload(item_id) for item_id in OPERATIONS])
    return payload


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/api/operations":
            operations = [
                {
                    "id": PORTFOLIO_ID,
                    "label": "Visao Geral",
                    "category": "Carteira",
                    "indexer": "Consolidado",
                    "badge": "Carteira",
                    "variant_options": [],
                }
            ]
            operations.extend(
                {
                    "id": item.id,
                    "label": item.label,
                    "category": item.category,
                    "indexer": item.indexer,
                    "badge": item.badge,
                    "variant_options": [
                        {"id": "total", "label": "Total"},
                        {"id": "cri", "label": "CRI"},
                        {"id": "deb", "label": "Debenture"},
                    ] if item.id == "axs02" else [],
                }
                for item in OPERATIONS.values()
            )
            self.respond_json({"operations": operations})
            return

        if path.startswith("/api/operations/"):
            operation_id = path.split("/")[-1]
            variant_id = query.get("variant", [None])[0]
            try:
                if query.get("refresh") == ["1"]:
                    compute_operation.cache_clear()
                payload = get_payload(operation_id, variant_id)
            except KeyError:
                self.respond_error(HTTPStatus.NOT_FOUND, f"Operacao '{operation_id}' nao encontrada.")
                return
            except Exception as exc:
                self.respond_error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Falha ao calcular '{operation_id}': {exc}")
                return
            self.respond_json(payload)
            return

        if path == "/":
            self.serve_file(DASH_DIR / "dashhtml.html", "text/html; charset=utf-8")
            return

        file_map = {
            "/dashboard.css": DASH_DIR / "dashboard.css",
            "/dashboard.js": DASH_DIR / "dashboard.js",
        }
        if path in file_map:
            content_type = "text/css; charset=utf-8" if path.endswith(".css") else "application/javascript; charset=utf-8"
            self.serve_file(file_map[path], content_type)
            return

        self.respond_error(HTTPStatus.NOT_FOUND, "Rota nao encontrada.")

    def serve_file(self, file_path: Path, content_type: str) -> None:
        if not file_path.exists():
            self.respond_error(HTTPStatus.NOT_FOUND, f"Arquivo nao encontrado: {file_path.name}")
            return
        content = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def respond_json(self, payload: dict[str, Any]) -> None:
        body = json.dumps(decimal_to_float(payload), ensure_ascii=False).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def respond_error(self, status: HTTPStatus, message: str) -> None:
        body = json.dumps({"error": message}, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return


def run_server(port: int = 8000) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), DashboardHandler)
    print(f"Dashboard disponivel em http://127.0.0.1:{port}")
    print("Pressione Ctrl+C para encerrar.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run_server()
