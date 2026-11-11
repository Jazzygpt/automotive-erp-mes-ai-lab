import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents"))
from orchestrator import Supervisor

WO = "MFG-WO-2026-00003"

# 1. Retrieve live MES information
subprocess.run(
    [sys.executable, str(ROOT / "agents/live_adapter.py"), WO],
    check=True
)

snapshot = json.loads(
    (ROOT / "reconciliation/live_snapshot.json")
    .read_text(encoding="utf-8-sig")
)

if len(snapshot["progress"]) != 1:
    raise RuntimeError("Expected exactly one MES work order")

p = snapshot["progress"][0]

if p["work_order_id"] != WO:
    raise RuntimeError("MES work order mismatch")

# 2. Retrieve live ERPNext information
result = subprocess.run(
    [sys.executable, str(ROOT / "erpnext/read_work_order.py"), WO],
    capture_output=True,
    text=True,
    check=True,
    timeout=30
)

erp = json.loads(result.stdout)

if erp["work_order"] != WO:
    raise RuntimeError("ERP work order mismatch")

if erp.get("produced_qty") is None:
    raise RuntimeError("ERP manufactured quantity unavailable")

# 3. Prepare shared agent evidence
data = {
    "work_order": WO,
    "target_quantity": p["target_quantity"],
    "mes_good": p["good_quantity"],
    "mes_rejected": p["rejected_quantity"],
    "machine_good": p.get("last_machine_good"),
    "erp_manufactured_qty": erp["produced_qty"],
    "batches": [
        {
            "batch_id": b["batch_id"],
            "quantity": b["quantity"],
            "status": b["status"],
            "erp_stock_entry": b.get("erp_stock_entry")
        }
        for b in snapshot["batches"]
    ]
}

# 4. Execute specialist agents and governance
report = Supervisor().run(data)

report["data_provenance"] = {
    "erp_source": "LIVE_ERPNEXT_API",
    "mes_source": "LIVE_POSTGRESQL",
    "erp_quantity_verified": True,
    "erp_status": erp["status"],
    "mes_status": p["status"],
    "erp_product": erp["production_item"],
    "mes_last_updated": str(p.get("updated_at")),
    "investigation_time_utc":
        datetime.now(timezone.utc).isoformat(),
    "time_windows_reconciled": False
}

report["operational_warning"] = (
    "ERP and MES quantities are real snapshots but their "
    "counter baselines and production periods have not "
    "been independently reconciled."
)

# 5. Save report locally (ignored by Git)
output = ROOT / "reconciliation/live_report.json"
output.write_text(
    json.dumps(report, indent=2),
    encoding="utf-8"
)

print("\n=== LIVE ERP + MES MULTI-AGENT INVESTIGATION ===")
print("Work Order:", WO)
print("ERP Manufactured:", erp["produced_qty"])
print("MES Good:", p["good_quantity"])
print("Agents:", report["supervisor_summary"]["agents_completed"])
print("Findings:", report["supervisor_summary"]["total_findings"])
print("Decision:", report["governance"]["decision"])
print("ERP Writes:", report["governance"]["erp_write_performed"])
print("Report:", output)
