import { sharedCardStyles } from "../styles/reptilecare-styles.js";
import { escapeHtml } from "../utils/html.js";
import { formatDueDetails } from "../utils/time.js";

function fieldInputMarkup(field, value) {
  const escapedValue = escapeHtml(value ?? "");
  const label = escapeHtml(field.display_name);
  const description = field.description
    ? `<p class="field-description">${escapeHtml(field.description)}</p>`
    : "";
  const unit = field.unit ? `<span class="field-unit">${escapeHtml(field.unit)}</span>` : "";

  if (field.field_type === "number") {
    return `
      <label class="field">
        <span class="field-label">${label}${field.required ? " *" : ""}</span>
        ${description}
        <div class="field-input-wrap">
          <input
            class="field-input"
            type="number"
            step="any"
            data-field-id="${escapeHtml(field.field_id)}"
            value="${escapedValue}"
          />
          ${unit}
        </div>
      </label>
    `;
  }

  return `
    <label class="field">
      <span class="field-label">${label}${field.required ? " *" : ""}</span>
      ${description}
      <div class="field-input-wrap">
        <input
          class="field-input"
          type="text"
          data-field-id="${escapeHtml(field.field_id)}"
          value="${escapedValue}"
        />
        ${unit}
      </div>
    </label>
  `;
}

