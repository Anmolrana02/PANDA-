<!-- The full file tree. Replace with architecture.md from the Project docs. -->
# PANDA - architecture

Last updated: 2026-11-16. Save this file as `docs/architecture.md`.

This is the target layout. Do not create every file on day one: create a file
when its task in `docs/plan.md` starts. `CLAUDE.md` holds a shorter copy of
this tree; when a top-level folder changes, update both.

## The three planes

| Plane | What it does | Folder | Owner |
|---|---|---|---|
| Portal plane | Review screen and the API behind it; stores human decisions | `portal_plane/` | <TEAMMATE> |
| Agent plane | Opens a case, collects evidence, validates, scores, routes, writes the report | `agent_plane/` | <YOUR NAME> |
| Data plane | Loaders and the small pieces of code that talk to each database | `data_plane/` | shared |

`common/` sits outside the planes because both the portal and the agents
import it. It holds the contracts the two of you agree on.

## Agent graph

One case is one provider NPI. The nodes run in this order, with a checkpoint
after each one:

1. plan evidence - read the trust matrix, decide which sources may be asked
2. collect evidence - call the source adapters through EVS
3. validate - compare the Gold record with the evidence
4. score - apply the confidence formula (no LLM)
5. route - turn the score into the next action
6. write ledger - save the validation report
7. outreach - create the reviewer task or email, then set the final state

## Stores

| Store | Holds | Local | Cloud |
|---|---|---|---|
| Cosmos DB | agent case state, checkpoints | emulator | Azure |
| PostgreSQL | portal audits, cases, reviewer actions | container | Azure |
| Databricks | Gold record, trust matrix, validation reports | to decide | to decide |
| Service Bus | evidence requests, ledger writes | emulator | Azure |
| Neo4j | provider - office - source graph | container | to decide |
| MLflow | case traces, evaluation runs | container | to decide |

## File tree

