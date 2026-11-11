from typing import Any
"""Local, read-only MCP tools for the Automotive Assembly Lab PostgreSQL database.

Place in automotive-assembly-lab/automotive-assembly-lab beside docker-compose.yml.
Install: py -m pip install fastmcp
Launch: py mes_mcp_server.py (typically launched by your MCP client as a stdio process).
No ERPNext or PostgreSQL passwords are stored in this file.
"""
from pathlib import Path
import re
import subprocess
from fastmcp import FastMCP

mcp = FastMCP("Automotive MES Traceability")
ROOT = Path(__file__).resolve().parent
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,100}$")


def read_sql(sql: str) -> list[dict[str, Any]]:
    # psql emits JSON, making structured tool outputs easy to consume.
    import json
    cmd = ["docker", "exec", "-i", "automotive-assembly-lab-postgres-1", "psql",
           "-U", "factory", "-d", "manufacturing", "-t", "-A", "-c",
           "SELECT COALESCE(json_agg(t),'[]'::json) FROM (" + sql + ") t"]
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "PostgreSQL command failed")
    return json.loads(result.stdout.strip())


def identifier(value: str) -> str:
    if not SAFE_ID.fullmatch(value):
        raise ValueError("Invalid identifier")
    return value


@mcp.tool()
def work_order_progress(work_order_id: str) -> list[dict[str, Any]]:
    """Read an MES work order's target, good, rejected, and latest machine counts."""
    wo = identifier(work_order_id)
    return read_sql(f"""SELECT w.work_order_id, w.target_quantity, w.status,
        p.good_quantity, p.rejected_quantity, p.last_machine_good,
        p.last_machine_rejected, p.updated_at
        FROM work_orders w LEFT JOIN work_order_progress p USING (work_order_id)
        WHERE w.work_order_id = '{wo}'""")


@mcp.tool()
def mes_batches(work_order_id: str) -> list[dict[str, Any]]:
    """List MES batches, ERP stock entry references, and posting status for a work order."""
    wo = identifier(work_order_id)
    return read_sql(f"""SELECT batch_id, quantity, mes_good_start, mes_good_end,
        status, erp_stock_entry, posted_at
        FROM erp_production_batches WHERE work_order_id = '{wo}'
        ORDER BY created_at DESC LIMIT 50""")


@mcp.tool()
def trace_serial(serial_number: str) -> list[dict[str, Any]]:
    """Trace one lab serial ID to its MES batch, work order, and ERP Stock Entry."""
    serial = identifier(serial_number)
    return read_sql(f"""SELECT serial_number, batch_id, work_order_id,
        erp_stock_entry, created_at
        FROM mes_unit_serials WHERE serial_number = '{serial}'""")


@mcp.tool()
def investigate_work_order(work_order_id: str) -> dict:
    """Run a read-only, five-agent manufacturing investigation."""
    import sys
    from pathlib import Path

    project_root = Path(__file__).resolve().parents[1]

    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from agents.orchestrator import Supervisor

    progress = work_order_progress(work_order_id)
    batches = mes_batches(work_order_id)

    if len(progress) != 1:
        return {
            "error": "Expected one MES work order",
            "rows": len(progress)
        }

    p = progress[0]

    data = {
        "work_order": work_order_id,
        "target_quantity": p["target_quantity"],
        "mes_good": p["good_quantity"],
        "mes_rejected": p["rejected_quantity"],
        "machine_good": p.get("last_machine_good"),
        "erp_manufactured_qty": None,
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
    
    # Retrieve live ERPNext data using the existing adapter.
    import json
    import os
    import subprocess

    erp_script = project_root / "erpnext" / "read_work_order.py"

    erp_result = subprocess.run(
        [sys.executable, str(erp_script), work_order_id],
        capture_output=True,
        text=True,
        timeout=30,
        env=os.environ.copy()
    )

    if erp_result.returncode == 0:
        erp = json.loads(erp_result.stdout)

        if (
            erp.get("work_order") == work_order_id
            and erp.get("produced_qty") is not None
        ):
            data["erp_manufactured_qty"] = erp["produced_qty"]
    else:
        raise RuntimeError(
            "ERPNext read failed. Check MCP process environment "
            "and ERPNext API connectivity."
        )


    report = Supervisor().run(data)

    report["source"] = "LIVE_POSTGRESQL_MES"
    report["erp_quantity_verified"] = False
    report["execution_mode"] = "READ_ONLY"

    return report



@mcp.tool()
def investigate_root_cause(work_order_id: str) -> dict:
    """Run a read-only manufacturing root-cause investigation.

    Returns evidence, possible causes, corrective actions
    and a human-review governance decision.
    """
    import json
    import subprocess
    import sys
    from pathlib import Path

    project = Path(__file__).resolve().parents[1]

    # Sprint 3 currently supports this validated work order.
    if work_order_id != "MFG-WO-2026-00003":
        return {
            "error": "Work order not yet supported",
            "requested_work_order": work_order_id
        }

    script = project / "agents" / "root_cause.py"

    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(project),
        capture_output=True,
        text=True,
        timeout=120
    )

    if result.returncode != 0:
        return {
            "error": "Root-cause investigation failed",
            "work_order": work_order_id
        }

    report_path = (
        project / "reconciliation" / "root_cause_report.json"
    )

    report = json.loads(
        report_path.read_text(encoding="utf-8-sig")
    )

    if report.get("work_order") != work_order_id:
        raise ValueError("Investigation work order mismatch")

    return report

@mcp.tool()
def investigate_integrated_work_order(work_order_id: str) -> dict:
    """Read-only live ERP/MES root-cause and transaction-level batch audit."""
    import json
    import subprocess
    import sys
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]
    script = repo / "agents" / "integrated_investigation.py"
    result = subprocess.run(
        [sys.executable, str(script), work_order_id],
        cwd=str(repo), capture_output=True, text=True, timeout=240
    )
    if result.returncode != 0:
        return {"error": "Integrated investigation failed; inspect local logs", "work_order": work_order_id}
    report = json.loads((repo / "reconciliation" / "integrated_report.json").read_text(encoding="utf-8-sig"))
    if report.get("work_order") != work_order_id:
        raise ValueError("Work order mismatch")
    return report
    
if __name__ == "__main__":
    mcp.run()  # local stdio; no network endpoint or write tools


