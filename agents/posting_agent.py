import json
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "reconciliation" / "root_cause_report.json"
OUTPUT = ROOT / "reconciliation" / "posting_proposal.json"


def num(value):
    return Decimal(str(value or 0))


def build_proposal(report):
    summary = report["summary"]
    findings = report["findings"]

    target = num(summary["erp_target"])
    erp = num(summary["erp_manufactured"])
    good = num(summary["mes_good"])
    batch_qty = num(summary["mes_batch_quantity"])
    posted = num(summary["mes_linked_posted_quantity"])

    high_risks = [
        f["code"] for f in findings
        if f["severity"] == "HIGH"
    ]

    reasons = []

    if good > target:
        reasons.append("MES production exceeds ERP target")

    if batch_qty < good:
        reasons.append("MES batch coverage incomplete")

    if erp != posted:
        reasons.append("ERP quantity differs from linked batches")

    if high_risks:
        reasons.append(
            "High severity root-cause findings unresolved"
        )

    return {
        "proposal_type": "MES_TO_ERP_BATCH_POSTING",
        "work_order": report["work_order"],
        "created_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "evidence": {
            "erp_target": str(target),
            "erp_manufactured": str(erp),
            "mes_good": str(good),
            "batch_quantity": str(batch_qty),
            "linked_posted_quantity": str(posted)
        },
        "risk_findings": high_risks,
        "decision": "BLOCKED" if reasons else "REVIEW_REQUIRED",
        "reasons": reasons,
        "human_approval_required": True,
        "approved": False,
        "erp_write_performed": False,
        "execution_enabled": False
    }


def main():
    report = json.loads(
        SOURCE.read_text(encoding="utf-8-sig")
    )

    proposal = build_proposal(report)

    OUTPUT.write_text(
        json.dumps(proposal, indent=2),
        encoding="utf-8"
    )

    print("=== GOVERNED BATCH POSTING PROPOSAL ===")
    print("Work Order:", proposal["work_order"])
    print("Decision:", proposal["decision"])
    print("High Risks:", len(proposal["risk_findings"]))
    print("ERP Writes:", proposal["erp_write_performed"])
    print("Proposal:", OUTPUT)

    for reason in proposal["reasons"]:
        print("BLOCKER:", reason)


if __name__ == "__main__":
    main()
