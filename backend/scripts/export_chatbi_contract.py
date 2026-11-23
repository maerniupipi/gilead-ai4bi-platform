"""Export the integration contract without importing main or connecting to a database."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from app.routers.chatbi.router import router
from app.schemas.chatbi import TableOutputs, ChartOutputs, ProgressNode


def export_contract(output):
    output = Path(output)
    (output / "schemas").mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="AI4BI Platform Service", version="1.0.0",
                  description="Streaming data analysis, progress, results and export service contract.")
    app.include_router(router)
    spec = app.openapi()
    spec["components"]["securitySchemes"] = {"serviceBearer": {
        "type": "http", "scheme": "bearer", "description": "Trusted server-to-server key; user identifies the end user."}}
    for path, methods in spec["paths"].items():
        for operation in methods.values():
            operation["security"] = [{"serviceBearer": []}]
            operation["parameters"] = [p for p in operation.get("parameters", []) if p.get("name") != "authorization"]
            codes = ("401", "403", "500", "503") if path == "/api/service/info" else ("400", "401", "403", "404", "409", "410", "413", "500", "503")
            for code in codes:
                operation["responses"][code] = {"description": "See README error codes", "content": {"application/json": {"schema": {
                    "type": "object", "properties": {"status": {"type": "integer"}, "code": {"type": "string"}, "message": {"type": "string"}},
                    "required": ["status", "code", "message"],
                }}}}
            operation["responses"].pop("422", None)
    spec["paths"]["/api/service/chat-messages"]["post"]["responses"]["200"]["content"].pop("application/json", None)
    (output / "openapi.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n")
    for name, model in (("table", TableOutputs), ("chart", ChartOutputs), ("progress", ProgressNode)):
        (output / "schemas" / f"{name}.schema.json").write_text(json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    export_contract(parser.parse_args().output_dir)
