# Contributing to ReptileCare

Thank you for helping make reptile care easier to manage in Home Assistant.
Contributions are welcome across code, tests, documentation, accessibility,
design, and domain research.

Before starting substantial work, read the [project vision](../VISION.md),
[architecture](ARCHITECTURE.md), [roadmap](ROADMAP.md), and
[UX principles](UX_PRINCIPLES.md).

## Discuss architectural changes first

Open an issue or discussion before implementing a change that affects domain
boundaries, persistence schemas, event semantics, CarePlan or CareTask
lifecycle, public Home Assistant APIs, or compatibility expectations.

Early discussion is not a barrier to contribution. It protects event history
and helps maintainers identify migration, user-experience, and Home Assistant
implications before code makes those decisions expensive to change.

## Branch naming

Create a focused branch from the latest `main`. Use lowercase words separated
by hyphens after one of these prefixes:

- `feature/` for new capabilities
- `fix/` for defect corrections
- `docs/` for documentation-only work
- `refactor/` for behavior-preserving internal changes
- `test/` for test infrastructure or coverage
- `chore/` for maintenance

Examples:

```text
feature/care-task-completion
fix/timeline-date-filter
docs/event-migration-policy
```

## Feature branch workflow

1. Update local `main` from the upstream repository.
2. Create a focused branch using the naming convention above.
3. Make small, reviewable commits with imperative commit messages.
4. Add or update tests and documentation with the implementation.
5. Run the complete local quality checks.
6. Rebase or update the branch if `main` changed materially.
7. Open a pull request and respond to review without rewriting unrelated code.

Avoid mixing cleanup or unrelated refactoring into a feature branch. Preserve
existing user changes when working in a shared checkout.

## Coding standards

ReptileCare follows current Home Assistant custom-integration practices.

- Use full type hints for production code.
- Prefer immutable dataclasses for domain values.
- Keep I/O asynchronous and avoid blocking the Home Assistant event loop.
- Keep persistence behind explicit protocols or boundaries.
- Derive care state from authoritative event history.
- Keep Home Assistant entities thin; domain logic belongs in domain modules.
- Add concise docstrings to public modules, classes, and interfaces.
- Use stable identifiers rather than display names for relationships.
- Do not introduce cloud dependencies for core behavior.

Ruff defines the project’s formatting and lint rules. Do not manually format
code in a way that conflicts with Ruff.

## Testing requirements

Every behavior change requires tests at the narrowest useful layer. Changes to
storage or history must cover serialization, restart behavior, ordering,
migration, and failure handling as applicable. Home Assistant lifecycle changes
must test setup and unload behavior.

Run before opening a pull request:

```bash
ruff format --check .
ruff check .
pytest --cov --cov-report=term-missing
```

The repository enforces a coverage threshold, but coverage percentage does not
replace meaningful assertions. Tests should describe observable behavior and
avoid depending on execution order or wall-clock time.

## Home Assistant and HACS validation

Pull requests must pass all configured GitHub Actions checks:

- Ruff formatting and linting
- pytest and coverage
- Home Assistant `hassfest`
- HACS validation

Keep `manifest.json` compatible with Home Assistant requirements. Its keys must
start with `domain`, then `name`, followed by all remaining keys alphabetically.
Update strings, translations, icons, diagnostics, and config-entry tests when a
change affects those surfaces.

## Documentation expectations

Documentation is part of the feature, not follow-up work.

- Update the README when installation, supported behavior, or document
  navigation changes.
- Update the roadmap when committed scope changes.
- Update architecture documentation when responsibilities or data flow change.
- Describe user-facing behavior in CareTask language rather than exposing
  CareEvents as the primary interaction.
- Include migration notes for persistent or public-contract changes.
- Avoid promises for exploratory ideas that have not been accepted into the
  roadmap.

Use direct, professional language. Explain constraints and tradeoffs rather
than repeating implementation details.

## Pull request expectations

A pull request should:

- Solve one clearly described problem.
- Explain the user impact and architectural impact.
- Link the relevant issue or prior design discussion.
- List validation performed and any platform-specific limitations.
- Include tests for new behavior and regressions.
- Include screenshots or recordings for visible UI changes.
- Identify storage migrations, compatibility concerns, or follow-up work.
- Leave the repository free of unrelated generated files and debug output.

Review focuses on correctness, maintainability, Home Assistant compatibility,
care-first UX, accessibility, and alignment with the project vision. All review
threads should be resolved before merge.

## Domain and health contributions

Reptile care varies by species and individual. Cite reliable sources when a
change introduces husbandry assumptions, and design defaults so keepers can
adapt them appropriately. ReptileCare must not present software behavior as
diagnosis or a substitute for a qualified veterinarian.

The project welcomes lived experience, but no single keeper’s routine should be
silently encoded as a universal rule.
