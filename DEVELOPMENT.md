# Development workflow

ReptileCare uses GitHub Issues, milestones, and the ReptileCare Roadmap project
to turn the committed roadmap into reviewable work. This document describes
how maintainers and contributors move work from an idea to a merged change.

## Planning model

The project uses four planning levels:

1. `docs/ROADMAP.md` defines the committed sequence of product phases.
2. A GitHub milestone represents one roadmap phase.
3. An issue labeled `type: epic` groups the work required to complete a phase.
4. Focused child issues describe independently reviewable outcomes.

Epic descriptions contain task lists that link their child issues. Keep those
lists current when scope changes. Exploratory ideas do not enter a committed
milestone until maintainers have accepted their scope.

## Labels

Labels are additive dimensions rather than an exhaustive state machine:

- GitHub's standard labels identify bugs, documentation, community-friendly
  work, duplicates, questions, and declined requests.
- `type:` labels identify epics, features, and maintenance work.
- `area:` labels identify the affected ReptileCare domain or infrastructure.
- `priority:` labels communicate scheduling priority within a milestone.
- `needs:` labels identify work that requires design or discussion first.
- `status: blocked` records an external dependency that prevents progress.

Every planned issue should have one primary area and one priority. Add a type
label when the standard GitHub labels do not already communicate the work type.

## Project board

The ReptileCare Roadmap project is the shared Kanban view for committed work:

- **Todo**: accepted and ready to be scheduled.
- **In Progress**: actively being implemented or documented.
- **Done**: completed and merged.

Move an issue to In Progress when a contributor begins work. Keep the issue
assigned to its roadmap milestone, and link the pull request before requesting
review. GitHub automation may move closed items to Done; maintainers should
correct the board when repository state and project state diverge.

## Starting work

1. Select an unblocked issue from Todo.
2. Confirm that its acceptance criteria and architectural boundaries are clear.
3. Discuss architecture, persistence, public APIs, or UX model changes before
   implementation.
4. Create a focused branch from current `main` using the naming rules in
   `docs/CONTRIBUTING.md`.
5. Move the issue to In Progress and assign it when appropriate.

One branch should address one primary issue. Additional cleanup belongs in a
separate issue unless it is necessary to deliver the accepted scope.

## Pull requests

Open a draft pull request early for work that benefits from design feedback.
Use a closing keyword such as `Closes #123` when the pull request fully resolves
an issue. Use a plain reference when it provides context without closing the
issue.

Before requesting review:

- satisfy the issue acceptance criteria;
- add or update focused tests;
- update relevant user and contributor documentation;
- run Ruff, pytest, hassfest, and HACS validation as applicable;
- describe migrations, compatibility concerns, and follow-up work; and
- remove unrelated files, generated artifacts, and debugging output.

Review is complete when required checks pass, actionable conversations are
resolved, and the change remains aligned with the project vision and UX
principles. Maintainers merge using the repository's current merge policy.

## Architecture decisions

Changes to domain boundaries, CarePlan or CareTask semantics, CareEvent
history, storage schemas, Home Assistant public APIs, or compatibility policy
must be discussed in an issue before implementation. Record the decision and
its tradeoffs in the issue or a dedicated architecture document so later
contributors can understand why the constraint exists.

## Milestone maintenance

When a child issue is added, removed, or moved, update the epic and milestone
together. Close an epic only when its accepted children are complete or
explicitly moved out of scope. Before closing a milestone, verify that its
documentation, migrations, tests, and release notes accurately describe the
delivered behavior.