export class ReptileCareTaskCompletionDialog extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._task = null;
    this._open = false;
    this._busy = false;
    this._error = "";
    this._notes = "";
    this._selectedOutcome = "";
    this._fieldValues = {};
    this._locale = "en";
  }

  set locale(value) {
    this._locale = value || "en";
    this._render();
  }

  set state(value) {
    this._task = value.task ?? null;
    this._open = Boolean(value.open);
    this._busy = Boolean(value.busy);
    this._error = value.error ?? "";
    this._notes = value.notes ?? "";
    this._selectedOutcome = value.selectedOutcome ?? "";
    this._fieldValues = value.fieldValues ?? {};
    this._render();
  }

  _dispatch(name, detail = {}) {
    this.dispatchEvent(
      new CustomEvent(`reptilecare:${name}`, {
        bubbles: true,
        composed: true,
        detail,
      }),
    );
  }

  _syncDialogOpenState() {
    const dialog = this.shadowRoot?.querySelector("dialog");
    if (!dialog) {
      return;
    }

    if (this._open && !dialog.open) {
      dialog.showModal();
    } else if (!this._open && dialog.open) {
      dialog.close();
    }
  }

  _bindEvents() {
    const dialog = this.shadowRoot.querySelector("dialog");
    dialog?.addEventListener("cancel", (event) => {
      event.preventDefault();
      this._dispatch("dialog-close");
    });

    this.shadowRoot.querySelector("[data-close]")?.addEventListener("click", () => {
      this._dispatch("dialog-close");
    });

    this.shadowRoot.querySelector("[data-submit]")?.addEventListener("click", () => {
      this._dispatch("dialog-submit");
    });

    this.shadowRoot.querySelectorAll("[name='outcome']").forEach((radio) => {
      radio.addEventListener("change", () => {
        this._dispatch("dialog-change", {
          selectedOutcome: radio.value,
        });
      });
    });

    this.shadowRoot.querySelector("[data-notes]")?.addEventListener("input", (event) => {
      this._dispatch("dialog-change", {
        notes: event.target.value,
      });
    });

    this.shadowRoot.querySelectorAll("[data-field-id]").forEach((input) => {
      input.addEventListener("input", (event) => {
        this._dispatch("dialog-field-change", {
          fieldId: input.getAttribute("data-field-id"),
          value: event.target.value,
        });
      });
    });
  }

  _render() {
    if (!this.shadowRoot || !this._task) {
      return;
    }

    const { absolute, relative } = formatDueDetails(this._task.due_at, this._locale);
    const outcomes = this._task.completion_schema.outcomes ?? [];
    const contextFields = this._task.completion_schema.context_fields ?? [];
    const errorMarkup = this._error
      ? `<p class="error-banner" role="alert">${escapeHtml(this._error)}</p>`
      : "";

    this.shadowRoot.innerHTML = `
      <style>
        ${sharedCardStyles}

        dialog {
          width: min(32rem, calc(100vw - 2rem));
          max-width: 100%;
          border: none;
          border-radius: 20px;
          padding: 0;
          background: var(--card-background-color);
          color: var(--primary-text-color);
          box-shadow: var(--ha-dialog-box-shadow, 0 24px 48px rgba(0, 0, 0, 0.28));
        }

        dialog::backdrop {
          background: rgba(0, 0, 0, 0.42);
        }

        .dialog-shell {
          display: grid;
          gap: 1rem;
          padding: 1.15rem;
        }

        .dialog-header {
          display: flex;
          justify-content: space-between;
          align-items: start;
          gap: 0.75rem;
        }

        .dialog-title {
          margin: 0;
          font-size: 1.1rem;
          line-height: 1.35;
        }

        .dialog-meta {
          margin: 0.3rem 0 0;
          color: var(--secondary-text-color);
          font-size: 0.92rem;
        }

        .dialog-close {
          border: none;
          background: transparent;
          color: var(--secondary-text-color);
          cursor: pointer;
          border-radius: 999px;
          width: 2.25rem;
          height: 2.25rem;
        }

        .section-title {
          margin: 0 0 0.55rem;
          font-size: 0.92rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.04em;
          color: var(--secondary-text-color);
        }

        .outcomes {
          display: grid;
          gap: 0.55rem;
        }

        .outcome-option {
          display: grid;
          gap: 0.25rem;
          padding: 0.8rem;
          border: 1px solid var(--divider-color);
          border-radius: 16px;
        }

        .outcome-label {
          display: flex;
          gap: 0.65rem;
          align-items: start;
        }

        .outcome-title {
          font-weight: 600;
        }

        .outcome-description,
        .field-description {
          margin: 0;
          color: var(--secondary-text-color);
          font-size: 0.9rem;
          line-height: 1.45;
        }

        .field-grid {
          display: grid;
          gap: 0.85rem;
        }

        .field {
          display: grid;
          gap: 0.35rem;
        }

        .field-label {
          font-weight: 600;
        }

        .field-input-wrap {
          display: grid;
          grid-template-columns: 1fr auto;
          gap: 0.55rem;
          align-items: center;
        }

        .field-input,
        .notes-input {
          width: 100%;
          box-sizing: border-box;
          border: 1px solid var(--divider-color);
          border-radius: 14px;
          background: var(--card-background-color);
          color: var(--primary-text-color);
          padding: 0.75rem 0.85rem;
          font: inherit;
        }

        .notes-input {
          min-height: 6rem;
          resize: vertical;
        }

        .field-unit {
          color: var(--secondary-text-color);
          font-size: 0.92rem;
        }

        .error-banner {
          margin: 0;
          padding: 0.75rem 0.85rem;
          border-radius: 14px;
          background: color-mix(in srgb, var(--error-color) 14%, transparent);
          color: var(--error-color);
        }

        .dialog-actions {
          display: flex;
          justify-content: end;
          gap: 0.65rem;
          flex-wrap: wrap;
        }

        .dialog-button {
          border: 1px solid var(--divider-color);
          border-radius: 999px;
          padding: 0.65rem 1rem;
          cursor: pointer;
          background: var(--card-background-color);
          color: var(--primary-text-color);
        }

        .dialog-button.primary {
          border-color: var(--primary-color);
          background: var(--primary-color);
          color: var(--text-primary-color, #fff);
        }
      </style>
      <dialog aria-label="${escapeHtml(this._task.presentation.title)}">
        <div class="dialog-shell">
          <div class="dialog-header">
            <div>
              <h2 class="dialog-title">${escapeHtml(this._task.presentation.title)}</h2>
              <p class="dialog-meta">Due ${escapeHtml(relative)} · ${escapeHtml(absolute)}</p>
            </div>
            <button class="dialog-close" type="button" data-close aria-label="Close dialog" ${this._busy ? "disabled" : ""}>
              <ha-icon icon="mdi:close"></ha-icon>
            </button>
          </div>
          ${errorMarkup}
          ${
            outcomes.length
              ? `
                <section>
                  <h3 class="section-title">Outcome</h3>
                  <div class="outcomes">
                    ${outcomes
                      .map(
                        (outcome) => `
                          <label class="outcome-option">
                            <span class="outcome-label">
                              <input
                                type="radio"
                                name="outcome"
                                value="${escapeHtml(outcome.outcome_id)}"
                                ${this._selectedOutcome === outcome.outcome_id ? "checked" : ""}
                                ${this._busy ? "disabled" : ""}
                              />
                              <span>
                                <span class="outcome-title">${escapeHtml(outcome.display_name)}</span>
                                ${
                                  outcome.description
                                    ? `<p class="outcome-description">${escapeHtml(outcome.description)}</p>`
                                    : ""
                                }
                              </span>
                            </span>
                          </label>
                        `,
                      )
                      .join("")}
                  </div>
                </section>
              `
              : ""
          }
          ${
            contextFields.length
              ? `
                <section>
                  <h3 class="section-title">Structured fields</h3>
                  <div class="field-grid">
                    ${contextFields
                      .map((field) => fieldInputMarkup(field, this._fieldValues[field.field_id]))
                      .join("")}
                  </div>
                </section>
              `
              : ""
          }
          <section>
            <h3 class="section-title">Notes</h3>
            <textarea
              class="notes-input"
              data-notes
              placeholder="Optional keeper notes"
              ${this._busy ? "disabled" : ""}
            >${escapeHtml(this._notes)}</textarea>
          </section>
          <div class="dialog-actions">
            <button class="dialog-button" type="button" data-close ${this._busy ? "disabled" : ""}>
              Cancel
            </button>
            <button class="dialog-button primary" type="button" data-submit ${this._busy ? "disabled" : ""}>
              Complete
            </button>
          </div>
        </div>
      </dialog>
    `;

    this._bindEvents();
    this._syncDialogOpenState();
  }
}

if (!customElements.get("reptilecare-task-completion-dialog")) {
  customElements.define(
    "reptilecare-task-completion-dialog",
    ReptileCareTaskCompletionDialog,
  );
}

