import { sharedCardStyles } from "../styles/reptilecare-styles.js";
import { escapeHtml } from "../utils/html.js";
import { formatDueDetails } from "../utils/time.js";

function eventName(name) {
  return `reptilecare:${name}`;
}

export class ReptileCareTaskListItem extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._task = null;
    this._busy = false;
    this._locale = "en";
  }

  set task(value) {
    this._task = value;
    this._render();
  }

  set busy(value) {
    this._busy = Boolean(value);
    this._render();
  }

  set locale(value) {
    this._locale = value || "en";
    this._render();
  }

  _dispatch(name, detail = {}) {
    this.dispatchEvent(
      new CustomEvent(eventName(name), {
        bubbles: true,
        composed: true,
        detail,
      }),
    );
  }

  _bindEvents() {
    this.shadowRoot.querySelectorAll("[data-action]").forEach((button) => {
      button.addEventListener("click", () => {
        const action = button.getAttribute("data-action");
        if (action === "details") {
          this._dispatch("details", { task: this._task });
        } else if (action === "complete") {
          this._dispatch("complete", { task: this._task });
        } else if (action === "skip") {
          this._dispatch("skip", { task: this._task });
        } else if (action === "quick-complete") {
          this._dispatch("quick-complete", {
            task: this._task,
            outcomeId: button.getAttribute("data-outcome-id"),
          });
        }
      });
    });
  }

  _render() {
    if (!this.shadowRoot || !this._task) {
      return;
    }

    const { absolute, relative } = formatDueDetails(this._task.due_at, this._locale);
    const presentation = this._task.presentation;
    const priority = escapeHtml(presentation.priority);
    const title = escapeHtml(presentation.title);
    const description = presentation.description
      ? `<p class="description">${escapeHtml(presentation.description)}</p>`
      : "";
    const overdue = this._task.due_state === "overdue";
    const dueBadge = overdue
      ? `<span class="status-badge overdue">Overdue</span>`
      : `<span class="status-badge">${escapeHtml(this._task.due_state)}</span>`;

    const quickActions = this._task.quick_actions_enabled
      ? `
        <div class="quick-actions">
          ${this._task.completion_schema.outcomes
            .map(
              (outcome) => `
                <button
                  class="quick-action-button"
                  type="button"
                  data-action="quick-complete"
                  data-outcome-id="${escapeHtml(outcome.outcome_id)}"
                  ${this._busy ? "disabled" : ""}
                >
                  ${escapeHtml(outcome.display_name)}
                </button>
              `,
            )
            .join("")}
        </div>
      `
      : `
        <button class="action-button" type="button" data-action="complete" ${this._busy ? "disabled" : ""}>
          Complete
        </button>
      `;

    this.shadowRoot.innerHTML = `
      <style>
        ${sharedCardStyles}

        :host {
          display: block;
        }

        .task {
          border: 1px solid var(--divider-color);
          border-radius: 18px;
          padding: 1rem;
          background:
            linear-gradient(
              180deg,
              color-mix(in srgb, var(--card-background-color) 94%, var(--primary-color)),
              var(--card-background-color)
            );
          display: grid;
          gap: 0.9rem;
        }

        .header {
          display: grid;
          grid-template-columns: auto 1fr auto;
          align-items: start;
          gap: 0.9rem;
        }

        .icon-wrap {
          width: 2.25rem;
          height: 2.25rem;
          border-radius: 14px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          background: color-mix(in srgb, var(--primary-color) 12%, transparent);
          color: var(--primary-color);
        }

        .title {
          font-size: 1rem;
          font-weight: 700;
          line-height: 1.35;
          margin: 0;
        }

        .meta,
        .due-line {
          margin: 0.2rem 0 0;
          color: var(--secondary-text-color);
          font-size: 0.92rem;
        }

        .description {
          margin: 0;
          color: var(--secondary-text-color);
          line-height: 1.45;
        }

        .priority {
          border-radius: 999px;
          padding: 0.2rem 0.6rem;
          background: color-mix(in srgb, var(--secondary-background-color) 80%, transparent);
          color: var(--secondary-text-color);
          font-size: 0.76rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.03em;
        }

        .footer {
          display: grid;
          gap: 0.75rem;
        }

        .actions,
        .quick-actions {
          display: flex;
          flex-wrap: wrap;
          gap: 0.55rem;
        }

        .secondary-actions {
          display: flex;
          gap: 0.55rem;
        }

        .status-badge {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          min-height: 1.75rem;
          padding: 0.15rem 0.55rem;
          border-radius: 999px;
          background: color-mix(in srgb, var(--primary-color) 10%, transparent);
          color: var(--primary-color);
          font-size: 0.78rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.04em;
        }

        .status-badge.overdue {
          background: color-mix(in srgb, var(--error-color) 14%, transparent);
          color: var(--error-color);
        }

        @media (max-width: 520px) {
          .header {
            grid-template-columns: auto 1fr;
          }

          .priority {
            justify-self: start;
          }
        }
      </style>
      <article class="task">
        <div class="header">
          <span class="icon-wrap" aria-hidden="true">
            <ha-icon icon="${escapeHtml(presentation.icon || "mdi:clipboard-text-clock-outline")}"></ha-icon>
          </span>
          <div>
            <h3 class="title">${title}</h3>
            <p class="due-line" title="${escapeHtml(absolute)}">Due ${escapeHtml(relative)}</p>
            <p class="meta">${escapeHtml(absolute)}</p>
          </div>
          <span class="priority">${priority}</span>
        </div>
        <div>${dueBadge}</div>
        ${description}
        <div class="footer">
          <div class="actions">
            ${quickActions}
          </div>
          <div class="secondary-actions">
            <button class="action-button" type="button" data-action="skip" ${this._busy ? "disabled" : ""}>
              Skip
            </button>
            <button class="action-button" type="button" data-action="details" ${this._busy ? "disabled" : ""}>
              Details
            </button>
          </div>
        </div>
      </article>
    `;

    this._bindEvents();
  }
}

if (!customElements.get("reptilecare-task-list-item")) {
  customElements.define("reptilecare-task-list-item", ReptileCareTaskListItem);
}

