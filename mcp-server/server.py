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


if __name__ == "__main__":
    mcp.run()  # local stdio; no network endpoint or write tools


