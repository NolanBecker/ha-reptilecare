// @vitest-environment jsdom

import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

function buildTask(overrides = {}) {
  return {
    task_id: overrides.task_id ?? "task-1",
    task_template_id: overrides.task_template_id ?? "builtin:feed_fruit",
    care_plan_id: overrides.care_plan_id ?? "plan-1",
    due_at: overrides.due_at ?? "2026-08-06T10:00:00-05:00",
    due_state: overrides.due_state ?? "due",
    presentation: {
      title: overrides.title ?? "Feed Fruit",
      description: overrides.description ?? "Offer fruit mix",
      icon: "mdi:food-apple",
      priority: overrides.priority ?? "normal",
      care_plan_display_name: "Feeding",
    },
    completion_schema: overrides.completion_schema ?? {
      outcomes: [
        { outcome_id: "ate_normally", display_name: "Ate Normally" },
        { outcome_id: "ate_partially", display_name: "Ate Partially" },
        { outcome_id: "refused", display_name: "Refused" },
      ],
      context_fields: [],
    },
  };
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
}

async function createCard({
  tasks = [buildTask()],
  resolveResponse,
  resolveError,
  reducedMotion = false,
} = {}) {
  let currentTasks = tasks;
  const callApi = vi.fn(async (_method, path, payload) => {
    if (path.includes("get_tasks")) {
      return { service_response: { tasks: currentTasks } };
    }
    if (path.includes("resolve_task")) {
      if (resolveError) {
        throw new Error(resolveError);
      }
      if (resolveResponse) {
        currentTasks = resolveResponse.nextTasks ?? currentTasks;
        return { service_response: resolveResponse.response };
      }
      return { service_response: { task: { task_id: payload.task_id, status: "completed" } } };
    }
    throw new Error(`Unexpected path: ${path}`);
  });

  const hass = {
    locale: { language: "en" },
    states: {
      "sensor.pixel_pending_care_tasks": {
        entity_id: "sensor.pixel_pending_care_tasks",
        state: String(currentTasks.length),
        last_updated: "2026-08-06T10:00:00-05:00",
        attributes: {
          reptile_id: "reptile-1",
          slug: "pixel",
          friendly_name: "Pixel Pending Care Tasks",
          species: "Gargoyle Gecko",
        },
      },
    },
    callApi,
  };

  window.matchMedia = vi.fn().mockImplementation((query) => ({
    matches: reducedMotion && query === "(prefers-reduced-motion: reduce)",
    media: query,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent() {
      return false;
    },
  }));

  const element = document.createElement("reptilecare-todays-care-card");
  element.setConfig({ slug: "pixel" });
  element.hass = hass;
  document.body.appendChild(element);
  await flush();
  await flush();
  return { element, hass, callApi };
}

beforeAll(async () => {
  window.customCards = [];
  if (globalThis.HTMLDialogElement) {
    HTMLDialogElement.prototype.showModal = function showModal() {
      this.open = true;
    };
    HTMLDialogElement.prototype.close = function close() {
      this.open = false;
    };
  }

  await import("../../custom_components/reptilecare/frontend/cards/todays-care-card.js");
});

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.runOnlyPendingTimers();
  vi.useRealTimers();
  document.body.innerHTML = "";
  vi.restoreAllMocks();
});

