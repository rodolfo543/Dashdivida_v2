from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime
from decimal import Decimal
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent
DOCS_DIR = ROOT_DIR / "docs"
ROOT_DATA_DIR = ROOT_DIR / "data"
DOCS_DATA_DIR = DOCS_DIR / "data"


def load_engine() -> Any:
    module_path = ROOT_DIR / "dashboard_server.py"
    if not module_path.exists():
        raise FileNotFoundError(f"Motor do dashboard nao encontrado em: {module_path}")

    spec = importlib.util.spec_from_file_location("codexdash_static_engine", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Nao foi possivel carregar o modulo: {module_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules["codexdash_static_engine"] = module
    spec.loader.exec_module(module)
    return module


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def to_json_compatible(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y %H:%M:%S")
    if hasattr(value, "strftime"):
        try:
            return value.strftime("%d/%m/%Y")
        except Exception:
            pass
    if isinstance(value, dict):
        return {key: to_json_compatible(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_json_compatible(item) for item in value]
    return value


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable = to_json_compatible(payload)
    path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")


def with_generation_meta(payload: dict[str, Any], generated_at: str, generated_at_iso: str) -> dict[str, Any]:
    enriched = dict(payload)
    enriched["generated_at"] = generated_at
    enriched["generated_at_iso"] = generated_at_iso
    return enriched


def build_operations_manifest(engine: Any, generated_at: str, generated_at_iso: str) -> dict[str, Any]:
    operations = [
        {
            "id": engine.PORTFOLIO_ID,
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
            "variant_options": engine.variant_options_for(item.id),
        }
        for item in engine.OPERATIONS.values()
    )
    return {
        "generated_at": generated_at,
        "generated_at_iso": generated_at_iso,
        "operations": operations,
    }


def rebuild_data_dirs() -> None:
    for data_dir in (ROOT_DATA_DIR, DOCS_DATA_DIR):
        (data_dir / "operations").mkdir(parents=True, exist_ok=True)
        for json_file in sorted(data_dir.rglob("*.json"), reverse=True):
            json_file.unlink(missing_ok=True)


def generate_operation_payloads(engine: Any, generated_at: str, generated_at_iso: str) -> None:
    manifest = build_operations_manifest(engine, generated_at, generated_at_iso)
    for base_dir in (ROOT_DATA_DIR, DOCS_DATA_DIR):
        write_json(base_dir / "operations.json", manifest)

    portfolio_payload = with_generation_meta(engine.get_payload(engine.PORTFOLIO_ID), generated_at, generated_at_iso)
    write_json(ROOT_DATA_DIR / "operations" / f"{engine.PORTFOLIO_ID}.json", portfolio_payload)
    write_json(DOCS_DATA_DIR / "operations" / f"{engine.PORTFOLIO_ID}.json", portfolio_payload)

    for operation_id in engine.OPERATIONS:
        payload = with_generation_meta(engine.get_payload(operation_id), generated_at, generated_at_iso)
        write_json(ROOT_DATA_DIR / "operations" / f"{operation_id}.json", payload)
        write_json(DOCS_DATA_DIR / "operations" / f"{operation_id}.json", payload)
        for option in engine.variant_options_for(operation_id):
            variant_id = option["id"]
            variant_payload = with_generation_meta(engine.get_payload(operation_id, variant_id), generated_at, generated_at_iso)
            filename = f"{operation_id}.json" if variant_id == "total" else f"{operation_id}--{variant_id}.json"
            write_json(ROOT_DATA_DIR / "operations" / filename, variant_payload)
            write_json(DOCS_DATA_DIR / "operations" / filename, variant_payload)


def sync_optional_knowledge_assets() -> None:
    chunks_path = ROOT_DIR / "chunks.json"
    if not chunks_path.exists():
        return
    content = chunks_path.read_text(encoding="utf-8")
    write_text(ROOT_DATA_DIR / "chunks.json", content)
    write_text(DOCS_DATA_DIR / "chunks.json", content)


def sync_frontend_assets() -> None:
    html = (ROOT_DIR / "dashhtml.html").read_text(encoding="utf-8")
    css = (ROOT_DIR / "dashboard.css").read_text(encoding="utf-8")
    js = (ROOT_DIR / "dashboard.js").read_text(encoding="utf-8")

    write_text(ROOT_DIR / "index.html", html)
    write_text(DOCS_DIR / "index.html", html)
    write_text(DOCS_DIR / "dashboard.css", css)
    write_text(DOCS_DIR / "dashboard.js", js)
    write_text(DOCS_DIR / ".nojekyll", "")


def build_static_site() -> None:
    engine = load_engine()
    generated = datetime.now()
    generated_at = generated.strftime("%d/%m/%Y %H:%M:%S")
    generated_at_iso = generated.isoformat(timespec="seconds")

    rebuild_data_dirs()
    sync_frontend_assets()
    sync_optional_knowledge_assets()
    generate_operation_payloads(engine, generated_at, generated_at_iso)


def serve_docs(port: int) -> None:
    docs_root = str(DOCS_DIR)

    class DocsHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=docs_root, **kwargs)

    server = ThreadingHTTPServer(("127.0.0.1", port), DocsHandler)
    print(f"Preview estatico disponivel em http://127.0.0.1:{port}")
    print("Pressione Ctrl+C para encerrar.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gera a versao estatica do dashboard e opcionalmente serve um preview local."
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="serve",
        choices=("build", "serve"),
        help="build gera os arquivos. serve gera e abre um preview local.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Porta do preview local quando usar o comando serve.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build_static_site()
    if args.command == "serve":
        serve_docs(args.port)
    else:
        print("Build estatico concluido.")
        print(f"Arquivos publicados em: {DOCS_DIR}")


if __name__ == "__main__":
    main()
