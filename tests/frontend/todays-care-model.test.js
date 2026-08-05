import { describe, expect, it } from "vitest";

import {
  cardType,
  isQuickActionTask,
  normalizeTask,
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
  });
});

