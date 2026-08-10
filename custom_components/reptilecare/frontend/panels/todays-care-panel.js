import { sharedCardStyles } from "../styles/reptilecare-styles.js";

class ReptileCareTodaysCarePanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
  }

  set hass(value) {
    this._hass = value;
    this._render();
  }

  _reptiles() {
    if (!this._hass) {
      return [];
    }

    const reptiles = Object.values(this._hass.states)
      .filter((stateObj) => stateObj.entity_id.endsWith("_pending_care_tasks"))
      .map((stateObj) => ({
        reptile_id: stateObj.attributes.reptile_id,
        name: stateObj.attributes.friendly_name?.replace(/ Pending Care Tasks$/, "") ?? "Reptile",
        species: stateObj.attributes.species ?? null,
      }))
      .filter((item) => item.reptile_id)
      .sort((left, right) => left.name.localeCompare(right.name));

    const unique = new Map();
    reptiles.forEach((item) => {
      if (!unique.has(item.reptile_id)) {
        unique.set(item.reptile_id, item);
      }
    });
    return [...unique.values()];
  }

  _render() {
    const reptiles = this._reptiles();

    this.shadowRoot.innerHTML = `
      <style>
        ${sharedCardStyles}
        :host {
          display: block;
          padding: 24px;
          box-sizing: border-box;
        }

        .layout {
          display: grid;
          gap: 20px;
          max-width: 1100px;
          margin: 0 auto;
        }

        .hero {
          background: linear-gradient(135deg, var(--card-background-color), color-mix(in srgb, var(--primary-color) 10%, var(--card-background-color)));
          border-radius: 24px;
          padding: 24px;
          border: 1px solid var(--divider-color);
        }

        .eyebrow {
          font-size: 0.8rem;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          color: var(--secondary-text-color);
          margin: 0 0 8px;
        }

        .title {
          margin: 0;
          font-size: clamp(1.8rem, 3vw, 2.4rem);
          line-height: 1.1;
        }

        .subtitle {
          margin: 12px 0 0;
          color: var(--secondary-text-color);
          max-width: 55rem;
          line-height: 1.5;
        }

        .empty {
          padding: 24px;
          border-radius: 20px;
          border: 1px dashed var(--divider-color);
          background: color-mix(in srgb, var(--card-background-color) 88%, var(--primary-color));
        }

        .cards {
          display: grid;
          gap: 20px;
        }

        .section-header {
          display: flex;
          flex-direction: column;
          gap: 4px;
        }

        .section-title {
          margin: 0;
          font-size: 1.1rem;
        }

        .section-meta {
          color: var(--secondary-text-color);
          font-size: 0.92rem;
        }

        @media (max-width: 720px) {
          :host {
            padding: 16px;
          }

          .hero {
            padding: 18px;
            border-radius: 18px;
          }
        }
      </style>
      <div class="layout">
        <section class="hero">
          <p class="eyebrow">ReptileCare</p>
          <h1 class="title">Today's Care</h1>
          <p class="subtitle">
            Review what each reptile needs today, record care as you complete it, and let ReptileCare update the day’s workload in place.
          </p>
        </section>
        ${
          reptiles.length === 0
            ? `
              <section class="empty">
                <h2 class="section-title">No reptiles are available yet.</h2>
                <p class="subtitle">
                  Add your first reptile from the ReptileCare integration settings to start tracking daily care here.
                </p>
              </section>
            `
            : `
              <section class="cards">
                ${reptiles
                  .map(
                    (reptile) => `
                      <div class="section-header">
                        <h2 class="section-title">${reptile.name}</h2>
                        ${
                          reptile.species
                            ? `<div class="section-meta">${reptile.species}</div>`
                            : ""
                        }
                      </div>
                      <reptilecare-todays-care-card data-reptile-id="${reptile.reptile_id}"></reptilecare-todays-care-card>
                    `,
                  )
                  .join("")}
              </section>
            `
        }
      </div>
    `;

    this.shadowRoot
      .querySelectorAll("reptilecare-todays-care-card")
      .forEach((card) => {
        card.setConfig({ reptile_id: card.dataset.reptileId });
        card.hass = this._hass;
      });
  }
}

if (!customElements.get("reptilecare-todays-care-panel")) {
  customElements.define("reptilecare-todays-care-panel", ReptileCareTodaysCarePanel);
}
