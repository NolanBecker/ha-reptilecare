import { describe, expect, it } from "vitest";

import {
  applyTaskUiState,
  buildHeaderContext,
  cardType,
  groupTasks,
  isQuickActionTask,
  mergeResolutionResult,
  normalizeTask,
  resolveReptileLabel,
  sortTasks,
  summarizeTaskList,
  validateTodaysCareConfig,
} from "../../custom_components/reptilecare/frontend/models/todays-care-model.js";

const NOW = new Date("2026-08-06T12:00:00-05:00");

function task(overrides = {}) {
  return normalizeTask({
    task_id: overrides.task_id ?? "task-1",
    task_template_id: overrides.task_template_id ?? "builtin:feed_fruit",
    care_plan_id: overrides.care_plan_id ?? "plan-1",
    due_at: overrides.due_at ?? "2026-08-06T15:00:00-05:00",
    due_state: overrides.due_state,
    presentation: {
      title: overrides.title ?? "Feed Fruit",
      priority: overrides.priority ?? "normal",
      icon: "mdi:food-apple",
      care_plan_display_name: "Feeding",
      description: overrides.description ?? null,
    },
    completion_schema: overrides.completion_schema ?? {
      outcomes: [],
      context_fields: [],
    },
    ui: overrides.ui,
  }, NOW);
}

describe("validateTodaysCareConfig", () => {
  it("accepts a slug-based configuration", () => {
    expect(validateTodaysCareConfig({ slug: "pixel" })).toEqual({
      type: cardType(),
      reptile_id: null,
      slug: "pixel",
      title: "Today's Care",
    });
  });

  it("rejects missing or conflicting identifiers", () => {
    expect(() => validateTodaysCareConfig({})).toThrow(
      "Provide exactly one of reptile_id or slug",
    );
    expect(() =>
      validateTodaysCareConfig({
        reptile_id: "550e8400-e29b-41d4-a716-446655440000",
        slug: "pixel",
      }),
    ).toThrow("Provide exactly one of reptile_id or slug");
  });
});

describe("quick actions", () => {
  it("enables quick actions for three or fewer outcomes with no required fields", () => {
    expect(
      isQuickActionTask({
        completion_schema: {
          outcomes: [{}, {}, {}],
          context_fields: [{ required: false }],
        },
      }),
    ).toBe(true);
  });

  it("disables quick actions when required fields exist", () => {
    expect(
      isQuickActionTask({
        completion_schema: {
          outcomes: [{}, {}],
          context_fields: [{ required: true }],
        },
      }),
    ).toBe(false);
  });
});

describe("normalizeTask", () => {
  it("fills missing presentation details with safe defaults", () => {
    const normalized = normalizeTask({
      task_id: "task-1",
      task_template_id: "builtin:feed_fruit",
      care_plan_id: "plan-1",
      completion_schema: { outcomes: [], context_fields: [] },
      due_at: "2026-08-07T10:00:00-05:00",
    }, NOW);

    expect(normalized.presentation.title).toBe("builtin:feed_fruit");
    expect(normalized.presentation.icon).toBe("mdi:clipboard-text-clock-outline");
    expect(normalized.quick_actions_enabled).toBe(false);
    expect(normalized.due_state).toBe("future");
  });
});

describe("resolveReptileLabel", () => {
  it("uses entity friendly names when available", () => {
    expect(
      resolveReptileLabel(
        { reptile_id: "reptile-1", slug: null },
        [{ attributes: { friendly_name: "Pixel Pending Care Tasks" } }],
      ),
    ).toBe("Pixel");
  });

  it("falls back to title-cased slug", () => {
    expect(resolveReptileLabel({ reptile_id: null, slug: "sir_pixel" }, [])).toBe(
      "Sir Pixel",
    );
  });
});

