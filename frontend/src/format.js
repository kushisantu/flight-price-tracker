export function parseISODate(iso) {
  const [year, month, day] = iso.split("T")[0].split("-").map(Number);
  return new Date(year, month - 1, day);
}

export function toISO(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function addDays(date, days) {
  const next = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  next.setDate(next.getDate() + days);
  return next;
}

export function daysBetween(startIso, endIso) {
  const ms = parseISODate(endIso) - parseISODate(startIso);
  return Math.round(ms / 86400000);
}

export function formatLong(iso) {
  return parseISODate(iso).toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

export function formatShort(iso) {
  return parseISODate(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

export function formatMonth(monthIso) {
  const [year, month] = monthIso.split("-").map(Number);
  return new Date(year, month - 1, 1).toLocaleDateString("en-US", {
    month: "long",
    year: "numeric",
  });
}

export function shiftMonth(monthIso, delta) {
  const [year, month] = monthIso.split("-").map(Number);
  const next = new Date(year, month - 1 + delta, 1);
  return `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, "0")}`;
}

export function money(value) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatDuration(minutes) {
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  if (!mins) return `${hours}h`;
  return `${hours}h ${String(mins).padStart(2, "0")}m`;
}

export function formatTime(iso) {
  const [hours, minutes] = iso.split("T")[1].split(":").map(Number);
  const suffix = hours < 12 ? "AM" : "PM";
  const hour12 = hours % 12 || 12;
  return `${hour12}:${String(minutes).padStart(2, "0")} ${suffix}`;
}

export function dayOffset(departAt, arriveAt) {
  const start = parseISODate(departAt);
  const end = parseISODate(arriveAt);
  return Math.round((end - start) / 86400000);
}

export function departHour(iso) {
  return Number(iso.split("T")[1].slice(0, 2));
}

export function todayISO() {
  return toISO(new Date());
}

export function defaultCriteria() {
  let depart = addDays(new Date(), 36);
  while (depart.getDay() !== 2) depart = addDays(depart, 1);
  return {
    origin: {
      code: "NYC",
      type: "city",
      city: "New York",
      name: "All airports",
      country: "United States",
    },
    destination: {
      code: "LON",
      type: "city",
      city: "London",
      name: "All airports",
      country: "United Kingdom",
    },
    departDate: toISO(depart),
    returnDate: toISO(addDays(depart, 7)),
    tripType: "round",
    passengers: 1,
    cabin: "economy",
  };
}

export function fromApiCriteria(criteria) {
  return {
    origin: criteria.origin,
    destination: criteria.destination,
    departDate: criteria.depart_date,
    returnDate: criteria.return_date,
    tripType: criteria.trip_type,
    passengers: criteria.passengers,
    cabin: criteria.cabin,
  };
}
