# Roadmap

This roadmap describes the intended sequence for ReptileCare. Each phase should
leave the integration useful, tested, and ready for the next layer. Scope may
be refined through design discussion, but later phases should not bypass the
domain boundaries established earlier.

The [core domain design proposal](CORE_DOMAIN_DESIGN.md) records the proposed
model and workflow boundaries that should be resolved before Phases 2–4 are
implemented. Open product decisions in that proposal are not committed
requirements until accepted.

## Committed roadmap

### Phase 1 — Foundation

Establish the Home Assistant integration lifecycle and the internal event
engine.

- HACS-ready custom integration structure
- Config-entry setup, reload, unload, diagnostics, and validation
- Immutable event model and canonical event vocabulary
- Versioned, migration-ready Home Assistant storage
- Timeline queries and coordinator ownership
- Test, lint, and documentation standards

### Phase 2 — Reptile Management

Allow keepers to create and maintain multiple reptile profiles.

- Add, edit, archive, and restore reptiles
- Species, morph, hatch date, sex, and notes
- Stable reptile identifiers independent of display names
- Pixel, a Gargoyle Gecko, as the first complete development profile
- Migration-safe persistence for reptile profiles

The phase now has two domain foundations: the versioned `SpeciesProfile`
registry for shared husbandry reference data, and the persistent
`ReptileRepository` for immutable keeper-owned animal records. User-facing
creation and editing workflows remain future work.

### Phase 3 — Care Plans

Define what care an individual reptile should receive and under what
conditions.

- Reusable plan model with reptile-specific configuration
- Feeding and cleaning plans as the initial care domains
- Clear recurrence and due-date semantics
- Pausing, resuming, and revising plans without rewriting history
- Separation between plan definitions and completed-care CareEvents

Phase 3 now begins with three upstream foundations already in place:
`SpeciesProfileRegistry` for shared husbandry guidance, `TaskTemplateRegistry`
for reusable care-action definitions, `WorkflowRegistry` for reusable behavior
definitions, and `ReptileRepository` for keeper-owned animal identity. Future
CarePlans should reference these foundations rather than redefining action
vocabulary, behavior vocabulary, or runtime reptile data.

The CarePlan foundation now also establishes persistent keeper-owned plan
identity, descriptive interval schedules, and descriptive reminder
configuration without generating tasks or executing workflows yet.

### Phase 4 — Care Tasks

Turn CarePlans into concrete, user-facing actions.

- Today, upcoming, overdue, and completed task views
- One- or two-tap completion for routine care
- Task dismissal, deferral, and correction rules
- CareEvent creation from completed tasks
- Clear handling of ad hoc care that did not originate from a plan

CareTasks are the primary interaction model. CareEvents remain the audit log
behind task completion.

This phase should consume `WorkflowGraph` definitions through an application
service rather than embedding workflow execution into templates or entities
directly.

The first CareTask foundation now exists: persistent task identity,
deterministic generation, startup reconciliation, and derived due-state
projection.

The CareEngine execution loop now also exists: terminal task resolution,
TaskOutcome validation, immutable CareEvent creation, pure workflow
evaluation, deterministic follow-up task generation, and restart
reconciliation.

Home Assistant task-resolution entities, notifications, and broader UI surfaces
remain future Phase 4 and Phase 5 work.

### Phase 5 — Home Assistant Services

Expose stable actions for automations, scripts, voice assistants, and external
clients.

- Create and complete supported CareTasks
- Record supported CareEvents
- Query or target reptiles using stable identifiers
- Validate inputs through shared domain logic
- Preserve backward compatibility as the service surface evolves

Phase 5 has now started with a first production-quality service layer for:

- reptile create, update, enable, and disable
- care-plan create, update, enable, and disable
- idempotent task generation
- CareEngine-backed task resolution
- manual immutable event logging
- read-only task and timeline queries

Entities, dashboards, notifications, and broader UI still remain future work.

The first entity milestone is now also complete:

- one Home Assistant device per reptile
- compact task-summary sensors
- compact care-state binary sensors
- a per-reptile generate-tasks button
- dynamic entity discovery for reptiles created through services
- recorder-friendly bounded attributes instead of one entity per task

### Phase 6 — Dashboard Cards

Provide polished, reusable cards that enhance existing Home Assistant
dashboards.

- A concise “needs today” card
- Reptile summary and CareTask cards
- Timeline and recent-care views
- Mobile-first layouts and accessible interactions
- Reusable cards that can be placed on any Home Assistant dashboard
- A future ReptileCare Center for advanced workflows

### Phase 7 — Notifications

Deliver useful prompts without creating alert fatigue.

- Actionable CareTask notifications
- Household-aware routing and quiet-time support
- Escalation rules for genuinely overdue care
- Completion directly from supported notification surfaces
- Context-sensitive suppression when care has already been recorded

### Phase 8 — Statistics

Derive understandable trends from event history.

- Care completion history and intervals
- Feeding, cleaning, weight, and shedding summaries
- Clear treatment of missing or corrected data
- Home Assistant-compatible statistics where appropriate
- Explanations that distinguish recorded facts from derived interpretation

Statistics should inform keepers without turning care into a score.

### Phase 9 — Health Tracking

Support structured observations while remaining firmly outside diagnosis.

- Health notes and observable symptoms
- Medication or treatment records when explicitly entered by the keeper
- Weight and shedding context
- Exportable history for conversations with qualified veterinary professionals
- Prominent boundaries against medical diagnosis or prescriptive advice

### Phase 10 — Photos and Growth Tracking

Connect visual history with growth and care records.

- Photographs attached to reptiles and relevant CareEvents
- Weight and measurement history
- Chronological growth views
- Storage-conscious media handling
- Privacy-preserving exports and backups

## Future exploration

The following ideas are not committed roadmap items. They require user research,
technical evaluation, and maintainership capacity before adoption:

- Environmental correlations using existing Home Assistant sensors
- Enclosure and habitat models shared by multiple animals
- Household roles and responsibility assignment
- Import and export formats for long-term portability
- Optional husbandry templates maintained separately from individual CarePlans
- Voice-first CareTask completion
- NFC, QR, or presence-assisted workflows near enclosures
- Privacy-preserving sharing with veterinarians or temporary caregivers
- Support for other exotic animals where the domain model genuinely fits

Exploratory features must preserve local-first operation, avoid presenting
correlation as medical advice, and strengthen rather than bypass the CarePlan →
CareTask → CareEvent model.
