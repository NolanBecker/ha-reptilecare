import { sharedCardStyles } from "../styles/reptilecare-styles.js";
import { escapeHtml } from "../utils/html.js";
import { formatDueDetails } from "../utils/time.js";

function eventName(name) {
  return `reptilecare:${name}`;
}

function dueStateLabel(task) {
  switch (task.urgency_group) {
    case "overdue":
      return "Overdue";
    case "due":
      return "Due now";
    case "upcoming_today":
      return "Upcoming today";
    default:
      return "Future";
  }
}

export class ReptileCareTaskListItem extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._task = null;
    this._locale = "en";
  }

  set task(value) {
    this._task = value;
    this._render();
  }

  get task() {
    return this._task;
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
    const title = escapeHtml(presentation.title);
    const carePlanName = presentation.care_plan_display_name
      ? `<p class="meta">${escapeHtml(presentation.care_plan_display_name)}</p>`
      : "";
    const description = presentation.description
      ? `<p class="description">${escapeHtml(presentation.description)}</p>`
      : "";
    const quickActions = this._task.quick_actions_enabled
      ? `
        <div class="quick-actions" role="group" aria-label="Quick outcomes for ${title}">
          ${this._task.completion_schema.outcomes
            .map(
              (outcome) => `
                <button
                  class="quick-action-button"
                  type="button"
                  data-action="quick-complete"
                  data-outcome-id="${escapeHtml(outcome.outcome_id)}"
                  ${this._task.ui.busy ? "disabled" : ""}
                >
                  ${escapeHtml(outcome.display_name)}
                </button>
              `,
            )
            .join("")}
        </div>
      `
      : `
        <button
          class="action-button primary-action"
          type="button"
          data-action="complete"
          ${this._task.ui.busy ? "disabled" : ""}
        >
          Complete
        </button>
      `;
    const inlineError = this._task.ui.error
      ? `<p class="inline-error" role="alert">${escapeHtml(this._task.ui.error)}</p>`
      : "";
    const busyIndicator = this._task.ui.busy
      ? `<span class="busy-indicator" aria-live="polite">Saving…</span>`
      : "";
    const urgencyClass = escapeHtml(this._task.urgency_group);
    const phase = escapeHtml(this._task.ui.phase);

    this.shadowRoot.innerHTML = `
      <style>
        ${sharedCardStyles}

        :host {
          display: block;
        }

        .task {
          display: grid;
          gap: 0.9rem;
          padding: 1rem;
          border: 1px solid color-mix(in srgb, var(--divider-color) 88%, transparent);
          border-radius: 20px;
          background:
            linear-gradient(
              180deg,
              color-mix(in srgb, var(--card-background-color) 96%, transparent),
              color-mix(in srgb, var(--secondary-background-color) 22%, var(--card-background-color))
            );
          transition:
            opacity 180ms ease,
            transform 180ms ease,
            border-color 180ms ease,
            box-shadow 180ms ease;
        }

        .task[data-urgency="overdue"] {
          border-color: color-mix(in srgb, var(--error-color) 40%, var(--divider-color));
          box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--error-color) 12%, transparent);
        }

        .task[data-urgency="due"] {
          border-color: color-mix(in srgb, var(--warning-color, #f0b400) 44%, var(--divider-color));
        }

        .task[data-phase="entering"] {
          opacity: 0;
          transform: translateY(10px);
        }

        .task[data-phase="exiting"] {
          opacity: 0;
          transform: translateY(-8px);
        }

        .task[data-busy="true"] {
          box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--primary-color) 16%, transparent);
        }

        .header {
          display: grid;
          grid-template-columns: auto 1fr;
          gap: 0.9rem;
          align-items: start;
        }

        .icon-wrap {
          width: 2.6rem;
          height: 2.6rem;
          border-radius: 16px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          background: color-mix(in srgb, var(--primary-color) 13%, transparent);
          color: var(--primary-color);
        }

        .task[data-urgency="overdue"] .icon-wrap {
          background: color-mix(in srgb, var(--error-color) 14%, transparent);
          color: var(--error-color);
        }

        .title-row {
          display: flex;
          flex-wrap: wrap;
          gap: 0.55rem;
          align-items: center;
        }

        .title {
          margin: 0;
          font-size: 1rem;
          font-weight: 700;
          line-height: 1.35;
        }

        .status-badge,
        .priority-badge {
          display: inline-flex;
          align-items: center;
          min-height: 1.7rem;
          padding: 0.2rem 0.6rem;
          border-radius: 999px;
          font-size: 0.76rem;
          font-weight: 700;
          letter-spacing: 0.03em;
        }

        .status-badge {
          background: color-mix(in srgb, var(--primary-color) 11%, transparent);
          color: var(--primary-color);
        }

        .task[data-urgency="overdue"] .status-badge {
          background: color-mix(in srgb, var(--error-color) 15%, transparent);
          color: var(--error-color);
        }

        .task[data-urgency="due"] .status-badge {
          background: color-mix(in srgb, var(--warning-color, #f0b400) 18%, transparent);
          color: color-mix(in srgb, var(--warning-color, #f0b400) 88%, black);
        }

        .priority-badge {
          background: color-mix(in srgb, var(--secondary-background-color) 70%, transparent);
          color: var(--secondary-text-color);
          text-transform: uppercase;
        }

        .meta,
        .due-line,
        .description {
          margin: 0;
          color: var(--secondary-text-color);
        }

        .due-line {
          margin-top: 0.3rem;
          font-weight: 600;
          color: var(--primary-text-color);
        }

        .meta {
          margin-top: 0.2rem;
          font-size: 0.92rem;
        }

        .description {
          line-height: 1.45;
          font-size: 0.94rem;
        }

        .footer {
          display: grid;
          gap: 0.75rem;
        }

        .actions,
        .quick-actions,
        .secondary-actions {
          display: flex;
          flex-wrap: wrap;
          gap: 0.55rem;
        }

        .primary-action,
        .quick-action-button {
          background: color-mix(in srgb, var(--primary-color) 12%, var(--card-background-color));
          border-color: color-mix(in srgb, var(--primary-color) 28%, var(--divider-color));
        }

        .inline-error {
          margin: 0;
          padding: 0.7rem 0.8rem;
          border-radius: 14px;
          background: color-mix(in srgb, var(--error-color) 12%, transparent);
          color: var(--error-color);
          font-size: 0.92rem;
          line-height: 1.4;
        }

        @media (max-width: 720px) {
          .task {
            padding: 0.95rem;
          }

          .header {
            grid-template-columns: auto 1fr;
          }

          .actions,
          .quick-actions,
          .secondary-actions {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }

          .quick-action-button:first-child:last-child,
          .primary-action {
            grid-column: 1 / -1;
          }
        }
      </style>
      <article
        class="task"
        data-urgency="${urgencyClass}"
        data-phase="${phase}"
        data-busy="${this._task.ui.busy ? "true" : "false"}"
        aria-busy="${this._task.ui.busy ? "true" : "false"}"
      >
        <div class="header">
          <span class="icon-wrap" aria-hidden="true">
            <ha-icon icon="${escapeHtml(presentation.icon)}"></ha-icon>
          </span>
          <div>
            <div class="title-row">
              <h3 class="title">${title}</h3>
              <span class="status-badge">${escapeHtml(dueStateLabel(this._task))}</span>
              <span class="priority-badge">${escapeHtml(presentation.priority)}</span>
            </div>
            <p class="due-line" title="${escapeHtml(absolute)}">Due ${escapeHtml(relative)}</p>
            <p class="meta">${escapeHtml(absolute)}</p>
            ${carePlanName}
          </div>
        </div>
        ${description}
        ${inlineError}
        <div class="footer">
          ${busyIndicator}
          <div class="actions">
            ${quickActions}
          </div>
          <div class="secondary-actions">
            <button
              class="action-button"
              type="button"
              data-action="skip"
              aria-label="Skip ${title}"
              ${this._task.ui.busy ? "disabled" : ""}
            >
              Skip
            </button>
            <button
              class="action-button"
              type="button"
              data-action="details"
              aria-label="Open details for ${title}"
              ${this._task.ui.busy ? "disabled" : ""}
            >
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
