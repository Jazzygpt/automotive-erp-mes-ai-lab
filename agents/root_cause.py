import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "reconciliation" / "live_snapshot.json"
REPORT = ROOT / "reconciliation" / "live_report.json"
OUTPUT = ROOT / "reconciliation" / "root_cause_report.json"


def qty(value):
    return Decimal(str(value or 0))


def analyse(snapshot, report):
    progress = snapshot["progress"]
    if len(progress) != 1:
        raise ValueError("Expected exactly one MES work order")

    p = progress[0]
    wo = p["work_order_id"]

    if wo != report["work_order"]:
        raise ValueError("Work order mismatch between sources")

    evidence = report.get("data_provenance", {})
    if not evidence.get("erp_quantity_verified"):
        raise ValueError("Live ERPNext verification is required")

    erp_reports = [
        a for a in report["agents"]
        if a["agent"] == "ERP Analyst"
    ]
    if len(erp_reports) != 1:
        raise ValueError("ERP Analyst evidence missing")

    erp_qty_raw = erp_reports[0]["evidence"].get(
        "manufactured_quantity"
    )
    if erp_qty_raw is None:
        raise ValueError("ERP quantity missing")

    target = qty(p["target_quantity"])
    good = qty(p["good_quantity"])
    rejected = qty(p["rejected_quantity"])
    machine_good = (
        qty(p["last_machine_good"])
        if p.get("last_machine_good") is not None else None
    )
    erp_qty = qty(erp_qty_raw)

    batches = snapshot["batches"]

    posted = [
        b for b in batches
        if str(b.get("status", "")).upper() == "POSTED"
        and b.get("erp_stock_entry")
    ]
    posted_qty = sum(
        (qty(b["quantity"]) for b in posted),
        Decimal(0)
    )
    batch_qty = sum(
        (qty(b["quantity"]) for b in batches),
        Decimal(0)
    )

    findings = []
    actions = []

    def add(code, severity, facts, hypothesis, action):
        findings.append({
            "code": code,
            "severity": severity,
            "confirmed_evidence": facts,
            "possible_root_cause": hypothesis,
            "root_cause_confirmed": False
        })
        actions.append({
            "finding": code,
            "recommendation": action,
            "requires_human_approval": True,
            "execution_status": "NOT_EXECUTED"
        })

    if target > 0 and good > target:
        add(
            "TARGET_CONTROL_FAILURE",
            "HIGH",
            f"MES good={good}; ERP target={target}; "
            f"excess={good-target}",
            "The simulator or work-order assignment may "
            "lack a production target stop condition.",
            "Review simulator target logic and work-order "
            "assignment. Do not automatically close ERP orders."
        )

    if good > batch_qty:
        add(
            "BATCH_COVERAGE_GAP",
            "HIGH",
            f"MES good={good}; all recorded batch quantity="
            f"{batch_qty}; uncovered={good-batch_qty}",
            "Batch generation may be disabled, incomplete, "
            "or limited to one manual trigger.",
            "Inspect Node-RED batch creation triggers, "
            "logs and batch IDs. Do not backfill yet."
        )

    if good > posted_qty:
        add(
            "ERP_POSTING_COVERAGE_GAP",
            "HIGH",
            f"MES good={good}; MES-linked ERP posted "
            f"batch quantity={posted_qty}; gap={good-posted_qty}",
            "The batch-to-ERP posting workflow may have "
            "stopped or may not run automatically.",
            "Inspect the posting flow and API responses. "
            "Reconcile posting records before any retry."
        )

    if erp_qty != posted_qty:
        add(
            "ERP_BATCH_RECONCILIATION",
            "HIGH",
            f"ERP produced={erp_qty}; MES-linked posted "
            f"quantity={posted_qty}; difference="
            f"{erp_qty-posted_qty}",
            "ERPNext may contain other manufacturing stock "
            "entries not represented in the MES batch table.",
            "Retrieve all submitted ERP Stock Entries "
            "for this work order and match them by reference."
        )

    if machine_good is not None and machine_good != good:
        add(
            "COUNTER_BASELINE_REVIEW",
            "MEDIUM",
            f"Machine good={machine_good}; MES good={good}; "
            f"offset={machine_good-good}",
            "A cumulative machine counter may include "
            "production before this work order.",
            "Compare counter offsets across timestamps "
            "and record a baseline for each work order."
        )

    total = good + rejected
    yield_percent = (
        (good / total * 100) if total else Decimal(0)
    )

    if total and yield_percent < 95:
        add(
            "QUALITY_YIELD_REVIEW",
            "MEDIUM",
            f"Good={good}; rejected={rejected}; "
            f"yield={yield_percent:.2f}%",
            "Process rejects require further classification; "
            "the current aggregate cannot identify their cause.",
            "Review reject reasons and process conditions "
            "before recommending corrective process changes."
        )

    return {
        "system": "Factory AI Root Cause Investigation",
        "work_order": wo,
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "sources": ["ERPNext", "PostgreSQL MES"],
        "summary": {
            "erp_target": str(target),
            "erp_manufactured": str(erp_qty),
            "mes_good": str(good),
            "mes_rejected": str(rejected),
            "yield_percent": f"{yield_percent:.2f}",
            "mes_batch_quantity": str(batch_qty),
            "mes_linked_posted_quantity": str(posted_qty),
            "posted_batch_count": len(posted)
        },
        "findings": findings,
        "corrective_actions": actions,
        "governance": {
            "decision": (
                "HUMAN_REVIEW_REQUIRED"
                if findings else "READ_ONLY_REVIEW_COMPLETE"
            ),
            "write_approved": False,
            "erp_write_performed": False,
            "actions_executed": 0
        },
        "limitations": [
            "Machine counter baselines are not yet verified.",
            "ERP and MES reporting windows are not reconciled.",
            "Root causes remain hypotheses until investigated.",
            "MES batch references may not cover all ERP entries."
        ]
    }


def main():
    # Reuse the existing working ERP/MES investigation.
    subprocess.run(
        [sys.executable, str(ROOT / "agents" / "run_live.py")],
        check=True
    )

    snapshot = json.loads(
        SNAPSHOT.read_text(encoding="utf-8-sig")
    )
    report = json.loads(
        REPORT.read_text(encoding="utf-8-sig")
    )

    result = analyse(snapshot, report)

    OUTPUT.write_text(
        json.dumps(result, indent=2),
        encoding="utf-8"
    )

    print("\n=== SPRINT 3 ROOT CAUSE INVESTIGATION ===")
    print("Work Order:", result["work_order"])
    print("Findings:", len(result["findings"]))
    print("Actions:", len(result["corrective_actions"]))
    print("Governance:", result["governance"]["decision"])
    print("ERP Writes:", result["governance"]["erp_write_performed"])
    print("Report:", OUTPUT)

    for f in result["findings"]:
        print(f["severity"], f["code"])


if __name__ == "__main__":
    main()
