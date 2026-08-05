# Contributing to ReptileCare

Thanks for helping improve ReptileCare. This repository uses short-lived
feature branches, Conventional PR titles, squash merges for feature work, and
Release Please so changes stay reviewable and releases stay predictable.

## Development workflow

Use the following path for normal work:

```text
feature branch
    ↓
draft pull request
    ↓
review and CI
    ↓
squash merge to main
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

## Conventional PR titles and commits

ReptileCare uses Conventional Commits because Release Please derives release
notes and semantic versions from the commit messages that land on `main`.

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

The pull request title must follow this format. GitHub Actions validates the PR
title on `pull_request` events so the generated squash-merge commit stays
parseable even if intermediate branch commits are not all Conventional.

Common types:

- `feat`: user-visible capability, triggers a minor release
- `fix`: bug fix, triggers a patch release
- `docs`: documentation only and may appear in changelog context, but does not
  normally trigger a release on its own
- `refactor`: internal restructuring without behavior change and does not
  normally trigger a release on its own
- `test`: tests only and does not normally trigger a release on its own
- `chore`: tooling, maintenance, or repository housekeeping and does not
  normally trigger a release on its own
- `ci`, `build`, `perf`, `revert`: allowed when they accurately describe the
  change

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
project version, integration manifest version, changelog, release PR, and
GitHub tag together.

Current baseline:

- latest published release: `v0.1.2`
- tracked Release Please baseline version: `0.1.2`
- commit baseline for future parsing: `9a7c45b41f95a9ab79253026ae80c61f52b3ddb9`

## Release workflow

1. Merge a feature PR with a Conventional Commit title into `main`.
2. Release Please opens or updates a release PR.
3. The release PR runs the normal repository validation workflows.
4. Review the proposed version and changelog in the release PR.
5. Merge the release PR normally once checks pass.
6. Release Please creates the GitHub tag and GitHub Release.
7. HACS consumes the new tagged release.

Preferred merge method:

- squash merge for normal feature, fix, docs, and refactor PRs
- normal merge for Release Please release PRs once checks pass

Squash merging keeps `main` linear and ensures the PR title becomes the
release-relevant commit subject that Release Please parses.

Version bump rules:

- `fix:` bumps patch
- `feat:` bumps minor
- `!` or `BREAKING CHANGE:` bumps major
- `docs`, `test`, `refactor`, `chore`, `ci`, `build`, `perf`, and `revert`
  are allowed titles but do not normally produce a release PR on their own

If Release Please logs `No user facing commits found`, check these first:

- the merged PR title on `main` was not a releasable `feat:` or `fix:`
- the PR was merged without a parseable Conventional title
- an old `autorelease: pending` or `autorelease: triggered` label is still
  attached to a prior release PR
- the fix or feature merged before the current configured release baseline

Use a repository secret named `RELEASE_PLEASE_TOKEN` when possible. A personal
access token allows release PRs, tags, and releases to trigger downstream
GitHub Actions consistently. `GITHUB_TOKEN` works as a fallback, but GitHub may
skip follow-on workflow execution for automation-created refs.

Safe verification method:

1. Merge this baseline fix as `chore(release): fix Release Please baseline`.
2. Open a small follow-up PR with a valid title such as
   `fix(release): verify automated release detection`.
3. Merge it with squash merge.
4. Confirm Release Please opens or updates a release PR.
5. Review the proposed version and changelog before merging the release PR.
6. Do not merge the release PR until the version and release notes look correct.

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
