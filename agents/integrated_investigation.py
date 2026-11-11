"""Read-only ERPNext/MES integrated investigation.

Calls the existing, verified investigation programs and correlates their
outputs. Never creates or submits an ERPNext transaction.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "reconciliation"
SUPPORTED_WO = "MFG-WO-2026-00003"


def load_json(name: str) -> dict:
    path = OUT_DIR / name
    if not path.is_file():
        raise RuntimeError(f"Expected report missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise RuntimeError(f"Report has invalid structure: {name}")
    return data


def run_existing(script: str) -> None:
    path = ROOT / "agents" / script
    if not path.is_file():
        raise RuntimeError(f"Required existing program missing: {path}")
    completed = subprocess.run(
        [sys.executable, str(path)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if completed.returncode:
        # Prevent inadvertent credential leakage via unfiltered exception logs.
        raise RuntimeError(f"{script} failed; see its local terminal log (exit {completed.returncode})")


def investigate(work_order_id: str) -> dict:
    if work_order_id != SUPPORTED_WO:
        raise ValueError("This demonstration supports only the validated work order")

    # Both existing scripts refresh live data. The snapshots are NOT atomic.
    run_existing("batch_audit.py")
    audit = load_json("batch_audit.json")
    run_existing("root_cause.py")
    root_cause = load_json("root_cause_report.json")

    if audit.get("work_order") != work_order_id or root_cause.get("work_order") != work_order_id:
        raise RuntimeError("Work-order ID mismatch across reports")
    if audit.get("erp_writes") is not False:
        raise RuntimeError("Batch audit did not attest read-only execution")
    if root_cause.get("governance", {}).get("erp_write_performed") is not False:
        raise RuntimeError("Root-cause report did not attest read-only execution")

    unmatched = audit.get("erp_entries_without_mes_batch")
    batches = audit.get("batch_results")
    if not isinstance(unmatched, list) or not isinstance(batches, list):
        raise RuntimeError("Batch audit evidence is incomplete")

    unmatched_total = sum(float(x["quantity"]) for x in unmatched)
    details = [
        {
            "code": "ERP_STOCK_ENTRY_MISSING_MES_BATCH",
            "severity": "HIGH",
            "status": "CONFIRMED_REFERENCE_GAP",
            "evidence": {
                "unmatched_erp_stock_entries": unmatched,
                "unmatched_erp_quantity": unmatched_total,
                "matched_batch_count": sum(b.get("result") == "MATCHED" for b in batches),
            },
            "interpretation": "One or more submitted ERP manufacturing Stock Entries have no corresponding reference in the MES batch ledger. This does not prove the ERP entry is wrong or duplicated.",
            "recommended_action": "Inspect the original Stock Entry creation context and any historical/manual posting workflow before changing records.",
            "root_cause_confirmed": False,
        }
    ] if unmatched else []

    result = {
        "system": "Factory AI Integrated Manufacturing Investigation",
        "work_order": work_order_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_freshness": "Live queries run sequentially; not a transactionally consistent cross-system snapshot",
        "erp_mes_summary": root_cause.get("summary", {}),
        "root_cause_findings": root_cause.get("findings", []),
        "batch_audit": {
            "mes_batches_checked": audit.get("mes_batches_checked"),
            "erp_manufacturing_entries_checked": audit.get("erp_manufacturing_entries_checked"),
            "batch_results": batches,
            "unmatched_erp_entries": unmatched,
        },
        "additional_transaction_findings": details,
        "proposed_corrective_actions": root_cause.get("corrective_actions", []) + [
            {"finding": item["code"], "recommendation": item["recommended_action"],
             "requires_human_approval": True, "execution_status": "NOT_EXECUTED"}
            for item in details
        ],
        "governance": {
            "decision": "HUMAN_REVIEW_REQUIRED",
            "write_approved": False,
            "erp_write_performed": False,
            "actions_executed": 0,
        },
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("work_order_id", nargs="?", default=SUPPORTED_WO)
    args = parser.parse_args()
    result = investigate(args.work_order_id)
    OUT_DIR.mkdir(exist_ok=True)
    dest = OUT_DIR / "integrated_report.json"
    dest.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("=== INTEGRATED ERP + MES INVESTIGATION ===")
    print("Work order:", result["work_order"])
    print("Root-cause findings:", len(result["root_cause_findings"]))
    print("Unmatched ERP entries:", len(result["batch_audit"]["unmatched_erp_entries"]))
    print("Governance:", result["governance"]["decision"])
    print("ERP writes:", result["governance"]["erp_write_performed"])
    print("Report:", dest)


if __name__ == "__main__":
    main()
