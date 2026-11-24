<!-- Feature spec for the shared contracts in common/. Fill in from feature-spec-template.md. -->
# Feature spec: 01 - contracts

Owner: Anmol Rana + Harsh Giri (common/ is shared). Phase in plan.md: 1.
Status: in progress. Built one file at a time; each section below is one file.

## Goal

Give the agent graph, the case opener and the portal one shared, tested
definition of every status a case, dispatch job or batch can have, and of
which moves between statuses are allowed.

---

## Part 1 - common/states.py

### Inputs and outputs

- Input: a current status and a proposed next status.
- Output: True/False for "is this move allowed", or an InvalidTransition error.
- Statuses are Python StrEnums, so they save to JSON, Cosmos and Postgres
  as plain text, e.g. AgentCaseState.SCORING is stored as "SCORING".

### Statuses and allowed moves

Agent case (one NPI investigation):

    CREATED -> PLANNED -> RETRIEVING -> VALIDATING -> SCORING -> ROUTING
    ROUTING -> CLOSED          (safe to auto-confirm)
    ROUTING -> HITL_PENDING    (a human must review)
    any non-final status -> CANCELLED   (unrecoverable error)
    Final: CLOSED, HITL_PENDING, CANCELLED

Dispatch job (handing the case to the graph):

    PENDING -> DISPATCHING
    DISPATCHING -> DONE        (agent finished or already finished)
    DISPATCHING -> PENDING     (busy or temporary failure: retry later)
    DISPATCHING -> EXHAUSTED   (out of retries)
    Final: DONE, EXHAUSTED

Portal batch (confirmed by both owners 2026-11-25):

    OPEN -> ASSIGNED -> IN_PROGRESS -> REVIEWER_DECIDED
    REVIEWER_DECIDED -> CLOSED          (nothing escalated)
    REVIEWER_DECIDED -> EXPERT_REVIEW   (some findings escalated)
    EXPERT_REVIEW -> CLOSED
    Final: CLOSED

### Rules

1. Only the moves listed above are allowed. Everything else is refused.
2. Moving to the same status is refused (SCORING -> SCORING).
3. Nothing moves out of a final status.
4. CANCELLED is reachable from every non-final agent status, and from no
   final status.
5. The three state machines are separate: an agent status can never be
   checked against dispatch rules, and vice versa.
6. The allowed moves live in one table per machine, in this file only.
   No other file defines its own list.
7. The error message names both statuses, e.g.
   "Cannot move agent case from CREATED to SCORING".

### Out of scope

- Validation outcomes and comparison modes (Part 2, validation_report.py)
- Routing actions (waiting on mentor question 3)
- TERMINATED (in the guide, not in our spec.md; add only if needed)
- Export states and reassignment (portal cut list)
- Saving states anywhere; this file only defines and checks them

### Acceptance tests

| # | Given | When | Then |
|---|---|---|---|
| 1 | agent CREATED | move to PLANNED | allowed |
| 2 | agent CREATED | move to SCORING | refused (skips steps) |
| 3 | agent ROUTING | move to CLOSED, or to HITL_PENDING | both allowed |
| 4 | agent VALIDATING | move to CANCELLED | allowed |
| 5 | agent CLOSED | move to any status | refused (final) |
| 6 | agent CANCELLED | move to CANCELLED | refused |
| 7 | agent SCORING | move to SCORING | refused (same status) |
| 8 | agent SCORING | move to PLANNED | refused (no going back) |
| 9 | each agent status | ask is_final | true only for CLOSED, HITL_PENDING, CANCELLED |
| 10 | dispatch DISPATCHING | move to PENDING | allowed (retry) |
| 11 | dispatch EXHAUSTED | move to PENDING | refused (final) |
| 12 | dispatch PENDING | move to DONE | refused (must dispatch first) |
| 13 | portal REVIEWER_DECIDED | move to EXPERT_REVIEW, or to CLOSED | both allowed |
| 14 | portal IN_PROGRESS | move to CLOSED | refused (must finish review first) |
| 15 | agent CREATED -> SCORING | call require_transition | InvalidTransition naming both statuses |
| 16 | AgentCaseState.SCORING | convert to JSON | the text "SCORING" |
| 17 | every agent status | look up its allowed moves | every status has an entry in the table |

### Files

- New: common/states.py
- New: common/tests/test_contracts.py (states tests first; later parts add to it)
- Hand-written by owner: none. The owner writes and checks the move tables
  above; Claude Code turns them into code.

### Tasks

- [x] Teammate confirms the portal batch statuses
- [x] Write failing tests for cases 1-17
- [x] Write common/states.py until they pass
- [x] ruff, mypy, pytest pass
- [x] Tick "common/states.py" in docs/plan.md, add a session log line

---

## Part 2 - common/validation_report.py
<next>

## Notes for the next session

<fill in at the end>