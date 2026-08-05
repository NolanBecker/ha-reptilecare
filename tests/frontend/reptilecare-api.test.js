import { describe, expect, it, vi } from "vitest";

import {
  fetchTodaysCareTasks,
  resolveTask,
} from "../../custom_components/reptilecare/frontend/services/reptilecare-api.js";

describe("reptilecare api wrapper", () => {
  it("loads tasks through the public get_tasks service response", async () => {
    const callApi = vi.fn().mockResolvedValue({
      service_response: {
        tasks: [
          {
            task_id: "task-1",
            task_template_id: "builtin:feed_fruit",
            care_plan_id: "plan-1",
            due_at: "2026-08-05T12:00:00+00:00",
            due_state: "due",
            completion_schema: { outcomes: [], context_fields: [] },
          },
        ],
      },
    });
    const hass = { callApi };

    const tasks = await fetchTodaysCareTasks(hass, { slug: "pixel" });

    expect(callApi).toHaveBeenCalledWith(
      "POST",
      "services/reptilecare/get_tasks?return_response",
      {
        slug: "pixel",
        include_details: true,
        include_terminal: false,
      },
    );
    expect(tasks[0].task_id).toBe("task-1");
    expect(tasks[0].presentation.title).toBe("builtin:feed_fruit");
  });

  it("resolves a task through the public resolve_task service", async () => {
    const callApi = vi.fn().mockResolvedValue({
      service_response: { task: { task_id: "task-1", status: "completed" } },
    });
    const hass = { callApi };

    const response = await resolveTask(hass, "task-1", {
      action: "complete",
      outcome_id: "ate_normally",
    });

    expect(callApi).toHaveBeenCalledWith(
      "POST",
      "services/reptilecare/resolve_task?return_response",
      {
        task_id: "task-1",
        action: "complete",
        outcome_id: "ate_normally",
      },
    );
    expect(response.task.status).toBe("completed");
  });
});

