import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import {
  dayOffset,
  daysBetween,
  departHour,
  formatDuration,
  formatLong,
  formatMonth,
  formatTime,
  money,
  parseISODate,
  shiftMonth,
  todayISO,
} from "../format";
import PriceChart from "./PriceChart";
import SearchForm from "./SearchForm";

const CABIN_LABEL = {
  economy: "Economy",
  premium: "Premium economy",
  business: "Business",
  first: "First",
};

function scoreFlights(flights) {
  if (!flights.length) return [];
  const prices = flights.map((flight) => flight.price);
  const durations = flights.map((flight) => flight.total_duration_minutes);
  const lowPrice = Math.min(...prices);
  const highPrice = Math.max(...prices);
  const lowDuration = Math.min(...durations);
  const highDuration = Math.max(...durations);
  return flights.map((flight) => ({
    ...flight,
    score:
      ((flight.price - lowPrice) / (highPrice - lowPrice || 1)) * 0.58
      + ((flight.total_duration_minutes - lowDuration) / (highDuration - lowDuration || 1)) * 0.42
      - (flight.stops === 0 ? 0.06 : 0),
  }));
}

export default function Results({
  criteria,
  result,
  loading,
  error,
  priceCap,
  notice,
  onChange,
  onSearch,
  onCreateAlert,
}) {
  const [stops, setStops] = useState("any");
  const [airlines, setAirlines] = useState([]);
  const [sort, setSort] = useState("best");
  const [maxPrice, setMaxPrice] = useState(priceCap);
  const [times, setTimes] = useState({ morning: true, afternoon: true, evening: true });
  const [draft, setDraft] = useState(null);
  const [target, setTarget] = useState(0);
  const [email, setEmail] = useState("");
  const [alertError, setAlertError] = useState("");
  const [saving, setSaving] = useState(false);
  const [showCalendar, setShowCalendar] = useState(false);
  const [month, setMonth] = useState(criteria.departDate.slice(0, 7));
  const [calendarDays, setCalendarDays] = useState([]);
  const [calendarLoading, setCalendarLoading] = useState(false);

  const flights = result?.flights || [];
  const priceCeiling = flights.length ? Math.max(...flights.map((flight) => flight.price)) : 0;

  useEffect(() => {
    setStops("any");
    setAirlines([]);
    setSort("best");
    setMaxPrice(priceCap && flights.some((flight) => flight.price <= priceCap) ? priceCap : null);
    setTimes({ morning: true, afternoon: true, evening: true });
    setMonth(criteria.departDate.slice(0, 7));
  }, [result, priceCap, criteria.departDate]);

  useEffect(() => {
    if (!showCalendar) return undefined;
    let ignore = false;
    setCalendarLoading(true);
    const nights = criteria.tripType === "round" ? Math.max(1, daysBetween(criteria.departDate, criteria.returnDate)) : 0;
    api.calendar({
      origin: criteria.origin.code,
      destination: criteria.destination.code,
      month,
      nights,
      cabin: criteria.cabin,
      tripType: criteria.tripType,
    }).then((data) => {
      if (!ignore) setCalendarDays(data.days);
    }).catch(() => {
      if (!ignore) setCalendarDays([]);
    }).finally(() => {
      if (!ignore) setCalendarLoading(false);
    });
    return () => {
      ignore = true;
    };
  }, [showCalendar, month, criteria]);

  const airlineOptions = useMemo(() => {
    const map = new Map();
    const priced = flights.filter((flight) => {
      if (stops === "nonstop") return flight.stops === 0;
      if (stops === "one") return flight.stops <= 1;
      return true;
    });
    priced.forEach((flight) => {
      const current = map.get(flight.airline_code);
      if (!current || flight.price < current.price) {
        map.set(flight.airline_code, { code: flight.airline_code, name: flight.airline_name, price: flight.price, color: flight.airline_color });
      }
    });
    return [...map.values()].sort((a, b) => a.price - b.price);
  }, [flights, stops]);

  const visible = useMemo(() => {
    const filtered = flights.filter((flight) => {
      if (stops === "nonstop" && flight.stops !== 0) return false;
      if (stops === "one" && flight.stops > 1) return false;
      if (airlines.length && !airlines.includes(flight.airline_code)) return false;
      if (maxPrice && flight.price > maxPrice) return false;
      const hour = departHour(flight.legs[0].depart_at);
      const bucket = hour < 12 ? "morning" : hour < 17 ? "afternoon" : "evening";
      if (!times[bucket]) return false;
      return true;
    });
    const scored = scoreFlights(filtered);
    const sorted = [...scored];
    if (sort === "cheap") sorted.sort((a, b) => a.price - b.price);
    else if (sort === "fast") sorted.sort((a, b) => a.total_duration_minutes - b.total_duration_minutes);
    else if (sort === "depart") sorted.sort((a, b) => a.legs[0].depart_at.localeCompare(b.legs[0].depart_at));
    else sorted.sort((a, b) => a.score - b.score);
    return sorted;
  }, [flights, stops, airlines, maxPrice, times, sort]);

  const cheapestId = visible.reduce((best, flight) => (!best || flight.price < best.price ? flight : best), null)?.id;
  const fastestId = visible.reduce((best, flight) => (!best || flight.total_duration_minutes < best.total_duration_minutes ? flight : best), null)?.id;
  const bestId = visible[0]?.id;
  const insight = result?.insight;

  function shiftDates(day) {
    const length = criteria.tripType === "round" ? daysBetween(criteria.departDate, criteria.returnDate) : 0;
    const next = {
      ...criteria,
      departDate: day.date,
      returnDate: criteria.tripType === "round" ? day.return_date : criteria.returnDate,
    };
    if (criteria.tripType === "round" && !day.return_date) {
      const depart = parseISODate(day.date);
      depart.setDate(depart.getDate() + length);
      const year = depart.getFullYear();
      const monthNumber = String(depart.getMonth() + 1).padStart(2, "0");
      const dateNumber = String(depart.getDate()).padStart(2, "0");
      next.returnDate = `${year}-${monthNumber}-${dateNumber}`;
    }
    onSearch(next);
  }

  async function saveAlert(event) {
    event.preventDefault();
    setSaving(true);
    setAlertError("");
    try {
      await onCreateAlert({
        origin: criteria.origin.code,
        destination: criteria.destination.code,
        depart_date: criteria.departDate,
        return_date: criteria.tripType === "oneway" ? null : criteria.returnDate,
        passengers: Number(criteria.passengers),
        cabin: criteria.cabin,
        airline_code: draft.airline_code,
        stops: draft.stops,
        target_price: Number(target),
        email: email.trim() || null,
      });
      setDraft(null);
      setEmail("");
    } catch (err) {
      setAlertError(err.message);
    } finally {
      setSaving(false);
    }
  }

  const pricedDays = calendarDays.filter((day) => day.price);
  const low = pricedDays.length ? Math.min(...pricedDays.map((day) => day.price)) : 0;
  const high = pricedDays.length ? Math.max(...pricedDays.map((day) => day.price)) : 1;
  const firstWeekday = calendarDays[0] ? parseISODate(calendarDays[0].date).getDay() : 0;

  return (
    <div className="results">
      <SearchForm value={criteria} onChange={onChange} onSubmit={onSearch} compact busy={loading} />
      <p className="route-title">
        {criteria.origin.city} to {criteria.destination.city}
        {" · "}
        {formatLong(criteria.departDate)}
        {criteria.tripType === "round" && criteria.returnDate ? ` – ${formatLong(criteria.returnDate)}` : ""}
        {" · "}
        {criteria.passengers} passenger{criteria.passengers > 1 ? "s" : ""}
        {" · "}
        {CABIN_LABEL[criteria.cabin]}
      </p>
      {notice && <p className="notice">{notice}</p>}
      {error && <p className="form-error">{error}</p>}

      {result && !loading && (
        <>
          <div className="strip-row">
            <div className="strip">
              {(result.date_strip || []).map((day) => (
                <button
                  key={day.date}
                  type="button"
                  className={day.selected ? "day-price on" : "day-price"}
                  onClick={() => shiftDates(day)}
                >
                  <span>{formatLong(day.date)}</span>
                  <strong>{money(day.price)}</strong>
                </button>
              ))}
            </div>
            <button type="button" className="secondary" onClick={() => setShowCalendar((open) => !open)}>
              {showCalendar ? "Hide calendar" : "Whole month"}
            </button>
          </div>

          {showCalendar && (
            <section className="panel calendar-panel">
              <div className="calendar-nav">
                <button type="button" onClick={() => setMonth(shiftMonth(month, -1))} disabled={month <= todayISO().slice(0, 7)}>Previous</button>
                <strong>{formatMonth(month)}</strong>
                <button type="button" onClick={() => setMonth(shiftMonth(month, 1))}>Next</button>
              </div>
              {calendarLoading ? <p className="muted">Loading the month…</p> : (
                <div className="calendar">
                  {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((label) => (
                    <span key={label} className="dow">{label}</span>
                  ))}
                  {Array.from({ length: firstWeekday }).map((_, index) => <span key={`pad-${index}`} />)}
                  {calendarDays.map((day) => {
                    const tone = day.price == null ? 0 : (day.price - low) / (high - low || 1);
                    const selected = day.date === criteria.departDate;
                    return (
                      <button
                        key={day.date}
                        type="button"
                        className={selected ? "cal-day selected" : "cal-day"}
                        disabled={day.price == null}
                        style={day.price == null ? undefined : { background: `hsl(${140 - tone * 135} 62% 90%)` }}
                        onClick={() => shiftDates(day)}
                      >
                        <span>{Number(day.date.slice(-2))}</span>
                        {day.price != null && <strong>{money(day.price)}</strong>}
                      </button>
                    );
                  })}
                </div>
              )}
            </section>
          )}

          {insight && (
            <section className={`banner ${insight.level}`}>
              <div>
                <p className="level">{insight.title}</p>
                <p>{insight.summary}</p>
                <p>{insight.advice}</p>
              </div>
              {insight.alternative && (
                <button
                  type="button"
                  className="secondary"
                  onClick={() => shiftDates({
                    date: insight.alternative.depart_date,
                    return_date: insight.alternative.return_date,
                  })}
                >
                  {formatLong(insight.alternative.depart_date)} · {money(insight.alternative.price)}
                </button>
              )}
            </section>
          )}

          <section className="panel history-panel">
            <div className="panel-head">
              <h2>How this fare has moved</h2>
              <p>Cheapest price for these exact dates. Low {money(insight?.low || 0)} · Average {money(insight?.average || 0)} · High {money(insight?.high || 0)}</p>
            </div>
            <PriceChart history={result.history} />
          </section>
        </>
      )}

      <div className="results-layout">
        <aside className="filters">
          <h2>Filters</h2>
          <fieldset>
            <legend>Stops</legend>
            {[
              ["any", "Any"],
              ["nonstop", "Nonstop"],
              ["one", "1 stop or fewer"],
            ].map(([id, label]) => (
              <label key={id}><input type="radio" name="stops" checked={stops === id} onChange={() => setStops(id)} /> {label}</label>
            ))}
          </fieldset>
          <fieldset>
            <legend>Departure</legend>
            {[
              ["morning", "Morning"],
              ["afternoon", "Afternoon"],
              ["evening", "Evening"],
            ].map(([id, label]) => (
              <label key={id}>
                <input
                  type="checkbox"
                  checked={times[id]}
                  onChange={() => setTimes((current) => ({ ...current, [id]: !current[id] }))}
                /> {label}
              </label>
            ))}
          </fieldset>
          <fieldset>
            <legend>Airlines</legend>
            {airlineOptions.map((airline) => (
              <label key={airline.code}>
                <input
                  type="checkbox"
                  checked={airlines.includes(airline.code)}
                  onChange={() => setAirlines((current) => (
                    current.includes(airline.code)
                      ? current.filter((code) => code !== airline.code)
                      : [...current, airline.code]
                  ))}
                />
                <i style={{ background: airline.color }} />
                {airline.name}
                <em>{money(airline.price)}</em>
              </label>
            ))}
          </fieldset>
          {priceCeiling > 0 && (
            <label className="slider">
              <span>Max price {maxPrice ? money(maxPrice) : "any"}</span>
              <input
                type="range"
                min={Math.min(...flights.map((flight) => flight.price))}
                max={priceCeiling}
                value={maxPrice || priceCeiling}
                onChange={(event) => {
                  const next = Number(event.target.value);
                  setMaxPrice(next >= priceCeiling ? null : next);
                }}
              />
            </label>
          )}
          <button
            type="button"
            className="textish"
            onClick={() => {
              setStops("any");
              setAirlines([]);
              setMaxPrice(null);
              setTimes({ morning: true, afternoon: true, evening: true });
            }}
          >
            Reset filters
          </button>
        </aside>

        <div className="list">
          <div className="sortbar">
            <span>{loading ? "Searching…" : `${visible.length} flight${visible.length === 1 ? "" : "s"}`}</span>
            <div>
              {[["best", "Best"], ["cheap", "Cheapest"], ["fast", "Fastest"], ["depart", "Departure"]].map(([id, label]) => (
                <button key={id} type="button" className={sort === id ? "chip on" : "chip"} onClick={() => setSort(id)}>{label}</button>
              ))}
            </div>
          </div>
          {loading && [0, 1, 2, 3].map((key) => <div key={key} className="skeleton" />)}
          {!loading && visible.length === 0 && <p className="empty">No flights match these filters.</p>}
          {visible.map((flight) => (
            <article key={flight.id} className="flight">
              <div className="badges">
                {flight.id === bestId && sort === "best" && <span>Best</span>}
                {flight.id === cheapestId && <span className="green">Cheapest</span>}
                {flight.id === fastestId && <span>Fastest</span>}
              </div>
              <div className="flight-body">
              <div className="flight-main">
                {flight.legs.map((leg) => {
                  const offset = dayOffset(leg.depart_at, leg.arrive_at);
                  return (
                    <div className="leg" key={`${leg.depart_at}-${leg.origin}-${leg.destination}`}>
                      <div className="carrier">
                        <span className="logo" style={{ background: leg.airline_color }}>{leg.airline_code}</span>
                        <div>
                          <strong>{leg.airline_name}</strong>
                          <small>{leg.flight_number} · {leg.aircraft}</small>
                        </div>
                      </div>
                      <div className="when">
                        <strong>{formatTime(leg.depart_at)}</strong>
                        <span>{leg.origin}</span>
                      </div>
                      <div className="path">
                        <span>{formatDuration(leg.duration_minutes)}</span>
                        <div className="rail" />
                        <span>
                          {leg.stops === 0 ? "Nonstop" : `1 stop · ${leg.stop_city}`}
                          {leg.layover_minutes > 0 ? ` ${formatDuration(leg.layover_minutes)}` : ""}
                        </span>
                      </div>
                      <div className="when arrive">
                        <strong>
                          {formatTime(leg.arrive_at)}
                          {offset > 0 && <sup>+{offset}</sup>}
                        </strong>
                        <span>{leg.destination}</span>
                      </div>
                    </div>
                  );
                })}
                <p className="fine">{flight.bag_note} · {flight.emissions_kg} kg CO₂</p>
              </div>
              <div className="flight-price">
                <strong className={flight.id === cheapestId ? "cheap-price" : ""}>{money(flight.price)}</strong>
                <span>per person</span>
                {criteria.passengers > 1 && <span>{money(flight.total_price)} total</span>}
                <button
                  type="button"
                  className="secondary"
                  onClick={() => {
                    setDraft(flight);
                    setTarget(Math.max(50, Math.round(flight.price * 0.9)));
                    setAlertError("");
                  }}
                >
                  Set alert
                </button>
              </div>
              </div>
            </article>
          ))}
        </div>
      </div>

      {draft && (
        <div className="modal-back" onClick={() => setDraft(null)}>
          <form className="modal" onClick={(event) => event.stopPropagation()} onSubmit={saveAlert}>
            <h2>Track this fare</h2>
            <p>
              {criteria.origin.city} to {criteria.destination.city}. This {draft.stops === 0 ? "nonstop" : "one-stop"} {draft.airline_name} fare is {money(draft.price)} per person right now.
            </p>
            <label className="field">
              <span>Alert me at or below</span>
              <input type="number" min="20" max="20000" value={target} onChange={(event) => setTarget(event.target.value)} />
            </label>
            <label className="field">
              <span>Email (optional, saved only)</span>
              <input type="email" value={email} placeholder="you@email.com" onChange={(event) => setEmail(event.target.value)} />
            </label>
            <p className="fine">The alert updates when you open Alerts or search this route. Email is stored for later, not sent yet.</p>
            {alertError && <p className="form-error">{alertError}</p>}
            <div className="modal-actions">
              <button type="button" className="secondary" onClick={() => setDraft(null)}>Cancel</button>
              <button className="primary" type="submit" disabled={saving}>{saving ? "Saving…" : "Create alert"}</button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
