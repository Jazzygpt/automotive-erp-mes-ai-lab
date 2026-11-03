import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents"))

from orchestrator import Supervisor

WORK_ORDER = "MFG-WO-2026-00003"

# Refresh live MES data before every investigation.
subprocess.run(
    [sys.executable, str(ROOT / "agents" / "live_adapter.py"),
     WORK_ORDER],
    check=True
)

snapshot = json.loads(
    (ROOT / "reconciliation" / "live_snapshot.json")
    .read_text(encoding="utf-8-sig")
)

progress = snapshot["progress"]
batches = snapshot["batches"]

if len(progress) != 1:
    raise RuntimeError(
        f"Expected one work order, received {len(progress)}"
    )

p = progress[0]

if p["work_order_id"] != WORK_ORDER:
    raise RuntimeError("Work order ID mismatch")

data = {
    "work_order": WORK_ORDER,
    "target_quantity": p["target_quantity"],
    "mes_good": p["good_quantity"],
    "mes_rejected": p["rejected_quantity"],
    "machine_good": p.get("last_machine_good"),
    "batches": [
        {
            "batch_id": b["batch_id"],
            "quantity": b["quantity"],
            "status": b["status"],
            "erp_stock_entry": b.get("erp_stock_entry")
        }
        for b in batches
    ]
}

# Do not invent ERP quantities from MES values.
# ERP reconciliation requires a separate ERPNext read.
report = Supervisor().run(data)

report["data_provenance"] = {
    "mes_source": "LIVE_POSTGRESQL",
    "erp_source": "NOT_YET_CONNECTED",
    "snapshot_time_utc": datetime.now(timezone.utc).isoformat(),
    "work_order_status": p["status"],
    "mes_last_updated": str(p.get("updated_at")),
    "erp_quantity_verified": False
}

output = ROOT / "reconciliation" / "live_report.json"
output.write_text(
    json.dumps(report, indent=2),
    encoding="utf-8"
)

print("\n=== LIVE MULTI-AGENT INVESTIGATION ===")
print("Work Order:", WORK_ORDER)
print("Agents:", report["supervisor_summary"]["agents_completed"])
print("Findings:", report["supervisor_summary"]["total_findings"])
print("Decision:", report["governance"]["decision"])
print("ERP Writes:", report["governance"]["erp_write_performed"])
print("ERP quantity verified: False")
print("Report:", output)
