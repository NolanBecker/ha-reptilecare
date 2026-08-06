# Onboarding

ReptileCare now includes a first-run onboarding flow designed for a completely
new Home Assistant user.

## Goal

A new user should be able to:

```text
Install ReptileCare
  ↓
Add Integration
  ↓
Create first reptile
  ↓
Choose species from built-in catalog
  ↓
Install recommended care plans
  ↓
Generate today's care
  ↓
Open dashboard
```

without seeing UUIDs, internal repository identifiers, or developer-only
concepts.

## Flow steps

The config flow now guides the user through:

1. Welcome
2. Create Reptile
3. Choose Species
4. Recommended Care
5. Generate Initial Tasks
6. Finish

The flow stores a serialized onboarding request in the config entry, and
`async_setup_entry` applies that request using the normal repositories and task
generation pipeline.

## What onboarding installs

On successful setup ReptileCare will:

- create the reptile record
- select the matching built-in SpeciesProfile
- install the selected keeper-owned CarePlans
- optionally generate initial CareTasks

The wizard never requires a user to create a SpeciesProfile manually.

## Species selection

Species choices come from the built-in content registry, not hardcoded Python
lists. Adding another packaged species file extends the available onboarding
choices without changing CareEngine.

## Recommended care

Species packages point to reusable built-in care-plan templates such as:

- feeding
- spot cleaning
- water changes
- deep cleaning

The onboarding wizard lets a keeper deselect any recommendation before
installation.

## Options flow

Existing installations skip onboarding and use the options flow as the
management hub.

The current options flow supports:

- Add Reptile
- Species Library
- Import Demo Data
- General Settings

This keeps existing users compatible while giving new users a friendlier first
experience.

## Demo data

Optional demo data installs:

- Pixel
- sample care plans
- sample history
- generated pending tasks

It is never installed automatically for an existing user.

## Boundaries

Onboarding is an adapter layer only.

It does not:

- write raw storage records directly
- bypass repositories
- hardcode CareEngine behavior
- evaluate workflows itself
- duplicate task generation logic

All persistent creation still flows through the existing repositories,
generator, and runtime event publisher.
