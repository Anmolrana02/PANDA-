#!/usr/bin/env python3
"""Create the PANDA folder and file layout from docs/architecture.md.

Every file gets a short comment at the top saying what it is for. The script
never overwrites a file that already exists, so it is safe to run again, and
safe to run after you have copied CLAUDE.md, spec.md and plan.md into the repo.

Usage (from the repo root):
    python scaffold_panda.py                 # create everything except web/ and .devcontainer/
    python scaffold_panda.py --dry-run       # only print what would be created
    python scaffold_panda.py --with-web      # also add the Next.js review files
    python scaffold_panda.py --with-devcontainer
    python scaffold_panda.py --root path/to/repo

Not created on purpose:
    - the four CSVs (copy them into data_plane/seed/ yourself; they are gitignored)
    - portal_plane/api/migrations/ (run `alembic init` there; it refuses a non-empty folder)
    - Next.js base files (run create-next-app first, then this script with --with-web)
    - .claude/settings.local.json and CLAUDE.local.md (personal, created when needed)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

HAND = (
    "HAND-WRITTEN: core logic written by the owner. Claude Code may propose an "
    "approach and tests, but does not write this file."
)

# ---------------------------------------------------------------------------
# Every file in the layout: (path, what it does)
# ---------------------------------------------------------------------------

ROOT_FILES = [
    ("CLAUDE.md", "Rules Claude Code reads at the start of every session. Replace with the full CLAUDE.md from the Project docs."),
    ("README.md", "Project overview, architecture, evaluation numbers and demo steps."),
    (".gitignore", "Files git must never track: secrets, seed CSVs, personal Claude files, caches."),
    (".gitattributes", "Forces one line-ending style so Windows and Mac produce the same files."),
    (".env.example", "Names of every secret the project needs, with no real values. Copy to .env and fill in."),
    ("docker-compose.yml", "Local services: Postgres, Neo4j, Cosmos DB emulator, Service Bus emulator, MLflow."),
    ("pyproject.toml", "Python dependencies and settings for ruff, mypy and pytest (managed with uv)."),
]

CLAUDE_FILES = [
    (".claude/settings.json", "Shared Claude Code permissions: what Claude may run and read."),
    (".claude/rules/.gitkeep", "Extra Claude rules that load only for matching folders. Empty for now."),
]

GITHUB_FILES = [
    (".github/CODEOWNERS", "Who must review changes to which folder."),
    (".github/pull_request_template.md", "Checklist shown on every new pull request."),
    (".github/workflows/ci.yml", "CI: ruff, mypy and pytest on every pull request."),
]

DOCS_FILES = [
    ("docs/spec.md", "What the whole system must do. Replace with spec.md from the Project docs."),
    ("docs/plan.md", "Phases, owners, next tasks and the session log. Replace with plan.md from the Project docs."),
    ("docs/architecture.md", "The full file tree. Replace with architecture.md from the Project docs."),
    ("docs/specs/01-contracts.md", "Feature spec for the shared contracts in common/. Fill in from feature-spec-template.md."),
    ("docs/specs/02-skeleton.md", "Feature spec for the walking skeleton: seven stub nodes, one NPI end to end."),
    ("docs/decisions/001-where-gold-lives.md", "Decision record: where the Gold record and trust matrix are stored (Databricks or local)."),
]

COMMON_FILES = [
    ("common/field_catalog.py", "The 29 audit fields: name, provider-level or location-level, and which Gold columns hold each one."),
    ("common/states.py", "State names for the agent case, the dispatcher and the portal, and which transitions are allowed."),
    ("common/evidence.py", "Evidence Assertion (what one source said, with raw_value, normalized_value, source, URL, time) and Evidence Bundle."),
    ("common/search_plan.py", "Search Plan: which sources to ask for which fields, built by the planner from the trust matrix."),
    ("common/validation_report.py", "The schema-7 validation report the agent writes and the portal reads."),
    ("common/finding_key.py", "FindingKey = (field_name, representation, location_key): the unique id of one finding."),
    ("common/tests/test_contracts.py", "Tests that every contract validates good examples and rejects bad ones, including a sample report."),
]

AGENT_FILES = [
    # case opener
    ("agent_plane/case_opener/app.py", "HTTP entry point: receives a request to open an audit case for one NPI."),
    ("agent_plane/case_opener/service.py", "Checks the NPI, pins the Gold and trust-matrix versions, and creates the case in state CREATED."),
    ("agent_plane/case_opener/dispatcher.py", "Hands a new case to the agent graph and retries if the hand-off fails."),
    # graph
    ("agent_plane/graph/langgraph_flow.py", "Builds the LangGraph: the seven nodes and the edges between them."),
    ("agent_plane/graph/state.py", "The state object passed from node to node. Each node only adds to it."),
    ("agent_plane/graph/run_case_graph.py", "Runs the graph for one case, resuming from the last checkpoint if there is one."),
    ("agent_plane/graph/checkpointer.py", "Saves a checkpoint after every node to Cosmos DB, so a case can resume after a crash."),
    ("agent_plane/graph/tracing.py", "MLflow setup: turns on autolog once and tags each case trace with case id, Gold version and trust-matrix version."),
    ("agent_plane/graph/eva/eva_planner.py", "Node 1, plan evidence: reads the trust matrix and builds the Search Plan for the case."),
    ("agent_plane/graph/eva/evidence_agent.py", "Node 2, collect evidence: sends the Search Plan to EVS and gathers the Evidence Bundles."),
    ("agent_plane/graph/validation/validation_agent.py", "Node 3, validate: compares each Gold value with the evidence and produces one finding per field."),
    ("agent_plane/graph/validation/office_audit.py", "Matches Gold practice locations to locations found in evidence, so by-location fields compare like with like."),
    ("agent_plane/graph/validation/normalizers.py", "Turns raw values into a standard form (phones, addresses, names, degrees) before comparing.\n\n" + HAND),
    ("agent_plane/graph/validation/comparators.py", "Decides whether a Gold value and an evidence value match, for each kind of field.\n\n" + HAND),
    ("agent_plane/graph/scoring/acl_engine.py", "Node 4, score: the fixed confidence formula. Weights and trust scores come from the trust matrix, never from code or an LLM.\n\n" + HAND),
    ("agent_plane/graph/scoring/confidence_policy.json", "Case score bands and deductions only. Weights and trust scores stay in the trust matrix."),
    ("agent_plane/graph/routing/router.py", "Node 5, route: turns scores into the next action (auto-confirm, review or escalate).\n\n" + HAND),
    ("agent_plane/graph/action/action_staging.py", "Turns routed findings into review tasks for the portal."),
    ("agent_plane/graph/action/outreach.py", "Node 7, outreach: creates the reviewer task or email and sets the final case state."),
    # evs
    ("agent_plane/evs/worker.py", "EVS entry point: receives evidence requests. EVS is the only part of the system allowed to call the internet."),
    ("agent_plane/evs/retrieve_core.py", "Picks the right adapter for each request, handles timeouts and errors, and returns Evidence Assertions."),
    ("agent_plane/evs/llm_extract.py", "Uses Gemini to turn scraped page text into structured values, validated with Pydantic. Page text is untrusted data."),
    ("agent_plane/evs/adapters/base.py", "The interface every source adapter follows."),
    ("agent_plane/evs/adapters/caqh.py", "Adapter for trust-matrix source \"CAQH\": reads caqh_.csv."),
    ("agent_plane/evs/adapters/nppes.py", "Adapter for trust-matrix source \"NPPES\": queries the public NPPES registry."),
    ("agent_plane/evs/adapters/firecrawl_web.py", "Adapter for trust-matrix source \"Provider Website\": scrapes with Firecrawl, then calls llm_extract."),
    ("agent_plane/evs/adapters/google_search.py", "Adapter for trust-matrix source \"Google Searches\": queries a search API (still to choose)."),
    # ledger
    ("agent_plane/ledger/ecc_writer.py", "Builds the validation report rows from the findings, scores and routes."),
    ("agent_plane/ledger/ledger_writer.py", "Node 6, write ledger: saves the report, writing the completion marker last."),
    # eval
    ("agent_plane/eval/run_eval.py", "Runs the agent on the hand-checked providers and logs per-field agreement to MLflow."),
    # tests
    ("agent_plane/tests/fixtures/.gitkeep", "Recorded source responses, so tests never call live services."),
    ("agent_plane/tests/test_planner.py", "Tests for eva_planner: the right sources are planned for each field."),
    ("agent_plane/tests/test_adapters.py", "Tests for the source adapters, using recorded fixtures."),
    ("agent_plane/tests/test_validation.py", "Tests for normalizers, comparators and the validation node."),
    ("agent_plane/tests/test_scoring.py", "Golden tests for the scoring formula: same input and policy always give the same score."),
    ("agent_plane/tests/test_router.py", "Tests for the router: each score band leads to the right action."),
    ("agent_plane/tests/test_graph_end_to_end.py", "One NPI runs through all seven nodes and produces a valid report."),
]

PORTAL_API_FILES = [
    ("portal_plane/api/main.py", "FastAPI app: creates the app and registers the endpoints."),
    ("portal_plane/api/models.py", "Postgres tables: audit, batch, case and reviewer action."),
    ("portal_plane/api/endpoints/audits.py", "Endpoints to create an audit and list work for reviewers."),
    ("portal_plane/api/endpoints/cases.py", "Endpoints to get a case's fields and record a reviewer decision."),
    ("portal_plane/api/services/audit_service.py", "Creates audits and cases, and asks the case opener to start them."),
    ("portal_plane/api/services/validation_report_service.py", "Reads the agent's validation report for a case."),
    ("portal_plane/api/services/review_findings.py", "Turns a validation report into rows for the review screen."),
    ("portal_plane/api/services/field_outcome.py", "Which reviewer decisions are allowed for each finding."),
    ("portal_plane/api/services/rationale_service.py", "Uses Gemini to write a plain-language explanation of a finding for the reviewer."),
    ("portal_plane/tests/.gitkeep", "Tests for the portal API."),
]

WEB_FILES = [
    ("portal_plane/web/app/page.tsx", "Home page of the review app."),
    ("portal_plane/web/app/review/[batchId]/page.tsx", "Review page for one batch of cases."),
    ("portal_plane/web/app/api/v1/[...path]/route.ts", "Backend-for-frontend: forwards browser calls to the FastAPI service."),
    ("portal_plane/web/components/review-batch/BatchCaseWorkspace.tsx", "Main review workspace: list of cases in a batch plus the selected case."),
    ("portal_plane/web/components/review-batch/AuditCaseReviewTable.tsx", "Table of findings for one case, with a decision control per row."),
    ("portal_plane/web/components/review-batch/CaseDetailEvidencePanel.tsx", "Side panel showing the evidence and sources behind a finding."),
    ("portal_plane/web/lib/api.ts", "Small typed client for calling the API from the web app."),
]

DATA_FILES = [
    ("data_plane/seed/load_seed.py", "Unwraps the extra quotes in the four CSVs and loads Gold, CAQH and the trust matrix into the stores."),
    ("data_plane/stores/directory_store.py", "Reads the Gold record and the trust matrix. Read-only: nothing here writes to Gold."),
    ("data_plane/stores/report_store.py", "Saves and reads validation reports."),
    ("data_plane/stores/cosmos_store.py", "Saves and reads agent case state in Cosmos DB."),
    ("data_plane/stores/service_bus.py", "Sends and receives messages on Service Bus (evidence requests, ledger writes)."),
    ("data_plane/kg/schema.cypher", "Neo4j schema: provider, office and source nodes, and how they link."),
    ("data_plane/kg/loader.py", "Loads providers, offices and sources into Neo4j."),
    ("data_plane/kg/queries.py", "Cypher queries the agents use, such as finding other providers at the same office."),
]

INFRA_FILES = [
    ("infra/docker/agent.Dockerfile", "Image for the agent graph and case opener."),
    ("infra/docker/evs.Dockerfile", "Image for EVS, the only service with internet access."),
    ("infra/docker/api.Dockerfile", "Image for the FastAPI portal service."),
    ("infra/docker/web.Dockerfile", "Image for the Next.js review app."),
    ("infra/azure/deploy.sh", "Deploys the services to Azure."),
]

DEVCONTAINER_FILES = [
    (".devcontainer/devcontainer.json", "Dev container: the same Python and tools for both developers, Windows and Mac."),
]

# Folders that hold Python code and need an __init__.py
PACKAGES = [
    "common", "common/tests",
    "agent_plane", "agent_plane/case_opener", "agent_plane/graph",
    "agent_plane/graph/eva", "agent_plane/graph/validation", "agent_plane/graph/scoring",
    "agent_plane/graph/routing", "agent_plane/graph/action",
    "agent_plane/evs", "agent_plane/evs/adapters", "agent_plane/ledger",
    "agent_plane/eval", "agent_plane/tests",
    "portal_plane", "portal_plane/api", "portal_plane/api/endpoints",
    "portal_plane/api/services", "portal_plane/tests",
    "data_plane", "data_plane/seed", "data_plane/stores", "data_plane/kg",
]

# ---------------------------------------------------------------------------
# Real content for files where a bare comment would be wrong or useless
# ---------------------------------------------------------------------------

SPECIAL_CONTENT = {
    ".gitignore": """\
