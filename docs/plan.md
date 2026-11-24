<!-- Phases, owners, next tasks and the session log. Replace with plan.md from the Project docs. -->
# PANDA - plan

This file says WHEN and WHO. Update it at the end of every working session.
One line per task; tick it when its tests pass and its PR is merged.

## Now

- Phase: 0 - setup and contracts
- Next task for <YOUR NAME>: <task>
- Next task for <TEAMMATE>: <task>
- Blocked on: <nothing>

## Phases

### Phase 0 - setup (day 1, both)
- [ ] Send the mentor the seven questions in spec.md section 13
- [ ] Repo hygiene: .gitattributes, .env.example, README, and a .gitignore that
      lists .env, data_plane/seed/*.csv, CLAUDE.local.md, .claude/settings.local.json
- [ ] Claude Code setup: CLAUDE.md at the repo root, .claude/settings.json;
      both commit it and check with /context that it loads
- [ ] Branch protection on main, CODEOWNERS (private repo needs GitHub Pro)
- [ ] pyproject.toml, CI (ruff, mypy, pytest)
- [ ] docker-compose.yml with Postgres, Neo4j, Cosmos emulator, MLflow server
- [ ] Decide dev container or native; stop at two hours of setup
- [ ] CSV loader that unwraps the extra quotes; load Gold, CAQH, trust matrix
- [ ] Quick tests, 15 minutes each, before building on them:
  - [ ] query Databricks Free Edition from a laptop
  - [ ] LangGraph checkpoint saves and resumes on the Cosmos emulator
  - [ ] Gemini key returns structured output
  - [ ] Firecrawl scrapes one practice website; note credits used
  - [ ] MLflow shows one trace from a toy LangGraph run (stop at one hour;
        if it fails, record the fallback in docs/decisions/)

### Phase 1 - contracts (days 1-2, both)   spec: docs/specs/01-contracts.md
- [ ] common/field_catalog.py - the 29 fields and their level
- [ ] common/states.py
- [ ] common/evidence.py, common/search_plan.py, common/finding_key.py
- [ ] common/validation_report.py + a sample report that passes contract tests

### Phase 2 - walking skeleton (day 3, <YOUR NAME>)   spec: 02-skeleton.md
- [ ] Graph with seven stub nodes and a checkpointer
- [ ] One NPI runs end to end and emits a valid (fake) report
- [ ] graph/tracing.py: one MLflow trace per case, tagged with case id,
      Gold version and trust-matrix version
Done when: teammate can read the report from their API.

### Phase 3 - evidence (days 4-6, <YOUR NAME>)   spec: 03-evidence.md
- [ ] Trust matrix loader and planner
- [ ] CAQH CSV adapter
- [ ] NPPES adapter with recorded fixtures

### Phase 4 - validation (days 6-8, <YOUR NAME>)   spec: 04-validation.md
- [ ] Normalizers and comparators for provider-level fields
- [ ] Validation node emits real findings

### Phase 5 - scoring, routing, ledger (days 8-9, <YOUR NAME>)   spec: 05-scoring.md
- [ ] Scoring engine with golden tests
- [ ] Router with guardrails
- [ ] Ledger write, terminal state last

### Phase 6 - web evidence and locations (days 10-12, <YOUR NAME>)   spec: 06-web.md
- [ ] Firecrawl adapter with LLM extraction; cache scraped pages
- [ ] Google search adapter
- [ ] Location reconciliation, by-location fields
- [ ] Neo4j loader and queries

### Phase 7 - guide-style infrastructure (days 12-14)   spec: 07-infra.md
- [ ] Case opener and dispatcher
- [ ] Service Bus between graph and EVS
- [ ] Deploy to Azure

### Phase 8 - hardening and demo (day 15, both)
- [ ] End-to-end test on 5 providers
- [ ] Evaluation: hand-check 20 providers; eval/run_eval.py logs per-field
      agreement to MLflow as one run per code version
- [ ] Check each case trace shows nodes, sources called, LLM calls and cost
- [ ] README with architecture, evaluation numbers and demo steps

### Portal track (<TEAMMATE>, in parallel)
- [ ] <Postgres models and migrations>
- [ ] <API: create audit, get case fields, record action>
- [ ] <Next.js review screen>

## Cut list (drop from the top if behind)

1. Exports
2. Expert Review stage
3. Dispatcher leases
4. Service Bus transport (call adapters in-process instead)

Never cut: the fields agreed with the mentor, checkpoints, tests.

## Risks

| Risk | Sign it is happening | What we do |
|---|---|---|
| Azure credit runs out | credit below $40 | stop cloud resources, demo locally |
| 16 fields have no source rules | mentor has not answered by day 3 | build the 13 covered fields first, write our own rules for the rest |
| Firecrawl or Gemini quota runs out | errors or slow responses | cache pages, test on 5 providers not 1000 |
| Portal track falls behind | no review screen by day 10 | show the report in a simple table |

## Session log (keep the last 10 lines)

- <DATE> <who>: <what finished, what is next, anything surprising>