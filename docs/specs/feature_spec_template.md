# Feature spec: <NN - name>

Save as `docs/specs/NN-name.md`. One file per feature, not per session.
Owner: <name>. Phase in plan.md: <n>. Status: draft / in progress / done.

## Goal

<One or two sentences. What can the system do after this that it could not do before?>

## Inputs and outputs

- Input: <which contract from common/, with an example>
- Output: <which contract, with an example>

## Rules

1. <A rule the code must follow, written so it can be tested.>
2. <...>

## Out of scope

- <What this feature deliberately does not do.>

## Acceptance tests

Each line becomes at least one test. Write these BEFORE any code.

| # | Given | When | Then |
|---|---|---|---|
| 1 | Gold phone "(555) 010-0100", evidence "555-010-0100" | validate phone | CONFIRMED |
| 2 | Gold phone "555-010-0100", evidence "555-010-0199" | validate phone | DISCREPANCY, recommended value is the evidence value |
| 3 | no evidence for phone | validate phone | CANNOT_BE_VERIFIED, reason no_data |

## Files

- New: <path>
- Changed: <path>
- Hand-written by owner (Claude proposes only): <path>

## Tasks

- [ ] Write failing tests for cases 1-3
- [ ] <implement ...>
- [ ] ruff, mypy, pytest pass
- [ ] Tick the task in docs/plan.md

## Notes for the next session

<What is half done, what was decided and why, what to do first next time.>