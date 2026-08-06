import { describe, expect, it } from "vitest";

import {
  cardType,
  isQuickActionTask,
  normalizeTask,
  resolveReptileLabel,
  sortTasks,
  summarizeTaskList,
  validateTodaysCareConfig,
} from "../../custom_components/reptilecare/frontend/models/todays-care-model.js";

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
    });

    expect(normalized.presentation.title).toBe("builtin:feed_fruit");
    expect(normalized.presentation.icon).toBe("mdi:clipboard-text-clock-outline");
    expect(normalized.quick_actions_enabled).toBe(false);
    expect(normalized.due_state).toBe("upcoming");
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

describe("sortTasks", () => {
  it("orders overdue before due and upcoming tasks", () => {
    const tasks = sortTasks([
      normalizeTask({
        task_id: "upcoming",
        task_template_id: "t3",
        care_plan_id: "plan-1",
        due_at: "2026-08-06T15:00:00+00:00",
        due_state: "upcoming",
        presentation: { title: "Upcoming", priority: "normal" },
        completion_schema: { outcomes: [], context_fields: [] },
      }),
      normalizeTask({
        task_id: "overdue",
        task_template_id: "t1",
        care_plan_id: "plan-1",
        due_at: "2026-08-06T09:00:00+00:00",
        due_state: "overdue",
        presentation: { title: "Overdue", priority: "normal" },
        completion_schema: { outcomes: [], context_fields: [] },
      }),
      normalizeTask({
        task_id: "due",
        task_template_id: "t2",
        care_plan_id: "plan-1",
        due_at: "2026-08-06T11:00:00+00:00",
        due_state: "due",
        presentation: { title: "Due", priority: "normal" },
        completion_schema: { outcomes: [], context_fields: [] },
      }),
    ]);

    expect(tasks.map((task) => task.task_id)).toEqual(["overdue", "due", "upcoming"]);
  });
});

describe("summarizeTaskList", () => {
  it("returns a friendly clear state when no tasks exist", () => {
    expect(summarizeTaskList([], { slug: "pixel", reptile_id: null }, [])).toEqual({
      tone: "clear",
      heading: "✨ Pixel is all caught up!",
      body: "No care is currently due.",
    });
  });

  it("returns a warning state when overdue tasks exist", () => {
    const tasks = [
      normalizeTask({
        task_id: "task-1",
        task_template_id: "builtin:feed_fruit",
        care_plan_id: "plan-1",
        due_at: "2026-08-06T09:00:00+00:00",
        due_state: "overdue",
        completion_schema: { outcomes: [], context_fields: [] },
      }),
    ];

    expect(summarizeTaskList(tasks, { slug: "pixel", reptile_id: null }, [])).toEqual({
      tone: "warning",
      heading: "⚠️ Pixel needs attention",
      body: "1 care task is overdue.",
    });
  });
});