```
panda/
├── CLAUDE.md                           # rules Claude Code reads every session
├── CLAUDE.local.md                     # your private notes for Claude (gitignored, optional)
├── README.md
├── .gitignore                          # .env, seed CSVs, CLAUDE.local.md, local settings
├── .gitattributes                      # forces one line-ending style (Windows + Mac)
├── .env.example                        # names of the secrets, no real values
├── docker-compose.yml                  # local Postgres, Neo4j, Cosmos, Service Bus, MLflow
├── pyproject.toml                      # Python dependencies and tool settings
│
├── .claude/                            # Claude Code configuration ONLY
│   ├── settings.json                   # shared permissions: what Claude may run and read
│   ├── settings.local.json             # your personal overrides (gitignored, auto-created)
│   └── rules/                          # extra rules that load only for matching folders
│
├── .devcontainer/                      # only if you choose the dev container route
│   └── devcontainer.json
│
├── .github/
│   ├── CODEOWNERS                      # who must review which folder
│   ├── pull_request_template.md
│   └── workflows/
│       └── ci.yml                      # ruff, mypy, pytest on every PR
│
├── docs/                               # project documents (never inside .claude/)
│   ├── spec.md                         # what the system must do
│   ├── plan.md                         # phases, owners, session log
│   ├── architecture.md                 # this file
│   ├── specs/                          # one feature spec per feature
│   │   ├── 01-contracts.md
│   │   └── 02-skeleton.md
│   └── decisions/                      # one short file per architecture decision
│       └── 001-where-gold-lives.md
│
├── common/                             # SHARED CONTRACTS (both owners)
│   ├── field_catalog.py                # the 29 fields: level, Gold columns
│   ├── states.py                       # agent case, dispatch and portal states
│   ├── evidence.py                     # Evidence Assertion, Evidence Bundle
│   ├── search_plan.py
│   ├── validation_report.py            # schema-7 report
│   ├── finding_key.py                  # (field_name, representation, location_key)
│   └── tests/
│       └── test_contracts.py
│
├── agent_plane/                        # owner: <YOUR NAME>
│   ├── case_opener/
│   │   ├── app.py                      # HTTP entry: open a case
│   │   ├── service.py                  # validate NPI, pin versions, create case
│   │   └── dispatcher.py               # hand the case to the graph, retry
│   ├── graph/
│   │   ├── langgraph_flow.py           # nodes and edges
│   │   ├── state.py                    # the state object passed between nodes
│   │   ├── run_case_graph.py           # run one case
│   │   ├── checkpointer.py             # Cosmos DB checkpoints
│   │   ├── tracing.py                  # MLflow setup: autolog once, tags per case
│   │   ├── eva/
│   │   │   ├── eva_planner.py          # trust matrix -> Search Plan
│   │   │   └── evidence_agent.py       # run the plan, collect bundles
│   │   ├── validation/
│   │   │   ├── validation_agent.py     # compare Gold with evidence
│   │   │   ├── office_audit.py         # location reconciliation
│   │   │   ├── normalizers.py          # hand-written
│   │   │   └── comparators.py          # hand-written
│   │   ├── scoring/
│   │   │   ├── acl_engine.py           # hand-written: weights come from the trust matrix
│   │   │   └── confidence_policy.json  # case bands and deductions only
│   │   ├── routing/
│   │   │   └── router.py               # hand-written: score -> next action
│   │   └── action/
│   │       ├── action_staging.py       # turn findings into review tasks
│   │       └── outreach.py             # reviewer task, email, terminal state
│   ├── evs/                            # the only code allowed to call the internet
│   │   ├── worker.py                   # receives evidence requests
│   │   ├── retrieve_core.py            # picks the adapter, handles errors
│   │   ├── llm_extract.py              # Gemini: page text -> structured values
│   │   └── adapters/
│   │       ├── base.py                 # the shape every adapter follows
│   │       ├── caqh.py                 # source "CAQH"
│   │       ├── nppes.py                # source "NPPES"
│   │       ├── firecrawl_web.py        # source "Provider Website"
│   │       └── google_search.py        # source "Google Searches"
│   ├── ledger/
│   │   ├── ecc_writer.py               # build report rows
│   │   └── ledger_writer.py            # save them, completion marker last
│   ├── eval/
│   │   └── run_eval.py                 # run the hand-checked set, log agreement to MLflow
│   └── tests/
│       ├── fixtures/                   # recorded source responses
│       ├── test_planner.py
│       ├── test_adapters.py
│       ├── test_validation.py
│       ├── test_scoring.py
│       ├── test_router.py
│       └── test_graph_end_to_end.py
│
├── portal_plane/                       # owner: <TEAMMATE>
│   ├── api/                            # FastAPI
│   │   ├── main.py
│   │   ├── models.py                   # Postgres tables: audit, batch, case, action
│   │   ├── migrations/                 # Alembic
│   │   ├── endpoints/
│   │   │   ├── audits.py               # create audit, list work
│   │   │   └── cases.py                # get fields, record action
│   │   └── services/
│   │       ├── audit_service.py
│   │       ├── validation_report_service.py  # read the agent's report
│   │       ├── review_findings.py      # report -> rows for the screen
│   │       ├── field_outcome.py        # which decisions are allowed
│   │       └── rationale_service.py    # Gemini: reviewer-facing explanation
│   ├── web/                            # Next.js (setup command creates the base files)
│   │   ├── package.json
│   │   ├── app/
│   │   │   ├── page.tsx                # home
│   │   │   ├── review/[batchId]/page.tsx
│   │   │   └── api/v1/[...path]/route.ts     # BFF: forwards calls to FastAPI
│   │   ├── components/
│   │   │   └── review-batch/
│   │   │       ├── BatchCaseWorkspace.tsx
│   │   │       ├── AuditCaseReviewTable.tsx
│   │   │       └── CaseDetailEvidencePanel.tsx
│   │   └── lib/
│   │       └── api.ts
│   └── tests/
│
├── data_plane/                         # shared
│   ├── seed/
│   │   ├── load_seed.py                # unwrap the extra quotes, load into the stores
│   │   ├── gold_.csv                   # gitignored
│   │   ├── caqh_.csv                   # gitignored
│   │   ├── trust.csv                   # gitignored
│   │   └── validation.csv              # gitignored
│   ├── stores/                         # one file per database; nothing else talks to a DB
│   │   ├── directory_store.py          # Gold record + trust matrix
│   │   ├── report_store.py             # validation reports
│   │   ├── cosmos_store.py             # agent case state
│   │   └── service_bus.py              # send and receive messages
│   └── kg/                             # Neo4j
│       ├── schema.cypher               # provider, office, source nodes and links
│       ├── loader.py
│       └── queries.py
│
└── infra/                              # owner: <TEAMMATE>
    ├── docker/
    │   ├── agent.Dockerfile
    │   ├── evs.Dockerfile
    │   ├── api.Dockerfile
    │   └── web.Dockerfile
    └── azure/
        └── deploy.sh
```

## Notes

- Every Python folder also needs an `__init__.py`; they are left out of the
  tree to keep it readable.
- File names follow the mentor's guide where it names them (`eva_planner.py`,
  `acl_engine.py`, `BatchCaseWorkspace.tsx`). The rest can be renamed.
- The four files marked hand-written are core logic written by the owner;
  Claude Code proposes an approach and tests for them but does not write them.
- Only code in `agent_plane/evs/` may call the internet. Validation, scoring
  and routing never use LLM output.