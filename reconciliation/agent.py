import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path


def number(value, field):
    if value is None or isinstance(value, bool):
        raise ValueError(f"{field} must be numeric")
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise ValueError(f"{field} must be numeric")
    if not result.is_finite() or result < 0:
        raise ValueError(f"{field} must be finite and non-negative")
    return result


def reconcile(data):
    required = ["work_order", "target_quantity", "mes_good",
                "mes_rejected", "batches"]
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"Missing fields: {missing}")

    target = number(data["target_quantity"], "target_quantity")
    good = number(data["mes_good"], "mes_good")
    rejected = number(data["mes_rejected"], "mes_rejected")

    if not isinstance(data["batches"], list):
        raise ValueError("batches must be a list")

    findings = []

    def flag(code, severity, detail):
        findings.append({
            "code": code,
            "severity": severity,
            "detail": detail
        })

    if good > target:
        flag(
            "OVER_TARGET",
            "HIGH",
            f"MES good {good} exceeds target {target} "
            f"by {good - target} units. Verify counter scope, "
            "duplicates and work-order assignment."
        )

    batch_total = Decimal("0")
    posted_total = Decimal("0")
    unposted = []

    for batch in data["batches"]:
        qty = number(batch["quantity"], "batch.quantity")
        batch_total += qty

        if str(batch.get("status", "")).upper() == "POSTED" \
                and batch.get("erp_stock_entry"):
            posted_total += qty
        else:
            unposted.append(batch.get("batch_id", "UNKNOWN"))

    if unposted:
        flag(
            "UNPOSTED_BATCHES",
            "HIGH",
            f"{len(unposted)} MES batches lack confirmed "
            "ERP posting references."
        )

    if batch_total != good:
        flag(
            "MES_BATCH_COVERAGE",
            "HIGH",
            f"MES good total {good}; batch quantity total "
            f"{batch_total}. Difference {good - batch_total}. "
            "Check whether batches cover the same period."
        )

    if data.get("erp_manufactured_qty") is not None:
        erp_qty = number(
            data["erp_manufactured_qty"], "erp_manufactured_qty"
        )
        if erp_qty != good:
            flag(
                "ERP_MES_VARIANCE",
                "HIGH",
                f"ERP manufactured {erp_qty}; MES good {good}. "
                f"Difference {good - erp_qty}. "
                "Confirm matching time windows before reconciliation."
            )
    else:
        erp_qty = None
        flag(
            "ERP_QUANTITY_UNAVAILABLE",
            "INFO",
            "ERP manufactured quantity not supplied."
        )

    machine_good = data.get("machine_good")
    if machine_good is not None:
        machine_good = number(machine_good, "machine_good")
        if machine_good != good:
            flag(
                "COUNTER_SCOPE_REVIEW",
                "MEDIUM",
                f"Machine good counter {machine_good} differs "
                f"from MES good {good}. Check counter resets, "
                "time windows and filtering before interpreting."
            )

    source_times = data.get("source_timestamps", {})
    if len(set(source_times.values())) > 1:
        flag(
            "SNAPSHOT_ALIGNMENT",
            "MEDIUM",
            "Source timestamps differ. Align the reporting "
            "periods before treating variances as confirmed."
        )

    return {
        "work_order": data["work_order"],
        "mode": "READ_ONLY",
        "summary": {
            "target_quantity": str(target),
            "mes_good": str(good),
            "mes_rejected": str(rejected),
            "listed_batch_quantity": str(batch_total),
            "batch_quantity_with_posting_reference": str(posted_total),
            "erp_manufactured_qty": (
                str(erp_qty) if erp_qty is not None else None
            )
        },
        "findings": findings,
        "requires_human_review": any(
            f["severity"] == "HIGH" for f in findings
        ),
        "erp_write_performed": False
    }


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: py reconciliation/agent.py input.json")

    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8-sig"))
    result = reconcile(data)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
