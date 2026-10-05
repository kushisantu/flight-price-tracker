import { useEffect, useState } from "react";
import { api } from "../api";
import { formatLong, money } from "../format";
import AirportField from "./AirportField";
import PriceChart from "./PriceChart";

const STATUS = {
  hit: "At or below your target",
  rose: "Hit your target earlier, then rose",
  watching: "Watching",
  paused: "Paused",
};

export default function Alerts({ onCount, onOpenRoute }) {
  const [alerts, setAlerts] = useState([]);
  const [selected, setSelected] = useState(null);
  const [outlook, setOutlook] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({
    origin: { code: "NYC", city: "New York", name: "All airports", country: "United States", type: "city" },
    destination: { code: "LON", city: "London", name: "All airports", country: "United Kingdom", type: "city" },
    departDate: "",
    returnDate: "",
    target: 500,
    email: "",
    cabin: "economy",
  });

  async function load() {
    setLoading(true);
    try {
      const data = await api.alerts();
      setAlerts(data.alerts);
      onCount(data.alerts.length);
      setSelected((current) => data.alerts.find((alert) => alert.id === current?.id) || data.alerts[0] || null);
      setError("");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (!selected) {
      setOutlook(null);
      return undefined;
    }
    let ignore = false;
    api.outlook({
      origin: selected.origin,
      destination: selected.destination,
      departDate: selected.depart_date,
      returnDate: selected.return_date,
      tripType: selected.return_date ? "round" : "oneway",
      passengers: selected.passengers,
      cabin: selected.cabin,
    }).then((data) => {
      if (!ignore) setOutlook(data);
    }).catch(() => {
      if (!ignore) setOutlook(null);
    });
    return () => {
      ignore = true;
    };
  }, [selected]);

  async function create(event) {
    event.preventDefault();
    setError("");
    try {
      await api.createAlert({
        origin: form.origin.code,
        destination: form.destination.code,
        depart_date: form.departDate,
        return_date: form.returnDate || null,
        passengers: 1,
        cabin: form.cabin,
        target_price: Number(form.target),
        email: form.email.trim() || null,
      });
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function remove(id) {
    await api.deleteAlert(id);
    await load();
  }

  return (
    <div className="alerts-page">
      <section className="panel">
        <h2>New alert</h2>
        <p className="fine">Prices are checked when this page opens. Email addresses are saved on the alert and are not sent anywhere yet.</p>
        <form className="alert-form" onSubmit={create}>
          <AirportField label="From" place={form.origin} onSelect={(origin) => setForm({ ...form, origin })} />
          <AirportField label="To" place={form.destination} onSelect={(destination) => setForm({ ...form, destination })} />
          <label className="field">
            <span>Departure</span>
            <input type="date" required value={form.departDate} onChange={(event) => setForm({ ...form, departDate: event.target.value })} />
          </label>
          <label className="field">
            <span>Return</span>
            <input type="date" value={form.returnDate} min={form.departDate} onChange={(event) => setForm({ ...form, returnDate: event.target.value })} />
          </label>
          <label className="field">
            <span>Target price</span>
            <input type="number" min="20" value={form.target} onChange={(event) => setForm({ ...form, target: event.target.value })} />
          </label>
          <label className="field">
            <span>Email</span>
            <input type="email" value={form.email} placeholder="Optional" onChange={(event) => setForm({ ...form, email: event.target.value })} />
          </label>
          <button className="primary" type="submit">Create alert</button>
        </form>
        {error && <p className="form-error">{error}</p>}
      </section>

      <section>
        {loading && <p className="muted">Checking prices…</p>}
        {!loading && alerts.length === 0 && (
          <p className="empty">No alerts yet. Search a route and choose Set alert, or create one here.</p>
        )}
        <div className="alert-list">
          {alerts.map((alert) => (
            <article key={alert.id} className={selected?.id === alert.id ? "alert-card on" : "alert-card"}>
              <button type="button" className="alert-main" onClick={() => setSelected(alert)}>
                <strong>{alert.origin.city} to {alert.destination.city}{alert.airline_name ? ` · ${alert.airline_name}` : ""}</strong>
                <span>
                  {formatLong(alert.depart_date)}
                  {alert.return_date ? ` – ${formatLong(alert.return_date)}` : " · One way"}
                </span>
                <span className={`pill ${alert.status}`}>{STATUS[alert.status]}</span>
              </button>
              <div className="alert-prices">
                <div>
                  <small>Current</small>
                  <strong>{alert.last_price ? money(alert.last_price) : "—"}</strong>
                </div>
                <div>
                  <small>Target</small>
                  <strong>{money(alert.target_price)}</strong>
                </div>
              </div>
              <div className="alert-actions">
                <button type="button" className="textish" onClick={() => onOpenRoute(alert)}>View flights</button>
                <button type="button" className="textish danger" onClick={() => remove(alert.id)}>Delete</button>
              </div>
            </article>
          ))}
        </div>
        {selected && (
          <section className="panel">
            <div className="panel-head">
              <h2>{selected.origin.city} to {selected.destination.city}</h2>
              <p>Target {money(selected.target_price)} per person. The green line is your target.</p>
            </div>
            <PriceChart history={outlook?.history} target={selected.target_price} />
          </section>
        )}
      </section>
    </div>
  );
}
