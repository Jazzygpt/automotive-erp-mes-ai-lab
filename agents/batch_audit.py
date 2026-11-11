
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / "mcp-server" / ".env", override=True)

WO = "MFG-WO-2026-00003"
OUT = ROOT / "reconciliation" / "batch_audit.json"

def number(v):
    return Decimal(str(v or 0))

def get_erp_entries():
    key = os.environ["ERPNEXT_API_KEY"]
    secret = os.environ["ERPNEXT_API_SECRET"]
    base = os.getenv("ERPNEXT_URL", "http://localhost:8080").rstrip("/")

    entries = []
    start = 0

    for _ in range(10):
        params = urllib.parse.urlencode({
            "fields": json.dumps([
                "name", "work_order", "docstatus",
                "purpose", "fg_completed_qty"
            ]),
            "filters": json.dumps([
                ["work_order", "=", WO],
                ["docstatus", "=", 1]
            ]),
            "limit_start": start,
            "limit_page_length": 100
        })

        url = f"{base}/api/resource/Stock%20Entry?{params}"

        request = urllib.request.Request(
            url,
            headers={
                "Authorization": f"token {key}:{secret}",
                "Accept": "application/json"
            },
            method="GET"
        )

        with urllib.request.urlopen(request, timeout=30) as response:
            page = json.load(response)["data"]

        entries.extend(page)

        if len(page) < 100:
            return entries

        start += 100

    raise RuntimeError("ERP result limit reached; audit incomplete")

def main():
    # Refresh existing read-only MES and ERP evidence.
    subprocess.run(
        [sys.executable, str(ROOT / "agents" / "run_live.py")],
        check=True
    )

    snapshot = json.loads(
        (ROOT / "reconciliation" / "live_snapshot.json")
        .read_text(encoding="utf-8-sig")
    )

    progress = snapshot["progress"]
    if len(progress) != 1 or progress[0]["work_order_id"] != WO:
        raise RuntimeError("MES work-order validation failed")

    batches = snapshot["batches"]

    # Retrieve submitted ERP stock entries for this work order.
    erp_entries = get_erp_entries()
    manufacturing_entries = [
        e for e in erp_entries
        if e.get("purpose") == "Manufacture"
    ]

    erp_by_name = {
        e["name"]: e for e in manufacturing_entries
    }

    refs = [
        str(b["erp_stock_entry"])
        for b in batches if b.get("erp_stock_entry")
    ]
    duplicate_refs = {
        r for r, count in Counter(refs).items()
        if count > 1
    }

    results = []

    for batch in batches:
        ref = batch.get("erp_stock_entry")
        entry = erp_by_name.get(ref)
        quantity = number(batch.get("quantity"))

        issues = []

        if not ref:
            issues.append("NO_ERP_REFERENCE")
        elif ref in duplicate_refs:
            issues.append("DUPLICATE_ERP_REFERENCE")

        if ref and not entry:
            issues.append("ERP_POSTING_NOT_VERIFIED")

        if entry and quantity != number(entry["fg_completed_qty"]):
            issues.append("QUANTITY_MISMATCH")

        results.append({
            "batch_id": batch.get("batch_id"),
            "mes_quantity": str(quantity),
            "erp_reference": ref,
            "erp_quantity": (
                str(number(entry["fg_completed_qty"]))
                if entry else None
            ),
            "result": "MATCHED" if not issues else "REVIEW",
            "issues": issues
        })

    referenced = set(refs)

    unmatched_erp = [
        {
            "stock_entry": e["name"],
            "quantity": str(number(e["fg_completed_qty"]))
        }
        for e in manufacturing_entries
        if e["name"] not in referenced
    ]

    report = {
        "work_order": WO,
        "audit_type": "READ_ONLY_BATCH_RECONCILIATION",
        "mes_batches_checked": len(results),
        "erp_manufacturing_entries_checked":
            len(manufacturing_entries),
        "batch_results": results,
        "erp_entries_without_mes_batch": unmatched_erp,
        "decision": "HUMAN_REVIEW_REQUIRED",
        "erp_writes": False,
        "posting_enabled": False
    }

    OUT.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8"
    )

    print("\n=== BATCH LEVEL ERP RECONCILIATION ===")
    print("MES batches:", len(results))
    print("ERP manufacturing entries:", len(manufacturing_entries))

    for b in results:
        print(
            b["batch_id"],
            "|", b["result"],
            "|", ",".join(b["issues"]) or "VERIFIED"
        )

    print("Unmatched ERP entries:", len(unmatched_erp))
    for entry in unmatched_erp:
        print("UNMATCHED:", entry["stock_entry"],
              "Qty:", entry["quantity"])

    print("Governance:", report["decision"])
    print("ERP Writes:", report["erp_writes"])
    print("Report:", OUT)

if __name__ == "__main__":
    main()
