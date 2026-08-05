function formatAbsoluteDateTime(value, locale) {
  const date = new Date(value);
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function formatRelative(value, locale) {
  const dueAt = new Date(value).getTime();
  const now = Date.now();
  const minutes = Math.round((dueAt - now) / 60000);
  const formatter = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });

  if (Math.abs(minutes) < 60) {
    return formatter.format(minutes, "minute");
  }

  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 48) {
    return formatter.format(hours, "hour");
  }

  const days = Math.round(hours / 24);
  return formatter.format(days, "day");
}

export function formatDueDetails(value, locale = "en") {
  return {
    absolute: formatAbsoluteDateTime(value, locale),
    relative: formatRelative(value, locale),
  };
}