# Files git must never track: secrets, seed CSVs, personal Claude files, caches.

# secrets
.env
.env.local

# seed data (may be real internal data - never commit)
data_plane/seed/*.csv

# personal Claude Code files
CLAUDE.local.md
.claude/settings.local.json

# Python
__pycache__/
*.pyc
.venv/
.pytest_cache/
.mypy_cache/
.ruff_cache/

# Node / Next.js
node_modules/
.next/

# MLflow local runs
mlruns/
mlartifacts/

# OS / editor
.DS_Store
Thumbs.db
.idea/
.vscode/
""",
    ".gitattributes": """\
# Forces one line-ending style so Windows and Mac produce the same files.
* text=auto eol=lf
*.sh text eol=lf
*.png binary
*.pdf binary
""",
    ".env.example": """\
# Names of every secret the project needs, with no real values.
# Copy this file to .env and fill in. Never commit .env.

# LLM
GEMINI_API_KEY=

# Scraping and search
FIRECRAWL_API_KEY=
SEARCH_API_KEY=

# Portal database
DATABASE_URL=postgresql://panda:panda@localhost:5432/panda

# Cosmos DB (local emulator values go here for development)
COSMOS_ENDPOINT=
COSMOS_KEY=

# Service Bus
SERVICE_BUS_CONNECTION_STRING=

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=

# Databricks
DATABRICKS_HOST=
DATABRICKS_HTTP_PATH=
DATABRICKS_TOKEN=

# MLflow
MLFLOW_TRACKING_URI=http://localhost:5000
""",
    "docker-compose.yml": """\
# Local services: Postgres, Neo4j, Cosmos DB emulator, Service Bus emulator, MLflow.
# Add each service here during Phase 0. Start with: docker compose up -d
services: {}
""",
    "pyproject.toml": """\
# Python dependencies and settings for ruff, mypy and pytest (managed with uv).
# Add dependencies with: uv add <package>

[project]
name = "panda"
version = "0.1.0"
description = "Agentic audit of a health insurer's provider directory"
requires-python = ">=3.12"
dependencies = []

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.mypy]
python_version = "3.12"
strict = true

[tool.pytest.ini_options]
markers = ["live: calls a real external service (skipped by default)"]
addopts = "-m 'not live'"
""",
    ".claude/settings.json": json.dumps(
        {
            "$schema": "https://json.schemastore.org/claude-code-settings.json",
            "permissions": {
                "allow": [
                    "Bash(uv run pytest)",
                    "Bash(uv run pytest *)",
                    "Bash(uv run ruff *)",
                    "Bash(uv run mypy *)",
                ],
                "ask": ["Bash(git push *)", "Bash(docker compose down *)"],
                "deny": [
                    "Read(./.env)",
                    "Read(./.env.local)",
                    "Read(./data_plane/seed/*.csv)",
                ],
            },
        },
        indent=2,
    )
    + "\n",
    ".github/CODEOWNERS": """\
# Who must review changes to which folder.
# Replace the usernames with your GitHub usernames, then uncomment.

# /common/        @your-username @teammate-username
# /agent_plane/   @your-username
# /portal_plane/  @teammate-username
# /infra/         @teammate-username
# /data_plane/    @your-username @teammate-username
""",
    ".github/pull_request_template.md": """\
<!-- Checklist shown on every new pull request. -->

## What this changes

## Feature spec
docs/specs/

## Checklist
- [ ] Tests written first and passing
- [ ] ruff, mypy and pytest pass
- [ ] No secrets, no seed CSVs
- [ ] common/ changed? Both owners agreed
- [ ] Task ticked in docs/plan.md
""",
    ".github/workflows/ci.yml": """\
# CI: ruff, mypy and pytest on every pull request.
# Only runs manually for now. When the first tests exist, add:
#   pull_request:
#     branches: [main]
name: ci

on:
  workflow_dispatch:

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run mypy .
      - run: uv run pytest
""",
    "agent_plane/graph/scoring/confidence_policy.json": json.dumps(
        {
            "_comment": "Case score bands and deductions only. Weights and trust scores stay in the trust matrix. Fill in once the mentor confirms the bands.",
            "case_bands": {},
            "deductions": [],
        },
        indent=2,
    )
    + "\n",
    ".devcontainer/devcontainer.json": json.dumps(
        {
            "_comment": "Dev container: the same Python and tools for both developers, Windows and Mac.",
            "name": "panda",
            "image": "mcr.microsoft.com/devcontainers/python:3.12",
        },
        indent=2,
    )
    + "\n",
}

# ---------------------------------------------------------------------------
# Comment style per file type
# ---------------------------------------------------------------------------


def comment_for(path: str, text: str) -> str:
    name = Path(path).name
    suffix = Path(path).suffix

    if name == ".gitkeep":
        return f"# {text}\n"
    if suffix == ".py":
        return f'"""{text}\n"""\n'
    if suffix == ".md":
        return f"<!-- {text} -->\n"
    if suffix in {".ts", ".tsx"}:
        lines = "".join(f"// {line}\n" for line in text.splitlines())
        if name == "route.ts":
            return lines + "\nexport {};\n"
        if suffix == ".tsx":
            component = Path(path).stem if Path(path).stem != "page" else "Page"
            return lines + f"\nexport default function {component}() {{\n  return null;\n}}\n"
        return lines + "\nexport {};\n"
    if suffix == ".cypher":
        return f"// {text}\n"
    if suffix == ".sh":
        return f"#!/usr/bin/env bash\n# {text}\nset -euo pipefail\n"
    if suffix == ".json":
        return json.dumps({"_comment": text}, indent=2) + "\n"
    # Dockerfile, yml, toml, CODEOWNERS and anything else that uses #
    return "".join(f"# {line}\n" if line else "#\n" for line in text.splitlines())


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the PANDA repo layout.")
    parser.add_argument("--root", default=".", help="repo root (default: current folder)")
    parser.add_argument("--dry-run", action="store_true", help="print only, create nothing")
    parser.add_argument("--with-web", action="store_true", help="also create the Next.js review files")
    parser.add_argument("--with-devcontainer", action="store_true", help="also create .devcontainer/")
    args = parser.parse_args()

    root = Path(args.root).resolve()

    files = (
        ROOT_FILES + CLAUDE_FILES + GITHUB_FILES + DOCS_FILES + COMMON_FILES
        + AGENT_FILES + PORTAL_API_FILES + DATA_FILES + INFRA_FILES
    )
    if args.with_web:
        files += WEB_FILES
    if args.with_devcontainer:
        files += DEVCONTAINER_FILES

    # __init__.py for every Python package
    files += [(f"{pkg}/__init__.py", "") for pkg in PACKAGES]

    created, skipped = 0, 0
    for rel, text in files:
        target = root / rel
        if target.exists():
            skipped += 1
            print(f"  skip    {rel}  (already exists)")
            continue
        content = SPECIAL_CONTENT.get(rel)
        if content is None:
            content = comment_for(rel, text) if text else ""
        if not args.dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
        created += 1
        print(f"  create  {rel}")

    print(f"\n{'Would create' if args.dry_run else 'Created'} {created} files, skipped {skipped}.")
    print("\nNext steps:")
    print("  1. Replace CLAUDE.md, docs/spec.md, docs/plan.md, docs/architecture.md with the Project docs versions.")
    print("  2. Copy the four CSVs into data_plane/seed/ (they are gitignored).")
    print("  3. When the portal starts: `alembic init portal_plane/api/migrations`.")
    if not args.with_web:
        print("  4. For the review screen: `npx create-next-app@latest portal_plane/web`,")
        print("     then run this script again with --with-web.")


if __name__ == "__main__":
    main()