describe("sorting and grouping", () => {
  it("orders overdue before due, today, and future tasks", () => {
    const tasks = sortTasks([
      task({
        task_id: "future",
        due_at: "2026-08-07T15:00:00-05:00",
        due_state: "future",
        title: "Future",
      }),
      task({
        task_id: "overdue",
        due_at: "2026-08-05T09:00:00-05:00",
        due_state: "overdue",
        title: "Overdue",
      }),
      task({
        task_id: "due",
        due_at: "2026-08-06T11:00:00-05:00",
        due_state: "due",
        title: "Due",
      }),
      task({
        task_id: "today",
        due_at: "2026-08-06T18:00:00-05:00",
        title: "Today",
      }),
    ], NOW);

    expect(tasks.map((item) => item.task_id)).toEqual([
      "overdue",
      "due",
      "today",
      "future",
    ]);
  });

  it("groups tasks by urgency buckets", () => {
    const sections = groupTasks([
      task({ task_id: "overdue", due_at: "2026-08-05T09:00:00-05:00", due_state: "overdue" }),
      task({ task_id: "due", due_at: "2026-08-06T11:00:00-05:00", due_state: "due" }),
      task({ task_id: "today", due_at: "2026-08-06T18:00:00-05:00" }),
      task({ task_id: "future", due_at: "2026-08-07T09:00:00-05:00" }),
    ], NOW);

    expect(sections.map((section) => section.key)).toEqual([
      "overdue",
      "due",
      "upcoming_today",
      "future",
    ]);
  });
});

describe("summary and header", () => {
  it("returns a friendly clear state when no tasks exist", () => {
    expect(summarizeTaskList([], { slug: "pixel", reptile_id: null }, [], NOW)).toEqual({
      tone: "clear",
      heading: "✨ Pixel is all caught up!",
      body: "No care is currently due.",
      statusLabel: "All Caught Up",
    });
  });

  it("returns a warning state when overdue tasks exist", () => {
    const tasks = [task({ task_id: "task-1", due_at: "2026-08-05T09:00:00-05:00", due_state: "overdue" })];

    expect(summarizeTaskList(tasks, { slug: "pixel", reptile_id: null }, [], NOW)).toEqual({
      tone: "overdue",
      heading: "⚠️ Pixel needs attention",
      body: "1 care task is overdue.",
      statusLabel: "Overdue",
    });
  });

  it("builds a header context with count and status", () => {
    const header = buildHeaderContext(
      [
        task({ task_id: "task-1", due_state: "due", due_at: "2026-08-06T10:00:00-05:00" }),
        task({ task_id: "task-2", due_at: "2026-08-06T16:00:00-05:00" }),
      ],
      { slug: "pixel", reptile_id: null },
      [{ attributes: { friendly_name: "Pixel Pending Care Tasks", species: "Gargoyle Gecko" } }],
      NOW,
    );

    expect(header.reptileLabel).toBe("Pixel");
    expect(header.species).toBe("Gargoyle Gecko");
    expect(header.pendingCount).toBe(2);
    expect(header.statusLabel).toBe("Due Today");
  });
});

describe("local task state", () => {
  it("applies task ui updates without disturbing ordering", () => {
    const tasks = applyTaskUiState(
      [task({ task_id: "a" }), task({ task_id: "b", due_at: "2026-08-05T09:00:00-05:00", due_state: "overdue" })],
      "a",
      { busy: true, error: "oops" },
      NOW,
    );

    expect(tasks.find((item) => item.task_id === "a").ui.busy).toBe(true);
    expect(tasks.find((item) => item.task_id === "a").ui.error).toBe("oops");
    expect(tasks.map((item) => item.task_id)).toEqual(["b", "a"]);
  });

  it("merges follow-up tasks from a resolution response", () => {
    const tasks = mergeResolutionResult(
      [task({ task_id: "task-1" })],
      "task-1",
      {
        created_follow_up_tasks: [
          {
            task_id: "task-2",
            task_template_id: "builtin:remove_food",
            care_plan_id: "plan-1",
            due_at: "2026-08-06T17:00:00-05:00",
          },
        ],
        existing_follow_up_tasks: [],
      },
      NOW,
    );

    expect(tasks.map((item) => item.task_id)).toEqual(["task-2"]);
    expect(tasks[0].ui.phase).toBe("entering");
  });
});
