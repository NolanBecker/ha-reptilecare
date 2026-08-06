import "../components/task-list-item.js";
import "../dialogs/task-completion-dialog.js";

import {
  applyTaskUiState,
  buildHeaderContext,
  groupTasks,
  mergeResolutionResult,
  normalizeTask,
  resolveReptileLabel,
  settleInsertedTasks,
  summarizeTaskList,
  validateTodaysCareConfig,
} from "../models/todays-care-model.js";
import { fetchTodaysCareTasks, resolveTask } from "../services/reptilecare-api.js";
import { sharedCardStyles } from "../styles/reptilecare-styles.js";
import { escapeHtml } from "../utils/html.js";

const RELEVANT_DOMAINS = new Set(["sensor", "binary_sensor", "button"]);
const EXIT_TRANSITION_MS = 180;
const ENTER_TRANSITION_MS = 220;

function cardMetadata() {
  return {
    type: "reptilecare-todays-care-card",
    name: "ReptileCare Today's Care",
    preview: false,
    description: "Shows actionable care tasks for one reptile and resolves them through ReptileCare services.",
    documentationURL: "https://github.com/NolanBecker/ha-reptilecare/blob/main/docs/FRONTEND.md",
  };
}

function defaultDialogState() {
  return {
    open: false,
    task: null,
    busy: false,
    error: "",
    notes: "",
    selectedOutcome: "",
    fieldValues: {},
  };
}

