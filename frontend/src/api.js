async function request(path, options = {}, attempt = 0) {
  let response;
  try {
    response = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
  } catch {
    if (attempt < 3) {
      await new Promise((resolve) => setTimeout(resolve, 700));
      return request(path, options, attempt + 1);
    }
    throw new Error("Cannot reach the API. Start the backend on port 8000.");
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    let message = "Request failed";
    if (typeof data.detail === "string") message = data.detail;
    else if (Array.isArray(data.detail)) message = data.detail.map((item) => item.msg).join(" ");
    throw new Error(message);
  }
  return data;
}

export function toSearchBody(criteria) {
  return {
    origin: criteria.origin.code,
    destination: criteria.destination.code,
    depart_date: criteria.departDate,
    return_date: criteria.tripType === "oneway" ? null : criteria.returnDate,
    trip_type: criteria.tripType,
    passengers: Number(criteria.passengers),
    cabin: criteria.cabin,
  };
}

function outlookQuery(criteria) {
  const body = toSearchBody(criteria);
  const params = new URLSearchParams({
    origin: body.origin,
    destination: body.destination,
    depart_date: body.depart_date,
    trip_type: body.trip_type,
    passengers: String(body.passengers),
    cabin: body.cabin,
  });
  if (body.return_date) params.set("return_date", body.return_date);
  return params.toString();
}

export const api = {
  health: () => request("/api/health"),
  airports: (q) => request(`/api/airports?q=${encodeURIComponent(q)}`),
  search: (criteria) => request("/api/search", { method: "POST", body: JSON.stringify(toSearchBody(criteria)) }),
  outlook: (criteria) => request(`/api/outlook?${outlookQuery(criteria)}`),
  calendar: ({ origin, destination, month, nights, cabin, tripType }) => {
    const params = new URLSearchParams({
      origin,
      destination,
      month,
      nights: String(nights),
      cabin,
      trip_type: tripType,
    });
    return request(`/api/calendar?${params.toString()}`);
  },
  deals: (origin) => request(`/api/deals?origin=${encodeURIComponent(origin)}`),
  smart: (query, origin) => request("/api/smart-search", {
    method: "POST",
    body: JSON.stringify({ query, origin }),
  }),
  alerts: () => request("/api/alerts"),
  createAlert: (body) => request("/api/alerts", { method: "POST", body: JSON.stringify(body) }),
  deleteAlert: (id) => request(`/api/alerts/${id}`, { method: "DELETE" }),
};
