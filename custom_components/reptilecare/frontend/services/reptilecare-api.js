import { normalizeTask } from "../models/todays-care-model.js";

const DOMAIN = "reptilecare";

async function callResponseService(hass, service, data) {
  const response = await hass.callApi(
    "POST",
    `services/${DOMAIN}/${service}?return_response`,
    data,
  );
  return response.service_response ?? response;
}

function identifierPayload(config) {
  return config.reptile_id
    ? { reptile_id: config.reptile_id }
    : { slug: config.slug };
}

export async function fetchTodaysCareTasks(hass, config) {
  const response = await callResponseService(hass, "get_tasks", {
    ...identifierPayload(config),
    include_details: true,
    include_terminal: false,
  });
  return (response.tasks ?? []).map(normalizeTask);
}

export async function resolveTask(hass, taskId, payload) {
  return callResponseService(hass, "resolve_task", {
    task_id: taskId,
    ...payload,
  });
}

