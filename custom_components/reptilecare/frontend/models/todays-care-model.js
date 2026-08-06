const CARD_TYPE = "custom:reptilecare-todays-care-card";
const KNOWN_ENTITY_NAME_SUFFIXES = [
  " Pending Care Tasks",
  " Next Care Task",
  " Last Care Event",
  " Care Due",
  " Overdue Care",
  " Pending Care",
  " Generate Tasks",
];
const DUE_STATE_PRIORITY = {
  overdue: 0,
  due: 1,
  upcoming: 2,
  snoozed: 3,
};
const TASK_PRIORITY_WEIGHT = {
  urgent: 0,
  high: 1,
  normal: 2,
  low: 3,
};

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

function titleCaseSlug(slug) {
  return slug
    .split(/[-_]+/u)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function resolveReptileLabel(config, entityStates = []) {
  for (const stateObj of entityStates) {
    const friendlyName = stateObj?.attributes?.friendly_name;
    if (typeof friendlyName !== "string" || friendlyName.trim() === "") {
      continue;
    }

    const trimmed = friendlyName.trim();
    const suffix = KNOWN_ENTITY_NAME_SUFFIXES.find((candidate) =>
      trimmed.endsWith(candidate),
    );
    if (suffix) {
      return trimmed.slice(0, -suffix.length) || trimmed;
    }
    return trimmed;
  }

  if (config.slug) {
    return titleCaseSlug(config.slug);
  }
  return "This reptile";
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
    due_state: task.due_state ?? "upcoming",
    quick_actions_enabled: isQuickActionTask({ completion_schema: completionSchema }),
  };
}

function taskSortKey(task) {
  const dueAt = typeof task.due_at === "string" ? Date.parse(task.due_at) : Number.NaN;
  return [
    DUE_STATE_PRIORITY[task.due_state] ?? 99,
    Number.isNaN(dueAt) ? Number.MAX_SAFE_INTEGER : dueAt,
    TASK_PRIORITY_WEIGHT[task.presentation.priority] ?? 99,
    task.presentation.title,
    task.task_id,
  ];
}

export function sortTasks(tasks) {
  return [...tasks].sort((left, right) => {
    const leftKey = taskSortKey(left);
    const rightKey = taskSortKey(right);
    for (let index = 0; index < leftKey.length; index += 1) {
      if (leftKey[index] < rightKey[index]) {
        return -1;
      }
      if (leftKey[index] > rightKey[index]) {
        return 1;
      }
    }
    return 0;
  });
}

export function summarizeTaskList(tasks, config, entityStates = []) {
  const reptileLabel = resolveReptileLabel(config, entityStates);
  const overdueCount = tasks.filter((task) => task.due_state === "overdue").length;
  const dueCount = tasks.filter((task) => task.due_state === "due").length;

  if (tasks.length === 0) {
    return {
      tone: "clear",
      heading: `✨ ${reptileLabel} is all caught up!`,
      body: "No care is currently due.",
    };
  }

  if (overdueCount > 0) {
    return {
      tone: "warning",
      heading: `⚠️ ${reptileLabel} needs attention`,
      body:
        overdueCount === 1
          ? "1 care task is overdue."
          : `${overdueCount} care tasks are overdue.`,
    };
  }

  if (dueCount > 0) {
    return {
      tone: "active",
      heading: `${reptileLabel} has care ready`,
      body:
        dueCount === 1
          ? "1 task is ready to complete."
          : `${dueCount} tasks are ready to complete.`,
    };
  }

  return {
    tone: "upcoming",
    heading: `${reptileLabel} has upcoming care`,
    body:
      tasks.length === 1
        ? "1 task is scheduled next."
        : `${tasks.length} tasks are scheduled next.`,
  };
}

export function cardType() {
  return CARD_TYPE;
}

