# Contributing to ReptileCare

Thanks for helping improve ReptileCare. This repository uses short-lived
feature branches, Conventional Commits, and Release Please so changes stay
reviewable and releases stay predictable.

## Development workflow

Use the following path for normal work:

```text
feature branch
    ↓
draft pull request
    ↓
review and CI
    ↓
merge to main
    ↓
Release Please release PR
    ↓
GitHub Release and tag
    ↓
HACS sees the new version
```

Start each change from the latest `main` and keep the branch focused on one
user-visible outcome or one tightly related maintenance change.

## Branch naming

Create lowercase branches with one of these prefixes:

- `feature/` for new capabilities
- `fix/` for bug fixes
- `docs/` for documentation-only work
- `refactor/` for behavior-preserving internal changes
- `test/` for test-only work
- `chore/` for maintenance and tooling

Examples:

```text
feature/task-entities
fix/service-error-message
chore/release-automation
```

## Conventional Commits

ReptileCare uses Conventional Commits because Release Please derives release
notes and semantic versions from merged commit messages.

Format:

```text
type(scope): summary
```

Examples:

```text
feat(services): add task-generation preview response
fix(entities): handle reptiles without care events
docs(readme): clarify HACS installation steps
chore(release): automate releases
```

Common types:

- `feat`: user-visible capability, usually triggers a minor release
- `fix`: bug fix, usually triggers a patch release
- `docs`: documentation only
- `refactor`: internal restructuring without behavior change
- `test`: tests only
- `chore`: tooling, maintenance, or repository housekeeping

Breaking changes must use either `!` after the type or scope, or a
`BREAKING CHANGE:` footer:

```text
feat(api)!: rename task query filters
```

## Versioning policy

ReptileCare follows semantic versioning:

- `MAJOR`: incompatible public-contract or migration-heavy change
- `MINOR`: backward-compatible new capability
- `PATCH`: backward-compatible bug fix

Pre-release tags remain valid semantic versions. Release Please updates the
Python package version, integration manifest version, changelog, release PR,
and GitHub tag together.

## Release workflow

1. Merge Conventional Commit history into `main`.
2. Release Please opens or updates a release PR.
3. The release PR runs the normal repository validation workflows.
4. When that PR is merged, Release Please creates the GitHub tag and release.
5. HACS consumes the new tagged version from the GitHub release.

Use a repository secret named `RELEASE_PLEASE_TOKEN` when possible. A personal
access token allows release PRs, tags, and releases to trigger downstream
GitHub Actions consistently. `GITHUB_TOKEN` works as a fallback, but GitHub may
skip follow-on workflow execution for automation-created refs.

## Local quality checks

Run before opening or updating a pull request:

```bash
ruff format --check .
ruff check .
pytest --cov --cov-report=term-missing
```

Pull requests must also pass the repository’s Home Assistant `hassfest` and
HACS validation workflows.

## Documentation expectations

Update documentation with the code change when behavior, architecture, release
process, or user-facing workflows change. At minimum, review:

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/ROADMAP.md`
- any feature-specific document affected by the change

## Pull requests

Open new work as a draft pull request early when the branch spans more than a
small edit. Include:

- the user-facing goal
- validation performed
- storage or compatibility concerns
- screenshots for visible UI changes
- follow-up decisions still needing review, if any

Keep unrelated cleanup out of the branch unless it is required to complete the
change safely.
