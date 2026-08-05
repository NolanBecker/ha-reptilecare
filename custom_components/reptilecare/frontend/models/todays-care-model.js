const CARD_TYPE = "custom:reptilecare-todays-care";

function assertText(value, field) {
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`${field} must be a non-empty string`);
  }
  return value.trim();
}

export function validateTodaysCareConfig(config) {
  if (!config || typeof config !== "object") {
    throw new Error("Card configuration is required");
  }

  const reptileId =
    "reptile_id" in config && config.reptile_id != null
      ? assertText(config.reptile_id, "reptile_id")
      : null;
  const slug =
    "slug" in config && config.slug != null
      ? assertText(config.slug, "slug")
      : null;

  if ((reptileId === null) === (slug === null)) {
    throw new Error("Provide exactly one of reptile_id or slug");
  }

  return {
    type: CARD_TYPE,
    reptile_id: reptileId,
    slug,
    title:
      typeof config.title === "string" && config.title.trim() !== ""
        ? config.title.trim()
        : "Today's Care",
  };
}

export function isQuickActionTask(task) {
  const outcomes = task.completion_schema?.outcomes ?? [];
  const requiredFields = (task.completion_schema?.context_fields ?? []).filter(
    (field) => field.required,
  );
  return outcomes.length > 0 && outcomes.length <= 3 && requiredFields.length === 0;
}

export function normalizeTask(task) {
  const completionSchema = task.completion_schema ?? {
    outcomes: [],
    context_fields: [],
  };
  return {
    ...task,
    presentation: task.presentation ?? {
      title: task.task_template_id,
      description: null,
      icon: "mdi:clipboard-text-clock-outline",
      priority: "normal",
      care_plan_display_name: task.care_plan_id,
    },
    completion_schema: completionSchema,
    quick_actions_enabled: isQuickActionTask({ completion_schema: completionSchema }),
  };
}

export function cardType() {
  return CARD_TYPE;
}

