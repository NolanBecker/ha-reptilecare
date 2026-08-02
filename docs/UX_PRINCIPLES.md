# User Experience Principles

ReptileCare should make responsible care feel calm, clear, and achievable. The
interface is successful when a keeper understands what needs attention and can
act without navigating the architecture beneath it.

## Start with today

The primary dashboard question is:

> What does my reptile need today?

The answer should be visible before history, configuration, or statistics.
Urgency must be understandable without relying on color alone, and the
interface should distinguish due, upcoming, completed, deferred, and overdue
work without creating alarm fatigue.

## Make daily care one or two taps

Routine CareTasks should usually require one tap to open and one tap to
complete. Defaults should reflect the active CarePlan, with optional details
available when the user needs them. Repeatedly asking for context Home Assistant
already knows is a design failure.

Fast interaction must not make accidental records difficult to correct. Future
correction workflows should remain explicit and preserve a trustworthy history.

## Speak in care language

Users work with reptiles, CarePlans, and CareTasks. CareEvents are the historical
audit log and should appear only where reviewing history makes them useful.
Storage versions, projections, and coordinator refreshes are never user-facing
concepts.

Labels should describe concrete actions: “Feed Pixel” is clearer than “Create
feeding event.” Wording should remain respectful and avoid implying veterinary
certainty.

## Reduce cognitive load on every screen

Each screen should have a clear purpose, a visible next action, and an
understandable hierarchy. Information should earn its place by helping a keeper
decide, act, or review.

- Prefer progressive disclosure over crowded forms.
- Preserve context when moving between a reptile, a task, and history.
- Use consistent status language across cards, notifications, and management
  views.
- Avoid streaks, guilt, and gamification that turn care into a score.
- Make exceptional conditions visible without making normal care feel urgent.

## Enhance Home Assistant rather than replacing it

ReptileCare should fit naturally into existing Home Assistant dashboards. A
keeper may want Pixel’s next CareTask beside enclosure climate controls or a
household overview. Reusable cards should support those compositions.

Advanced management—editing reptiles, configuring CarePlans, reviewing full
history, and exploring statistics—belongs in a future ReptileCare Center.
That dashboard complements normal Home Assistant views; it does not become a
parallel smart-home interface.

## Provide beautiful defaults and deep customization

The default presentation should be polished, accessible, and useful without
manual dashboard construction. Visual rhythm, typography, empty states, and
status treatments should feel intentional.

Home Assistant users also expect control. Cards should offer meaningful options
and compose with themes without requiring every user to design the basic
experience themselves. Customization should extend a coherent default rather
than compensate for a missing one.

## Design mobile-first

Care happens near an enclosure, often with one hand occupied. Primary actions
need comfortable touch targets, short paths, and layouts that work on narrow
screens. Important information must not depend on hover behavior.

Desktop layouts may reveal more context, but the essential workflow must remain
complete on a phone.

## Be Home Assistant-first

Use familiar Home Assistant interaction patterns, terminology, entities,
services, notifications, and dashboard behavior wherever they fit. Novel UI
should be reserved for reptile-care needs that standard patterns cannot express
well.

Automation should quietly capture useful context and remove repetitive steps.
It should remain inspectable, reversible where appropriate, and compatible with
the user’s broader Home Assistant configuration.

## Remain local-first

Core care workflows, history, and dashboards must operate without a vendor
cloud. The user owns the data and should eventually have clear ways to back it
up and export it.

Optional integrations may enrich context in the future, but loss of internet
access must not prevent a keeper from seeing or recording care.

## Build trust through clarity

ReptileCare should distinguish recorded facts, derived conclusions, configured
expectations, and suggestions. When an answer depends on missing history or a
changed CarePlan, the interface should say so plainly.

The integration supports care organization; it does not diagnose illness or
replace qualified veterinary advice. Health-oriented screens must preserve that
boundary in both wording and interaction design.
