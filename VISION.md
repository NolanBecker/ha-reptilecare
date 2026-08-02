# LizardCare Vision

## Mission

LizardCare exists to make excellent reptile care easier to sustain. It gives
keepers a calm, dependable view of what each animal needs, records what has
happened, and uses thoughtful automation to reduce the mental load of recurring
care.

The project is local-first, open source, and native to Home Assistant. It should
feel like part of the home rather than another isolated tracking application.

## The problem

Reptile care is a collection of small, important actions spread across
different timescales. Feeding may happen several times a week, water and food
may need follow-up, enclosure maintenance happens on multiple cycles, and
weight, shedding, health observations, and environmental conditions become
meaningful only when viewed over time.

Today, keepers often hold this context in memory or distribute it across notes,
calendar reminders, spreadsheets, and device-specific applications. Those
tools can record information, but they rarely connect care history to the home
where care takes place. The result is unnecessary cognitive overhead: deciding
what is due, remembering what was completed, and reconstructing a history when
something changes.

LizardCare is designed around a more useful question:

> What does my reptile need today?

Answering that question well requires reliable history, understandable care
plans, and a user experience that makes routine actions nearly effortless.

## Why Home Assistant

Home Assistant already understands the context around animal care. It can know
the enclosure temperature and humidity, whether someone is home, when lights
changed, and which notification channels are appropriate. It offers durable
local operation, flexible dashboards, mature automation, and a large ecosystem
of devices without requiring LizardCare to recreate them.

LizardCare should use those strengths directly. Its cards should fit into
existing Home Assistant dashboards. Its future entities and services should
compose with standard automations. Advanced management can live in a dedicated
LizardCare dashboard without forcing users to abandon the views they already
use for their homes.

The integration remains useful without cloud services. Care history belongs to
the keeper, stays under their control, and continues to work when the internet
does not.

## Core philosophy

### Care comes first

The product is organized around animals and their care, not around data entry.
Language, defaults, and workflows should reflect how keepers think. Every
feature must make care clearer, easier, or more reliable.

### Care Tasks are the primary interaction

Users interact with **Care Tasks**: concrete actions such as feeding Pixel,
removing uneaten food, or spot-cleaning an enclosure. A routine task should
usually take one or two taps to complete. Care Plans explain why and when those
tasks appear.

Events are an implementation detail and historical audit log. They make the
system trustworthy, but users should not have to understand event sourcing to
care for an animal.

### Automation should be quiet and useful

Automation should reduce mental load, not create more alerts to manage. When
Home Assistant already has useful context, LizardCare should capture or apply
it without asking the user to repeat information. Notifications should be
timely, actionable, and respectful of attention.

### State is derived from history

LizardCare records immutable facts and derives current answers from them. This
makes care history auditable, allows improved logic to reinterpret existing
records, and avoids contradictory fields such as a stored “last feeding” that
does not match the event history.

### Beautiful defaults, durable foundations

The default experience should be approachable and visually considered. Deep
customization should remain available through Home Assistant, but it should not
be required for a useful result. Internally, stable boundaries and clear domain
language matter more than rushing visible features.

### Open development

LizardCare is open source so keepers and contributors can inspect its behavior,
shape its priorities, and adapt it to different species and husbandry
practices. The project should welcome evidence, experience, and respectful
disagreement without presenting software defaults as veterinary advice.

## Long-term vision

LizardCare should become the care layer for reptiles in Home Assistant. A
keeper should be able to define a reptile and its Care Plans, see today’s Care
Tasks alongside the rest of the home, complete routine care quickly, and review
a coherent timeline of what happened.

Over time, the same foundation can support health observations, growth,
photographs, environmental context, and careful statistics. Reusable dashboard
cards should work wherever a keeper needs them. A dedicated management
dashboard should provide deeper planning and history without replacing normal
Home Assistant dashboards.

Pixel, a Gargoyle Gecko, is the first development reptile. Pixel provides a
real, concrete use case, but the architecture and language must remain suitable
for many reptiles, species, households, and care practices.

## Non-goals

LizardCare is not intended to:

- Replace veterinary care or provide diagnosis.
- Prescribe universal husbandry rules for every species or animal.
- Become a general-purpose veterinary practice or shelter-management system.
- Duplicate Home Assistant’s automation engine, notification system, or
  dashboard platform.
- Require a hosted account, proprietary cloud, or closed ecosystem.
- Turn routine care into a competitive score or punish users for imperfect
  streaks.

The measure of success is not how much data LizardCare collects. It is whether
keepers can understand and complete good care with less effort and greater
confidence.
