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
  future: 3,
  snoozed: 4,
};
const TASK_PRIORITY_WEIGHT = {
  urgent: 0,
  high: 1,
  normal: 2,
  low: 3,
};
const STATUS_LABELS = {
  clear: "All Caught Up",
  due: "Due Today",
  overdue: "Overdue",
  upcoming: "Upcoming",
};
const GROUP_LABELS = {
  overdue: "Overdue",
  due: "Due Now",
  upcoming_today: "Upcoming Today",
  future: "Future",
};

function assertText(value, field) {
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`${field} must be a non-empty string`);
  }
  return value.trim();
}

function titleCaseSlug(slug) {
  return slug
    .split(/[-_]+/u)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function parseDate(value) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function isSameLocalDay(left, right) {
  return (
    left.getFullYear() === right.getFullYear()
    && left.getMonth() === right.getMonth()
    && left.getDate() === right.getDate()
  );
}

function deriveDueState(task, now = new Date()) {
  if (task.due_state === "overdue" || task.due_state === "due" || task.due_state === "snoozed") {
    return task.due_state;
  }

  const dueAt = parseDate(task.due_at);
  if (!dueAt) {
    return "future";
  }
  if (dueAt.getTime() < now.getTime()) {
    return isSameLocalDay(dueAt, now) ? "due" : "overdue";
  }
  if (isSameLocalDay(dueAt, now)) {
    return "upcoming";
  }
  return "future";
}

function deriveUrgencyGroup(task, now = new Date()) {
  const dueState = deriveDueState(task, now);
  if (dueState === "overdue") {
    return "overdue";
  }
  if (dueState === "due") {
    return "due";
  }
  if (dueState === "upcoming") {
    return "upcoming_today";
  }
  return "future";
}

function taskSortKey(task, now = new Date()) {
  const dueAt = parseDate(task.due_at);
  const dueValue = dueAt ? dueAt.getTime() : Number.MAX_SAFE_INTEGER;
  const dueState = deriveDueState(task, now);
  return [
    DUE_STATE_PRIORITY[dueState] ?? 99,
    dueValue,
    TASK_PRIORITY_WEIGHT[task.presentation.priority] ?? 99,
    task.presentation.title,
    task.task_id,
  ];
}

function entityString(stateObj, ...keys) {
  for (const key of keys) {
    const value = stateObj?.attributes?.[key];
    if (typeof value === "string" && value.trim() !== "") {
      return value.trim();
    }
  }
  return null;
}

export function validateTodaysCareConfig(config) {
  if (!config || typeof config !== "object") {
    throw new Error("Card configuration is required");
  }

  const reptileId = "reptile_id" in config && config.reptile_id != null
    ? assertText(config.reptile_id, "reptile_id")
    : null;
  const slug = "slug" in config && config.slug != null
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

export function resolveReptileLabel(config, entityStates = []) {
  for (const stateObj of entityStates) {
    const friendlyName = entityString(stateObj, "friendly_name");
    if (!friendlyName) {
      continue;
    }

    const suffix = KNOWN_ENTITY_NAME_SUFFIXES.find((candidate) => friendlyName.endsWith(candidate));
    if (suffix) {
      return friendlyName.slice(0, -suffix.length) || friendlyName;
    }
    return friendlyName;
  }

  if (config.slug) {
    return titleCaseSlug(config.slug);
  }
  return "This reptile";
}

export function resolveSpeciesLabel(entityStates = []) {
  for (const stateObj of entityStates) {
    const species = entityString(
      stateObj,
      "species",
      "species_name",
      "species_display_name",
      "model",
    );
    if (species) {
      return species;
    }
  }
  return null;
}

export function normalizeTask(task, now = new Date()) {
  const completionSchema = task.completion_schema ?? {
    outcomes: [],
    context_fields: [],
  };
  const dueState = deriveDueState(task, now);
  const urgencyGroup = deriveUrgencyGroup({ ...task, due_state: dueState }, now);
  return {
    ...task,
    presentation: {
      title: task.presentation?.title ?? task.task_template_id,
      description: task.presentation?.description ?? null,
      icon: task.presentation?.icon ?? "mdi:clipboard-text-clock-outline",
      priority: task.presentation?.priority ?? "normal",
      care_plan_display_name:
        task.presentation?.care_plan_display_name ?? task.care_plan_id,
    },
    completion_schema: completionSchema,
    due_state: dueState,
    urgency_group: urgencyGroup,
    quick_actions_enabled:
      typeof task.quick_actions_enabled === "boolean"
        ? task.quick_actions_enabled
        : isQuickActionTask({ completion_schema: completionSchema }),
    ui: {
      busy: Boolean(task.ui?.busy),
      error: task.ui?.error ?? "",
      phase: task.ui?.phase ?? "idle",
    },
  };
}

export function sortTasks(tasks, now = new Date()) {
  return [...tasks].sort((left, right) => {
    const leftKey = taskSortKey(left, now);
    const rightKey = taskSortKey(right, now);
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

export function groupTasks(tasks, now = new Date()) {
  const buckets = {
    overdue: [],
    due: [],
    upcoming_today: [],
    future: [],
  };
  for (const task of tasks) {
    buckets[deriveUrgencyGroup(task, now)].push(task);
  }
  return Object.entries(buckets)
    .filter(([, items]) => items.length > 0)
    .map(([key, items]) => ({
      key,
      label: GROUP_LABELS[key],
      tasks: sortTasks(items, now),
    }));
}

export function buildHeaderContext(tasks, config, entityStates = [], now = new Date()) {
  const reptileLabel = resolveReptileLabel(config, entityStates);
  const species = resolveSpeciesLabel(entityStates);
  const overdueCount = tasks.filter((task) => deriveDueState(task, now) === "overdue").length;
  const dueCount = tasks.filter((task) => deriveDueState(task, now) === "due").length;
  const pendingCount = tasks.length;

  let statusTone = "clear";
  if (overdueCount > 0) {
    statusTone = "overdue";
  } else if (dueCount > 0) {
    statusTone = "due";
  } else if (pendingCount > 0) {
    statusTone = "upcoming";
  }

  return {
    reptileLabel,
    species,
    pendingCount,
    overdueCount,
    dueCount,
    statusTone,
    statusLabel: STATUS_LABELS[statusTone],
  };
}

export function summarizeTaskList(tasks, config, entityStates = [], now = new Date()) {
  const header = buildHeaderContext(tasks, config, entityStates, now);
  const upcomingTodayCount = tasks.filter(
    (task) => deriveUrgencyGroup(task, now) === "upcoming_today",
  ).length;

  if (tasks.length === 0) {
    return {
      tone: "clear",
      heading: `✨ ${header.reptileLabel} is all caught up!`,
      body: "No care is currently due.",
      statusLabel: STATUS_LABELS.clear,
    };
  }

  if (header.overdueCount > 0) {
    return {
      tone: "overdue",
      heading: `⚠️ ${header.reptileLabel} needs attention`,
      body:
        header.overdueCount === 1
          ? "1 care task is overdue."
          : `${header.overdueCount} care tasks are overdue.`,
      statusLabel: STATUS_LABELS.overdue,
    };
  }

  if (header.dueCount > 0) {
    return {
      tone: "due",
      heading: `${header.reptileLabel} has care ready`,
      body:
        header.dueCount === 1
          ? "1 task is ready to complete."
          : `${header.dueCount} tasks are ready to complete.`,
      statusLabel: STATUS_LABELS.due,
    };
  }

  if (upcomingTodayCount > 0) {
    return {
      tone: "upcoming",
      heading: `🎉 Great work!`,
      body: "Everything scheduled for today has been completed.",
      statusLabel: STATUS_LABELS.upcoming,
    };
  }

  return {
    tone: "upcoming",
    heading: `${header.reptileLabel} has future care queued`,
    body:
      tasks.length === 1
        ? "1 task is scheduled next."
        : `${tasks.length} tasks are scheduled next.`,
    statusLabel: STATUS_LABELS.upcoming,
  };
}

export function applyTaskUiState(tasks, taskId, patch, now = new Date()) {
  return sortTasks(
    tasks.map((task) => (
      task.task_id === taskId
        ? normalizeTask(
          {
            ...task,
            ui: {
              ...task.ui,
              ...patch,
            },
          },
          now,
        )
        : task
    )),
    now,
  );
}

export function settleInsertedTasks(tasks, now = new Date()) {
  return sortTasks(
    tasks.map((task) => normalizeTask({ ...task, ui: { ...task.ui, phase: "idle" } }, now)),
    now,
  );
}

export function mergeResolutionResult(tasks, resolvedTaskId, response, now = new Date()) {
  const remaining = tasks.filter((task) => task.task_id !== resolvedTaskId);
  const knownTaskIds = new Set(remaining.map((task) => task.task_id));
  const followUps = [
    ...(response.created_follow_up_tasks ?? []),
    ...(response.existing_follow_up_tasks ?? []),
  ]
    .filter((task) => task?.task_id && !knownTaskIds.has(task.task_id))
    .map((task) => normalizeTask({ ...task, ui: { phase: "entering" } }, now));

  return sortTasks([...remaining, ...followUps], now);
}

export function cardType() {
  return CARD_TYPE;
}
