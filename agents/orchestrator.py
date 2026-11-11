import json
import sys
from decimal import Decimal
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from reconciliation.agent import reconcile, number


def finding(code, severity, message, owner):
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "owner": owner
    }


class ERPAnalyst:
    role = "ERP Analyst"

    def run(self, data):
        target = number(data["target_quantity"], "target_quantity")
        manufactured = data.get("erp_manufactured_qty")
        return {
            "agent": self.role,
            "status": "COMPLETE",
            "evidence": {
                "work_order": data["work_order"],
                "target_quantity": str(target),
                "manufactured_quantity": (
                    str(number(manufactured, "erp_manufactured_qty"))
                    if manufactured is not None else None
                )
            },
            "findings": []
        }


class MESAnalyst:
    role = "MES Analyst"

    def run(self, data):
        batches = data["batches"]
        posted = [
            b for b in batches
            if b.get("status", "").upper() == "POSTED"
            and b.get("erp_stock_entry")
        ]
        return {
            "agent": self.role,
            "status": "COMPLETE",
            "evidence": {
                "mes_good": str(number(data["mes_good"], "mes_good")),
                "batch_count": len(batches),
                "batches_with_erp_reference": len(posted)
            },
            "findings": []
        }


class QualityAnalyst:
    role = "Quality Analyst"

    def run(self, data):
        good = number(data["mes_good"], "mes_good")
        rejected = number(data["mes_rejected"], "mes_rejected")
        total = good + rejected
        yield_pct = (
            (good / total * Decimal("100"))
            if total else Decimal("0")
        )

        issues = []
        if total == 0:
            issues.append(finding(
                "NO_PRODUCTION_DATA", "INFO",
                "No production quantity available.",
                self.role
            ))
        if total and yield_pct < 95:
            issues.append(finding(
                "LOW_YIELD", "MEDIUM",
                f"Calculated yield is {yield_pct:.2f}%.",
                self.role
            ))

        return {
            "agent": self.role,
            "status": "COMPLETE",
            "evidence": {
                "rejected_quantity": str(rejected),
                "calculated_yield_percent": f"{yield_pct:.2f}"
            },
            "findings": issues
        }


class ReconciliationAgent:
    role = "Reconciliation Agent"

    def run(self, data):
        result = reconcile(data)
        return {
            "agent": self.role,
            "status": "COMPLETE",
            "evidence": result["summary"],
            "findings": [
                finding(
                    x["code"], x["severity"],
                    x["detail"], self.role
                )
                for x in result["findings"]
            ]
        }


class GovernanceAgent:
    role = "Governance Agent"

    def run(self, reports):
        all_findings = [
            finding
            for report in reports
            for finding in report["findings"]
        ]
        high = [
            f for f in all_findings
            if f["severity"] == "HIGH"
        ]
        return {
            "agent": self.role,
            "status": "COMPLETE",
            "decision": (
                "HUMAN_REVIEW_REQUIRED" if high
                else "READ_ONLY_REVIEW_COMPLETE"
            ),
            "write_approved": False,
            "erp_write_performed": False,
            "reason": (
                f"{len(high)} high-severity findings require review."
                if high else
                "No high-severity findings identified."
            )
        }


class Supervisor:
    role = "Manufacturing AI Supervisor"

    def __init__(self):
        self.specialists = [
            ERPAnalyst(),
            MESAnalyst(),
            QualityAnalyst(),
            ReconciliationAgent()
        ]
        self.governance = GovernanceAgent()

    def run(self, data):
        reports = [agent.run(data) for agent in self.specialists]
        decision = self.governance.run(reports)
        return {
            "system": "Factory AI Multi-Agent Orchestrator",
            "work_order": data["work_order"],
            "executed_at_utc": datetime.now(timezone.utc).isoformat(),
            "execution_mode": "READ_ONLY",
            "source": "LOCAL_JSON_FIXTURE",
            "agents": reports,
            "governance": decision,
            "supervisor_summary": {
                "agents_completed": len(reports) + 1,
                "total_findings": sum(
                    len(r["findings"]) for r in reports
                ),
                "next_action": decision["decision"]
            }
        }


def main():
    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: py agents/orchestrator.py input.json"
        )
    data = json.loads(
        Path(sys.argv[1]).read_text(encoding="utf-8-sig")
    )
    report = Supervisor().run(data)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
