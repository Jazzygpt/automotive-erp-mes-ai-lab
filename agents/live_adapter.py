import importlib.util
import json
import sys
from pathlib import Path
from datetime import date, datetime
from decimal import Decimal

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "mcp-server" / "server.py"

def json_safe(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"Unsupported type: {type(value)}")

def main():
    work_order = (
        sys.argv[1] if len(sys.argv) > 1
        else "MFG-WO-2026-00003"
    )

    spec = importlib.util.spec_from_file_location(
        "existing_mes_server", SERVER
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    progress = module.work_order_progress(work_order)
    batches = module.mes_batches(work_order)

    snapshot = {
        "work_order": work_order,
        "source": "LIVE_POSTGRESQL_MES",
        "mode": "READ_ONLY",
        "progress": progress,
        "batches": batches
    }

    destination = ROOT / "reconciliation" / "live_snapshot.json"
    destination.write_text(
        json.dumps(snapshot, indent=2, default=json_safe),
        encoding="utf-8"
    )

    print("LIVE MES SNAPSHOT CREATED")
    print("Progress rows:", len(progress))
    print("Batch rows:", len(batches))
    print("Progress fields:",
          list(progress[0]) if progress else [])
    print("Batch fields:",
          list(batches[0]) if batches else [])

if __name__ == "__main__":
    main()