describe("Today's Care card", () => {
  it("renders quick action buttons for simple tasks", async () => {
    const { element } = await createCard();
    const item = element.shadowRoot.querySelector("reptilecare-task-list-item");

    expect(item).not.toBeNull();
    expect(
      item.shadowRoot.querySelectorAll(".quick-action-button").length,
    ).toBe(3);
  });

  it("opens the dialog for tasks that require structured fields", async () => {
    const { element } = await createCard({
      tasks: [
        buildTask({
          completion_schema: {
            outcomes: [
              { outcome_id: "completed", display_name: "Completed" },
              { outcome_id: "partial", display_name: "Partial" },
              { outcome_id: "skipped", display_name: "Skipped" },
            ],
            context_fields: [
              {
                field_id: "grams",
                display_name: "Weight",
                field_type: "number",
                required: true,
              },
            ],
          },
        }),
      ],
    });

    const item = element.shadowRoot.querySelector("reptilecare-task-list-item");
    item.shadowRoot.querySelector("[data-action='complete']").click();
    await flush();

    const dialog = element.shadowRoot.querySelector("reptilecare-task-completion-dialog");
    expect(dialog.shadowRoot.querySelector("dialog").open).toBe(true);
    expect(dialog.shadowRoot.textContent).toContain("Structured fields");
    expect(dialog.shadowRoot.textContent).toContain("Weight");
  });

  it("optimistically disables one task, removes it, and inserts follow-up tasks", async () => {
    const { element } = await createCard({
      resolveResponse: {
        nextTasks: [
          buildTask({
            task_id: "task-2",
            task_template_id: "builtin:remove_food",
            title: "Remove Food",
            due_at: "2026-08-06T14:00:00-05:00",
          }),
        ],
        response: {
          task: { task_id: "task-1", status: "completed" },
          care_event: { event_id: "event-1" },
          created_follow_up_tasks: [
            {
              task_id: "task-2",
              task_template_id: "builtin:remove_food",
              care_plan_id: "plan-1",
              due_at: "2026-08-06T14:00:00-05:00",
            },
          ],
          existing_follow_up_tasks: [],
          warnings: [],
        },
      },
    });

    const item = element.shadowRoot.querySelector("reptilecare-task-list-item");
    item.shadowRoot.querySelector(".quick-action-button").click();
    const busyItem = element.shadowRoot.querySelector("reptilecare-task-list-item");
    expect(busyItem.task.ui.busy).toBe(true);
    expect(
      busyItem.shadowRoot.querySelector(".quick-action-button").hasAttribute("disabled"),
    ).toBe(true);
    await flush();
    await vi.runAllTimersAsync();
    await flush();

    const items = element.shadowRoot.querySelectorAll("reptilecare-task-list-item");
    expect(items.length).toBe(1);
    expect(items[0].task.task_id).toBe("task-2");
  });

  it("restores task state and shows an inline error when the backend rejects a resolution", async () => {
    const { element } = await createCard({
      resolveError: "Resolution rejected",
    });

    const item = element.shadowRoot.querySelector("reptilecare-task-list-item");
    item.shadowRoot.querySelector(".quick-action-button").click();
    await flush();
    await flush();

    const failedItem = element.shadowRoot.querySelector("reptilecare-task-list-item");
    expect(element.shadowRoot.textContent).toContain("Resolution rejected");
    expect(failedItem.task.task_id).toBe("task-1");
    expect(failedItem.shadowRoot.querySelector(".inline-error").textContent).toContain(
      "Resolution rejected",
    );
  });

  it("respects reduced motion by applying the final optimistic state immediately", async () => {
    const { element } = await createCard({
      reducedMotion: true,
      resolveResponse: {
        nextTasks: [],
        response: {
          task: { task_id: "task-1", status: "completed" },
          care_event: { event_id: "event-1" },
          created_follow_up_tasks: [],
          existing_follow_up_tasks: [],
          warnings: [],
        },
      },
    });

    const item = element.shadowRoot.querySelector("reptilecare-task-list-item");
    item.shadowRoot.querySelector(".quick-action-button").click();
    await flush();
    await flush();

    expect(
      element.shadowRoot.querySelectorAll("reptilecare-task-list-item").length,
    ).toBe(0);
  });

  it("renders accessible header controls and live regions", async () => {
    const { element } = await createCard();

    expect(element.shadowRoot.querySelector(".status-chip").textContent).toContain(
      "Due Today",
    );
    expect(
      element.shadowRoot.querySelector("[data-refresh]").getAttribute("aria-label"),
    ).toBe("Refresh today's care");
    expect(
      element.shadowRoot.querySelector(".sr-only").getAttribute("aria-live"),
    ).toBe("polite");
    expect(element.shadowRoot.textContent).toContain("Gargoyle Gecko");
  });

  it("renders a friendly empty state", async () => {
    const { element } = await createCard({ tasks: [] });

    expect(element.shadowRoot.textContent).toContain("Pixel is all caught up");
    expect(element.shadowRoot.textContent).toContain("No care is currently due.");
  });

  it("includes a mobile layout media query", async () => {
    const { element } = await createCard();

    expect(element.shadowRoot.innerHTML).toContain("@media (max-width: 720px)");
  });
});
