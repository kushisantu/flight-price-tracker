import AirportField from "./AirportField";
import { addDays, parseISODate, todayISO, toISO } from "../format";

const CABINS = [
  ["economy", "Economy"],
  ["premium", "Premium economy"],
  ["business", "Business"],
  ["first", "First"],
];

export default function SearchForm({ value, onChange, onSubmit, compact = false, busy = false }) {
  const samePlace = value.origin?.code && value.origin.code === value.destination?.code;
  const missingReturn = value.tripType === "round" && !value.returnDate;

  function patch(partial) {
    onChange({ ...value, ...partial });
  }

  function swap() {
    patch({ origin: value.destination, destination: value.origin });
  }

  return (
    <form
      className={compact ? "search compact" : "search"}
      onSubmit={(event) => {
        event.preventDefault();
        if (!samePlace && !missingReturn) onSubmit(value);
      }}
    >
      <div className="trip-types" role="radiogroup" aria-label="Trip type">
        {[["round", "Round trip"], ["oneway", "One way"]].map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={value.tripType === id ? "chip on" : "chip"}
            onClick={() => patch({ tripType: id })}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="search-grid">
        <AirportField label="From" place={value.origin} onSelect={(origin) => patch({ origin })} />
        <button type="button" className="swap" onClick={swap} aria-label="Swap origin and destination">
          ⇄
        </button>
        <AirportField label="To" place={value.destination} onSelect={(destination) => patch({ destination })} />
        <label className="field">
          <span>Departure</span>
          <input
            type="date"
            value={value.departDate}
            min={todayISO()}
            onChange={(event) => {
              const departDate = event.target.value;
              const partial = { departDate };
              if (value.returnDate && departDate >= value.returnDate) {
                partial.returnDate = toISO(addDays(parseISODate(departDate), 7));
              }
              patch(partial);
            }}
          />
        </label>
        {value.tripType === "round" && (
          <label className="field">
            <span>Return</span>
            <input
              type="date"
              value={value.returnDate || ""}
              min={value.departDate}
              onChange={(event) => patch({ returnDate: event.target.value })}
            />
          </label>
        )}
        <label className="field">
          <span>Passengers</span>
          <select value={value.passengers} onChange={(event) => patch({ passengers: Number(event.target.value) })}>
            {[1, 2, 3, 4, 5, 6].map((count) => (
              <option key={count} value={count}>{count}</option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Cabin</span>
          <select value={value.cabin} onChange={(event) => patch({ cabin: event.target.value })}>
            {CABINS.map(([id, label]) => (
              <option key={id} value={id}>{label}</option>
            ))}
          </select>
        </label>
        <button className="primary" type="submit" disabled={busy || samePlace || missingReturn || !value.origin || !value.destination}>
          {busy ? "Searching…" : "Search"}
        </button>
      </div>
      {samePlace && <p className="form-error">Choose two different places.</p>}
    </form>
  );
}