export class ReptileCareTodaysCareCard extends HTMLElement {
  static getStubConfig() {
    return { slug: "pixel" };
  }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = null;
    this._hass = null;
    this._loading = false;
    this._error = "";
    this._tasks = [];
    this._refreshHandle = null;
    this._entitySignature = "";
    this._dialog = defaultDialogState();
    this._announcer = "";
    this._loadPromise = null;
    this._queuedSilentRefresh = false;
  }

  setConfig(config) {
    this._config = validateTodaysCareConfig(config);
    this._render();
  }

  set hass(value) {
    this._hass = value;
    this._scheduleRefreshFromStateChange();
    this._render();
  }

  connectedCallback() {
    this._loadTasks();
  }

  disconnectedCallback() {
    if (this._refreshHandle) {
      window.clearTimeout(this._refreshHandle);
      this._refreshHandle = null;
    }
  }

  getCardSize() {
    return Math.max(3, this._tasks.length * 2);
  }

  getGridOptions() {
    return {
      columns: 6,
      min_rows: 3,
      rows: Math.max(3, this._tasks.length * 2),
    };
  }

  _identifierPayload() {
    return this._config.reptile_id
      ? { reptile_id: this._config.reptile_id }
      : { slug: this._config.slug };
  }

  _matchingEntityStates() {
    if (!this._hass || !this._config) {
      return [];
    }

    return Object.values(this._hass.states)
      .filter((stateObj) => RELEVANT_DOMAINS.has(stateObj.entity_id.split(".")[0]))
      .filter((stateObj) => {
        if (this._config.reptile_id) {
          return stateObj.attributes.reptile_id === this._config.reptile_id;
        }
        return stateObj.attributes.slug === this._config.slug;
      })
      .sort((left, right) => left.entity_id.localeCompare(right.entity_id));
  }

  _computeEntitySignature() {
    return this._matchingEntityStates()
      .map((stateObj) => `${stateObj.entity_id}:${stateObj.state}:${stateObj.last_updated}`)
      .join("|");
  }

  _prefersReducedMotion() {
    return Boolean(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
  }

  async _afterMotion(delayMs) {
    if (this._prefersReducedMotion()) {
      return;
    }
    await new Promise((resolve) => {
      window.setTimeout(resolve, delayMs);
    });
  }

  _scheduleRefreshFromStateChange() {
    if (!this.isConnected || !this._hass || !this._config) {
      return;
    }

    const nextSignature = this._computeEntitySignature();
    if (!nextSignature || nextSignature === this._entitySignature) {
      return;
    }

    this._entitySignature = nextSignature;
    if (this._refreshHandle) {
      window.clearTimeout(this._refreshHandle);
    }
    this._refreshHandle = window.setTimeout(() => {
      this._refreshHandle = null;
      this._loadTasks({ silent: true });
    }, 120);
  }

  _replaceTasks(tasks) {
    this._tasks = tasks.map((task) => normalizeTask(task));
  }

  _setTasks(tasks) {
    this._tasks = tasks.map((task) => normalizeTask(task));
    this._render();
  }

  _setAnnouncer(message) {
    this._announcer = message;
  }

  async _loadTasks({ silent = false } = {}) {
    if (!this._hass || !this._config) {
      return;
    }

    if (this._loadPromise) {
      this._queuedSilentRefresh = this._queuedSilentRefresh || silent;
      return this._loadPromise;
    }

    if (!silent) {
      this._loading = true;
      this._error = "";
      this._render();
    }

    this._loadPromise = (async () => {
      try {
        this._replaceTasks(await fetchTodaysCareTasks(this._hass, this._config));
        this._error = "";
        this._entitySignature = this._computeEntitySignature();
      } catch (error) {
        this._error = error instanceof Error ? error.message : "Unable to load care tasks";
      } finally {
        this._loading = false;
        this._render();
      }
    })();

    try {
      await this._loadPromise;
    } finally {
      this._loadPromise = null;
      if (this._queuedSilentRefresh) {
        this._queuedSilentRefresh = false;
        void this._loadTasks({ silent: true });
      }
    }
  }

  _openDialog(task) {
    const defaultOutcome = task.completion_schema.outcomes[0]?.outcome_id ?? "";
    this._dialog = {
      open: true,
      task,
      busy: false,
      error: "",
      notes: "",
      selectedOutcome: defaultOutcome,
      fieldValues: {},
    };
    this._render();
  }

  _closeDialog() {
    this._dialog = defaultDialogState();
    this._render();
  }

  _updateDialog(change) {
    this._dialog = {
      ...this._dialog,
      ...change,
    };
    this._render();
  }

  _updateDialogField(fieldId, value) {
    this._dialog = {
      ...this._dialog,
      fieldValues: {
        ...this._dialog.fieldValues,
        [fieldId]: value,
      },
    };
    this._render();
  }

  _buildOutcomeMetadata(task) {
    const metadata = {};
    for (const field of task.completion_schema.context_fields) {
      const rawValue = this._dialog.fieldValues[field.field_id];
      if (rawValue == null || rawValue === "") {
        if (field.required) {
          throw new Error(`${field.display_name} is required`);
        }
        continue;
      }

      if (field.field_type === "number") {
        const numeric = Number(rawValue);
        if (!Number.isFinite(numeric)) {
          throw new Error(`${field.display_name} must be a number`);
        }
        metadata[field.field_id] = numeric;
      } else {
        metadata[field.field_id] = rawValue;
      }
    }
    return metadata;
  }

  async _applyResolutionSuccess(task, response) {
    this._tasks = applyTaskUiState(this._tasks, task.task_id, {
      busy: false,
      error: "",
      phase: "exiting",
    });
    this._render();

    await this._afterMotion(EXIT_TRANSITION_MS);

    this._tasks = mergeResolutionResult(this._tasks, task.task_id, response);
    this._setAnnouncer(`${task.presentation.title} updated.`);
    this._render();

    if (!this._prefersReducedMotion()) {
      window.setTimeout(() => {
        this._tasks = settleInsertedTasks(this._tasks);
        this._render();
      }, ENTER_TRANSITION_MS);
    }

    void this._loadTasks({ silent: true });
  }

  async _resolveTask(task, payload) {
    this._tasks = applyTaskUiState(this._tasks, task.task_id, {
      busy: true,
      error: "",
      phase: "busy",
    });
    this._error = "";
    this._render();

    try {
      const response = await resolveTask(this._hass, task.task_id, payload);
      await this._applyResolutionSuccess(task, response);
      return response;
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to resolve task";
      this._tasks = applyTaskUiState(this._tasks, task.task_id, {
        busy: false,
        error: message,
        phase: "idle",
      });
      this._error = message;
      this._setAnnouncer(message);
      this._render();
      throw error;
    }
  }

  async _handleQuickComplete(task, outcomeId) {
    try {
      await this._resolveTask(task, {
        action: "complete",
        outcome_id: outcomeId,
        outcome_metadata: {},
      });
    } catch {
      return;
    }
  }

  async _handleSkip(task) {
    try {
      await this._resolveTask(task, {
        action: "skip",
      });
    } catch {
      return;
    }
  }

  async _submitDialog() {
    const task = this._dialog.task;
    if (!task) {
      return;
    }

    this._updateDialog({ busy: true, error: "" });
    try {
      if (task.completion_schema.outcomes.length && !this._dialog.selectedOutcome) {
        throw new Error("Select an outcome before completing the task");
      }

      const outcomeMetadata = this._buildOutcomeMetadata(task);
      await this._resolveTask(task, {
        action: "complete",
        outcome_id: this._dialog.selectedOutcome || undefined,
        outcome_metadata: outcomeMetadata,
        notes: this._dialog.notes || undefined,
      });
      this._closeDialog();
    } catch (error) {
      this._updateDialog({
        busy: false,
        error: error instanceof Error ? error.message : "Unable to complete task",
      });
    }
  }

  _attachCardEvents() {
    this.shadowRoot
      .querySelector("[data-refresh]")
      ?.addEventListener("click", () => this._loadTasks());

    this.shadowRoot.querySelectorAll("reptilecare-task-list-item").forEach((item) => {
      item.addEventListener("reptilecare:complete", (event) => {
        this._openDialog(event.detail.task);
      });
      item.addEventListener("reptilecare:details", (event) => {
        this._openDialog(event.detail.task);
      });
      item.addEventListener("reptilecare:skip", (event) => {
        void this._handleSkip(event.detail.task);
      });
      item.addEventListener("reptilecare:quick-complete", (event) => {
        void this._handleQuickComplete(event.detail.task, event.detail.outcomeId);
      });
    });

    const dialog = this.shadowRoot.querySelector("reptilecare-task-completion-dialog");
    dialog?.addEventListener("reptilecare:dialog-close", () => this._closeDialog());
    dialog?.addEventListener("reptilecare:dialog-submit", () => {
      void this._submitDialog();
    });
    dialog?.addEventListener("reptilecare:dialog-change", (event) =>
      this._updateDialog(event.detail),
    );
    dialog?.addEventListener("reptilecare:dialog-field-change", (event) =>
      this._updateDialogField(event.detail.fieldId, event.detail.value),
    );
  }

  _renderTaskSections() {
    if (this._loading) {
      return `
        <div class="message loading" role="status" aria-live="polite">
          <strong>Loading today’s care…</strong>
          <p>Checking what ${escapeHtml(resolveReptileLabel(this._config, this._matchingEntityStates()))} needs right now.</p>
        </div>
      `;
    }

    if (this._error && this._tasks.length === 0) {
      return `
        <div class="message error" role="alert">
          <strong>We couldn’t load today’s care.</strong>
          <p>${escapeHtml(this._error)}</p>
        </div>
      `;
    }

    if (!this._tasks.length) {
      const summary = summarizeTaskList(
        this._tasks,
        this._config,
        this._matchingEntityStates(),
      );
      return `
        <div class="message empty" role="status" aria-live="polite">
          <strong>${escapeHtml(summary.heading)}</strong>
          <p>${escapeHtml(summary.body)}</p>
        </div>
      `;
    }

    return groupTasks(this._tasks)
      .map(
        (section) => `
          <section class="task-group" aria-labelledby="group-${escapeHtml(section.key)}">
            <div class="group-header">
              <h3 id="group-${escapeHtml(section.key)}" class="group-title">${escapeHtml(section.label)}</h3>
              <span class="group-count">${section.tasks.length}</span>
            </div>
            <div class="task-list">
              ${section.tasks
                .map(() => "<reptilecare-task-list-item></reptilecare-task-list-item>")
                .join("")}
            </div>
          </section>
        `,
      )
      .join("");
  }

  _renderSummaryPanel() {
    const summary = summarizeTaskList(this._tasks, this._config, this._matchingEntityStates());
    return `
      <section class="summary-panel ${escapeHtml(summary.tone)}" aria-live="polite">
        <p class="summary-eyebrow">${escapeHtml(summary.heading)}</p>
        <p class="summary-body">${escapeHtml(summary.body)}</p>
      </section>
    `;
  }

  _renderHeader() {
    const header = buildHeaderContext(this._tasks, this._config, this._matchingEntityStates());
    return `
      <div class="header">
        <div class="title-wrap">
          <div class="title-row">
            <h2 class="title">🦎 ${escapeHtml(header.reptileLabel)}</h2>
            <span class="status-chip ${escapeHtml(header.statusTone)}">${escapeHtml(header.statusLabel)}</span>
          </div>
          ${
            header.species
              ? `<p class="subtitle">${escapeHtml(header.species)}</p>`
              : ""
          }
        </div>
        <div class="header-meta">
          <div class="count-chip">
            <span class="count-value">${header.pendingCount}</span>
            <span class="count-label">${header.pendingCount === 1 ? "task" : "tasks"}</span>
          </div>
          ${
            header.overdueCount > 0
              ? `<span class="alert-chip">${header.overdueCount} overdue</span>`
              : ""
          }
          <button class="icon-button" type="button" data-refresh aria-label="Refresh today's care" ${this._loading ? "disabled" : ""}>
            <ha-icon icon="mdi:refresh"></ha-icon>
          </button>
        </div>
      </div>
    `;
  }

  _render() {
    if (!this.shadowRoot || !this._config) {
      return;
    }

    this.shadowRoot.innerHTML = `
      <style>
        ${sharedCardStyles}

        ha-card {
          overflow: hidden;
        }

        .shell {
          display: grid;
          gap: 1rem;
          padding: 1rem;
        }

        .header {
          display: grid;
          gap: 0.9rem;
        }

        .title-wrap {
          display: grid;
          gap: 0.25rem;
        }

        .title-row {
          display: flex;
          flex-wrap: wrap;
          gap: 0.55rem;
          align-items: center;
        }

        .title {
          margin: 0;
          font-size: 1.2rem;
          line-height: 1.25;
        }

        .subtitle {
          margin: 0;
          color: var(--secondary-text-color);
          font-size: 0.94rem;
        }

        .header-meta {
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          gap: 0.65rem;
        }

        .count-chip,
        .status-chip,
        .alert-chip {
          display: inline-flex;
          align-items: center;
          min-height: 2rem;
          border-radius: 999px;
          padding: 0.2rem 0.75rem;
          font-size: 0.82rem;
          font-weight: 700;
        }

        .count-chip {
          gap: 0.45rem;
          background: color-mix(in srgb, var(--secondary-background-color) 72%, transparent);
        }

        .count-value {
          font-size: 0.98rem;
          color: var(--primary-text-color);
        }

        .count-label {
          color: var(--secondary-text-color);
        }

        .status-chip {
          background: color-mix(in srgb, var(--primary-color) 12%, transparent);
          color: var(--primary-color);
        }

        .status-chip.overdue {
          background: color-mix(in srgb, var(--error-color) 14%, transparent);
          color: var(--error-color);
        }

        .status-chip.due {
          background: color-mix(in srgb, var(--warning-color, #f0b400) 18%, transparent);
          color: color-mix(in srgb, var(--warning-color, #f0b400) 88%, black);
        }

        .status-chip.clear {
          background: color-mix(in srgb, var(--success-color, #2e7d32) 16%, transparent);
          color: var(--success-color, #2e7d32);
        }

        .alert-chip {
          background: color-mix(in srgb, var(--error-color) 14%, transparent);
          color: var(--error-color);
        }

        .icon-button {
          border: none;
          width: 2.5rem;
          height: 2.5rem;
          border-radius: 999px;
          cursor: pointer;
          background: color-mix(in srgb, var(--secondary-background-color) 78%, transparent);
          color: var(--secondary-text-color);
        }

        .summary-panel {
          display: grid;
          gap: 0.35rem;
          padding: 1rem 1.05rem;
          border-radius: 18px;
          background:
            linear-gradient(
              140deg,
              color-mix(in srgb, var(--primary-color) 10%, transparent),
              color-mix(in srgb, var(--secondary-background-color) 78%, transparent)
            );
        }

        .summary-panel.overdue {
          background:
            linear-gradient(
              140deg,
              color-mix(in srgb, var(--error-color) 18%, transparent),
              color-mix(in srgb, var(--secondary-background-color) 70%, transparent)
            );
        }

        .summary-panel.clear {
          background:
            linear-gradient(
              140deg,
              color-mix(in srgb, var(--success-color, #2e7d32) 16%, transparent),
              color-mix(in srgb, var(--secondary-background-color) 76%, transparent)
            );
        }

        .summary-eyebrow,
        .summary-body {
          margin: 0;
        }

        .summary-eyebrow {
          font-size: 1rem;
          font-weight: 700;
          line-height: 1.35;
        }

        .summary-body {
          color: var(--secondary-text-color);
          line-height: 1.45;
        }

        .message {
          border-radius: 18px;
          padding: 1.1rem;
          background: color-mix(in srgb, var(--secondary-background-color) 82%, transparent);
          color: var(--secondary-text-color);
        }

        .message strong,
        .message p {
          margin: 0;
        }

        .message p {
          margin-top: 0.45rem;
        }

        .message.error {
          background: color-mix(in srgb, var(--error-color) 14%, transparent);
          color: var(--error-color);
        }

        .message.empty {
          text-align: center;
          padding-block: 1.3rem;
        }

        .task-group {
          display: grid;
          gap: 0.8rem;
        }

        .group-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 0.75rem;
        }

        .group-title {
          margin: 0;
          font-size: 0.98rem;
          line-height: 1.3;
        }

        .group-count {
          min-width: 1.8rem;
          min-height: 1.8rem;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          border-radius: 999px;
          padding: 0 0.45rem;
          background: color-mix(in srgb, var(--secondary-background-color) 72%, transparent);
          color: var(--secondary-text-color);
          font-weight: 700;
          font-size: 0.82rem;
        }

        .task-list {
          display: grid;
          gap: 0.85rem;
        }

        @media (max-width: 720px) {
          .shell {
            padding: 0.9rem;
          }

          .header-meta {
            justify-content: space-between;
          }

          .icon-button {
            margin-left: auto;
          }
        }
      </style>
      <ha-card aria-busy="${this._loading ? "true" : "false"}">
        <div class="shell">
          <p class="sr-only" aria-live="polite">${escapeHtml(this._announcer)}</p>
          ${this._renderHeader()}
          ${this._renderSummaryPanel()}
          ${this._renderTaskSections()}
          <reptilecare-task-completion-dialog></reptilecare-task-completion-dialog>
        </div>
      </ha-card>
    `;

    const renderedTaskItems = Array.from(
      this.shadowRoot.querySelectorAll("reptilecare-task-list-item"),
    );
    const orderedTasks = groupTasks(this._tasks).flatMap((section) => section.tasks);
    renderedTaskItems.forEach((item, index) => {
      item.task = orderedTasks[index];
      item.locale = this._hass?.locale?.language ?? "en";
    });

    const dialog = this.shadowRoot.querySelector("reptilecare-task-completion-dialog");
    if (dialog) {
      dialog.locale = this._hass?.locale?.language ?? "en";
      dialog.state = this._dialog;
    }

    this._attachCardEvents();
  }
}

if (!customElements.get("reptilecare-todays-care-card")) {
  customElements.define("reptilecare-todays-care-card", ReptileCareTodaysCareCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.find((entry) => entry.type === cardMetadata().type)) {
  window.customCards.push(cardMetadata());
}
