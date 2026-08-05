import "../components/task-list-item.js";
import "../dialogs/task-completion-dialog.js";

import { validateTodaysCareConfig } from "../models/todays-care-model.js";
import { fetchTodaysCareTasks, resolveTask } from "../services/reptilecare-api.js";
import { sharedCardStyles } from "../styles/reptilecare-styles.js";
import { escapeHtml } from "../utils/html.js";

const RELEVANT_DOMAINS = new Set(["sensor", "binary_sensor", "button"]);

function cardMetadata() {
  return {
    type: "reptilecare-todays-care",
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
    this._busyTaskId = null;
    this._refreshHandle = null;
    this._entitySignature = "";
    this._dialog = defaultDialogState();
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
    return Math.max(2, this._tasks.length * 2);
  }

  getGridOptions() {
    return {
      columns: 6,
      min_rows: 2,
      rows: Math.max(2, this._tasks.length * 2),
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

  async _loadTasks({ silent = false } = {}) {
    if (!this._hass || !this._config) {
      return;
    }

    if (!silent) {
      this._loading = true;
      this._error = "";
      this._render();
    }

    try {
      this._tasks = await fetchTodaysCareTasks(this._hass, this._config);
      this._error = "";
      this._entitySignature = this._computeEntitySignature();
    } catch (error) {
      this._error = error instanceof Error ? error.message : "Unable to load care tasks";
    } finally {
      this._loading = false;
      this._render();
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

  async _resolveTask(task, payload) {
    this._busyTaskId = task.task_id;
    this._error = "";
    this._render();

    try {
      await resolveTask(this._hass, task.task_id, payload);
      await this._loadTasks({ silent: true });
    } catch (error) {
      this._error = error instanceof Error ? error.message : "Unable to resolve task";
      throw error;
    } finally {
      this._busyTaskId = null;
      this._render();
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
        this._handleSkip(event.detail.task);
      });
      item.addEventListener("reptilecare:quick-complete", (event) => {
        this._handleQuickComplete(event.detail.task, event.detail.outcomeId);
      });
    });

    const dialog = this.shadowRoot.querySelector("reptilecare-task-completion-dialog");
    dialog?.addEventListener("reptilecare:dialog-close", () => this._closeDialog());
    dialog?.addEventListener("reptilecare:dialog-submit", () => this._submitDialog());
    dialog?.addEventListener("reptilecare:dialog-change", (event) =>
      this._updateDialog(event.detail),
    );
    dialog?.addEventListener("reptilecare:dialog-field-change", (event) =>
      this._updateDialogField(event.detail.fieldId, event.detail.value),
    );
  }

  _renderTaskList() {
    if (this._loading) {
      return `<div class="message">Loading today's care…</div>`;
    }

    if (this._error) {
      return `<div class="message error" role="alert">${escapeHtml(this._error)}</div>`;
    }

    if (!this._tasks.length) {
      return `<div class="message empty">No care due.</div>`;
    }

    return `
      <div class="task-list">
        ${this._tasks.map(() => `<reptilecare-task-list-item></reptilecare-task-list-item>`).join("")}
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
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 0.75rem;
        }

        .title-wrap {
          display: grid;
          gap: 0.2rem;
        }

        .title {
          margin: 0;
          font-size: 1.12rem;
          line-height: 1.3;
        }

        .subtitle {
          margin: 0;
          color: var(--secondary-text-color);
          font-size: 0.92rem;
        }

        .icon-button {
          border: none;
          width: 2.4rem;
          height: 2.4rem;
          border-radius: 999px;
          cursor: pointer;
          background: color-mix(in srgb, var(--secondary-background-color) 78%, transparent);
          color: var(--secondary-text-color);
        }

        .message {
          border-radius: 18px;
          padding: 1rem;
          background: color-mix(in srgb, var(--secondary-background-color) 82%, transparent);
          color: var(--secondary-text-color);
        }

        .message.error {
          background: color-mix(in srgb, var(--error-color) 14%, transparent);
          color: var(--error-color);
        }

        .message.empty {
          text-align: center;
          padding-block: 1.25rem;
        }

        .task-list {
          display: grid;
          gap: 0.85rem;
        }
      </style>
      <ha-card>
        <div class="shell">
          <div class="header">
            <div class="title-wrap">
              <h2 class="title">${escapeHtml(this._config.title)}</h2>
              <p class="subtitle">Actionable care tasks for one reptile</p>
            </div>
            <button class="icon-button" type="button" data-refresh aria-label="Refresh today's care">
              <ha-icon icon="mdi:refresh"></ha-icon>
            </button>
          </div>
          ${this._renderTaskList()}
          <reptilecare-task-completion-dialog></reptilecare-task-completion-dialog>
        </div>
      </ha-card>
    `;

    const items = this.shadowRoot.querySelectorAll("reptilecare-task-list-item");
    items.forEach((item, index) => {
      item.task = this._tasks[index];
      item.busy = this._busyTaskId === this._tasks[index].task_id;
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
