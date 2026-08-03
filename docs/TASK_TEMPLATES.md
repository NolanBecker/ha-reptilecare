# Task Templates

Task Templates are immutable reusable definitions of care actions. They answer
one narrow question:

> What kind of care action is this?

Examples include **Feed Fruit Mix**, **Spot Clean**, **Deep Clean**, **Weigh**,
**Medication**, and **Replace UVB**.

Task Templates are not scheduled work, do not belong to one reptile, and do
not execute workflows. They exist so later layers can reference stable,
validated care-action definitions without duplicating action vocabulary across
plans, tasks, services, dashboards, or automations.

## Purpose

Task Templates provide the reusable building blocks for future planning and task
layers:

- They define stable template IDs such as `builtin:feed_fruit`.
- They classify work using typed categories.
- They declare which outcomes are valid for that kind of work.
- They describe optional structured context a future completion flow may ask
  for.
- They reserve a typed place for future completion behavior and workflow-graph
  attachment without executing anything today.

Templates intentionally do not answer when something should happen or which
reptile needs it. That belongs to future CarePlans and CareTasks.

## Lifecycle

The current foundation only supports bundled built-in JSON templates:

```text
Bundled JSON template
        ↓
 task_template_from_dict
        ↓
   TaskTemplate
        ↓
TaskTemplateRegistry
        ↓
 ReptileCare runtime data
```

This keeps template loading deterministic, validation strict, and runtime usage
independent from Home Assistant entities or event history.

## Relationship to Care Plans

A future CarePlan will reference one TaskTemplate to describe what kind of work
it schedules.

```text
TaskTemplate --> CarePlan --> CareTask --> CareEvent
```

The template defines the action vocabulary. The plan will define recurrence,
timing, and reptile-specific configuration later.

That separation prevents reusable definitions such as **Weigh** or
**Replace UVB** from accumulating reptile state, schedule rules, or historical
facts.

## Relationship to Care Tasks

A future CareTask will be a concrete actionable instance derived from a
TaskTemplate plus CarePlan context and reptile context.

```text
TaskTemplate
   ↓ defines
CareTask
   ↓ completed as
CareEvent
```

The template describes the kind of action. The task will later represent one
specific actionable occurrence of that action.

## Relationship to TaskWorkflowService

`CompletionBehavior` exists only as a descriptive placeholder in this branch.
`workflow_graph_id` allows a template to reference a reusable `WorkflowGraph`
without embedding the graph inline.

They intentionally do not:

- execute workflows
- generate follow-up tasks
- schedule future work
- create notifications

That execution boundary belongs to a future `TaskWorkflowService`, which will
consume validated template definitions rather than embedding template logic
inside its own runtime state.

## Model structure

The current `TaskTemplate` model includes:

- `template_id`: stable namespaced identifier such as `builtin:feed_fruit`
- `display_name`: keeper-facing label
- `description`: reusable action description
- `category`: typed `TaskCategory`
- `icon`: optional future presentation hint
- `expected_outcomes`: typed `TaskOutcomeDefinition` entries
- `context_fields`: typed `TaskContextFieldDefinition` entries
- `default_priority`: typed default importance
- `estimated_duration`: optional expected minutes
- `completion_behavior`: descriptive future side effects
- `completion_behavior.workflow_graph_id`: optional reusable workflow graph
  reference
- `metadata`: extensible structured data
- `schema_version` and `template_version`: explicit version fields

All models are immutable and validated at construction time.

## Outcomes

Outcomes are definitions, not recorded facts. They establish which result
labels are valid for a given template.

Examples:

- `builtin:feed_fruit`: `ate_normally`, `ate_partially`, `refused`, `skipped`,
  `cancelled`
- `builtin:spot_clean`: `completed`, `partially_completed`,
  `nothing_to_clean`, `skipped`
- `builtin:medication`: `administered`, `refused`, `missed`, `regurgitated`

This gives future task-completion and workflow layers a typed vocabulary without
recording actual outcomes in this branch.

## Context fields

Context fields are reusable definitions of optional structured information a
future completion flow may request.

Examples:

- Feeding: `food_used`, `quantity`, `notes`
- Weigh: `weight`, `notes`
- Medication: `dosage`, `notes`
- Health Check: `notes`, `photo`

Field definitions describe identifiers, display names, value types, optional
units, and extensible metadata. They do not collect values yet.

## Current boundaries

This foundation does not implement:

- Care Plans
- Care Tasks
- workflow execution
- Home Assistant services
- entities
- notifications
- dashboards
- completion UI
- recorded template-specific runtime state

Task Templates remain reusable definitions only.
