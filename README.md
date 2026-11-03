# Automotive Assembly | ERP-MES-AI Integration Lab

An industrial digitalisation portfolio project demonstrating integration between manufacturing ERP, shop-floor telemetry, an MES database and an AI assistant using the Model Context Protocol (MCP).

## Architecture

```text
ERPNext (Manufacturing ERP)
          |
          | REST API
          v
Node-RED (Integration & Automation)
          ^
          | MQTT
          |
Simulated Production Equipment
          |
          v
PostgreSQL (MES Production & Traceability)
          |
          | FastMCP Python Server
          v
Claude Desktop (AI Manufacturing Assistant)
```

The diagram is conceptual. ERPNext transactions, MQTT telemetry and MES persistence use distinct integration flows.

## Technology Stack

- ERP: ERPNext v16
- Integration: Node-RED
- Telemetry: MQTT
- MES: PostgreSQL
- MCP server: Python, FastMCP
- AI client: Claude Desktop
- Infrastructure: Docker

## Demonstrated Capabilities

- Manufacturing work order retrieval
- Shop-floor telemetry ingestion
- MES production tracking
- Manufacturing Stock Entry creation through ERPNext
- Serial-to-batch-to-work-order traceability
- ERPNext Stock Entry reference linkage
- AI-assisted queries using MCP

## MCP Tools

| Tool | Purpose |
|---|---|
| work_order_progress | Retrieve MES work order progress |
| mes_batches | Retrieve batch quantities and ERP posting status |
| trace_serial | Trace an individual serial to its production and ERP references |

## Verified Demonstration

Work order: MFG-WO-2026-00003

Product: AAL-BRACKET-001

Example trace:

Serial -> MES Batch -> Work Order -> ERPNext Stock Entry

AAL-BRACKET-001-000826
-> MES-MFG-WO-2026-00003-826-835
-> MFG-WO-2026-00003
-> MAT-STE-2026-00004

This verifies traceability for the example serial, not automatic reconciliation of every MES production record.

## Repository Contents

- `mcp-server/server.py` - MCP tools
- `node-red/flows.json` - Node-RED flow export
- `database/schema.sql` - PostgreSQL schema-only export
- `docs/` - Architecture and operating documentation
- `tests/` - Planned integration tests

## Known Limitations

- Production telemetry is simulated.
- MES production counts may exceed the ERP work order target.
- Machine, MES and ERP quantities require reconciliation.
- Automated duplicate prevention and production limits remain to be implemented.
- Deployment instructions and automated tests are still being prepared.

## Security

This repository must not contain credentials, API secrets,
real database backups or private production records.

Use environment variables and local configuration files for
development secrets.

## Project Status

Working prototype. MCP tool connectivity and an example
serial-to-ERP trace have been verified.

Not intended for production deployment without additional
testing, security controls and operational safeguards.
