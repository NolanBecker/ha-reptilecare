# LizardCare

LizardCare is a Home Assistant custom integration for tracking reptile care. It
is being built around an event-driven, multi-reptile architecture so care
history can grow without coupling independent features together.

> [!NOTE]
> This first release is an architectural foundation. It creates a single
> LizardCare config entry but does not yet expose entities or pet-management
> features.

## Features

The current foundation provides:

- UI configuration through Home Assistant's config flow
- Safe setup, reload, and unload behavior
- An event-driven `DataUpdateCoordinator` with no periodic polling
- Typed event and runtime models
- A pluggable event-store boundary for future persistence
- Downloadable diagnostics containing non-sensitive scaffold metadata

Planned feature modules include feeding, cleaning, weight, shedding, health,
notes, photos, and environmental tracking. Schedules, reminders, dashboards,
and pet logic are intentionally outside this initial milestone.

## Installation through HACS

Until LizardCare is listed in the default HACS catalog:

1. Open HACS in Home Assistant.
2. Select **Integrations** and open the three-dot menu.
3. Choose **Custom repositories**.
4. Add `https://github.com/NolanBecker/ha-lizardcare` with the **Integration**
   category.
5. Install **LizardCare** and restart Home Assistant.
6. Go to **Settings → Devices & services → Add integration**, then search for
   **LizardCare**.

## Manual installation

1. Copy `custom_components/lizardcare` into the `custom_components` directory
   in your Home Assistant configuration directory.
2. Restart Home Assistant.
3. Add **LizardCare** from **Settings → Devices & services**.

## Development setup

Python 3.14.2 or newer is recommended.

```bash
git clone https://github.com/NolanBecker/ha-lizardcare.git
cd ha-lizardcare
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[test]"
ruff format --check .
ruff check .
pytest
```

On Windows, activate the environment with `.venv\Scripts\activate`.

## Architecture

Each future feature is expected to own its event vocabulary and projection
logic while sharing immutable `LizardCareEvent` records, the `EventStore`
contract, the canonical `EventType` vocabulary, and the coordinator's immutable
snapshot. This keeps feature modules independent and allows the initial no-op
store to be replaced by persistent storage without changing entity code.

## Roadmap

- Establish the integration lifecycle and event/storage contracts
- Add multi-reptile profiles and persistent event history
- Introduce feeding, cleaning, weight, and shedding modules
- Add health, notes, photos, and environmental tracking
- Build schedules, reminders, and dashboard-friendly entities after the event
  model is stable

Pixel, a Gargoyle Gecko, is the first development reptile and will guide early
use cases. LizardCare is intentionally designed to support many individual
reptiles and reptile species in future releases.

## License

LizardCare is licensed under the [MIT License](LICENSE).
