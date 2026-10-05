import { useEffect, useState } from "react";
import { api } from "./api";
import Alerts from "./components/Alerts";
import Explore from "./components/Explore";
import Results from "./components/Results";
import { defaultCriteria, fromApiCriteria, money } from "./format";

function Plane() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path fill="currentColor" d="M21 16v-2l-8-5V3.5a1.5 1.5 0 0 0-3 0V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" />
    </svg>
  );
}

export default function App() {
  const [view, setView] = useState("explore");
  const [criteria, setCriteria] = useState(defaultCriteria);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [priceCap, setPriceCap] = useState(null);
  const [notice, setNotice] = useState("");
  const [toast, setToast] = useState("");
  const [alertCount, setAlertCount] = useState(0);
  const [health, setHealth] = useState(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth({ status: "down" }));
    api.alerts().then((data) => setAlertCount(data.alerts.length)).catch(() => {});
  }, []);

  useEffect(() => {
    if (!toast) return undefined;
    const handle = setTimeout(() => setToast(""), 3600);
    return () => clearTimeout(handle);
  }, [toast]);

  async function runSearch(next, cap = null) {
    setCriteria(next);
    setPriceCap(cap);
    setView("results");
    setLoading(true);
    setError("");
    try {
      const data = await api.search(next);
      setResult(data);
      if (cap && data.flights.every((flight) => flight.price > cap)) {
        setNotice(`Nothing is at or below ${money(cap)} right now. Showing fares from ${money(Math.min(...data.flights.map((flight) => flight.price)))}.`);
        setPriceCap(null);
      }
    } catch (err) {
      setResult(null);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function runSmart(query) {
    const parsed = await api.smart(query, criteria.origin?.code);
    setNotice(parsed.interpretation);
    await runSearch(fromApiCriteria(parsed.criteria), parsed.max_price);
    setToast(parsed.interpretation);
  }

  async function createAlert(body) {
    await api.createAlert(body);
    const data = await api.alerts();
    setAlertCount(data.alerts.length);
    setToast(`Alert set for ${money(body.target_price)} per person`);
  }

  const offline = health?.status === "down";

  return (
    <div className="page">
      <header className="topbar">
        <button type="button" className="brand" onClick={() => setView("explore")}>
          <span className="brand-mark"><Plane /></span>
          Flight Price Tracker
        </button>
        <nav>
          <button type="button" className={view !== "alerts" ? "nav on" : "nav"} onClick={() => setView(view === "results" ? "results" : "explore")}>
            Flights
          </button>
          <button type="button" className={view === "alerts" ? "nav on" : "nav"} onClick={() => setView("alerts")}>
            Alerts {alertCount > 0 && <span className="count">{alertCount}</span>}
          </button>
        </nav>
      </header>

      <main>
        {offline && (
          <p className="form-error banner-error">The API is not running. Start the FastAPI server on port 8000, then refresh.</p>
        )}
        {view === "explore" && (
          <Explore criteria={criteria} onChange={setCriteria} onSearch={(next) => runSearch(next, null)} busy={loading} onSmart={runSmart} />
        )}
        {view === "results" && (
          <Results
            criteria={criteria}
            result={result}
            loading={loading}
            error={error}
            priceCap={priceCap}
            notice={notice}
            onChange={setCriteria}
            onSearch={(next) => runSearch(next, priceCap)}
            onCreateAlert={createAlert}
          />
        )}
        {view === "alerts" && (
          <Alerts
            onCount={setAlertCount}
            onOpenRoute={(alert) => runSearch({
              origin: alert.origin,
              destination: alert.destination,
              departDate: alert.depart_date,
              returnDate: alert.return_date,
              tripType: alert.return_date ? "round" : "oneway",
              passengers: alert.passengers,
              cabin: alert.cabin,
            }, null)}
          />
        )}
      </main>

      <footer>
        <p>
          Sample fares for planning, stored in {health?.database === "postgresql" ? "PostgreSQL" : health?.database === "sqlite" ? "a local SQLite file until PostgreSQL is running" : "the database"}.
          {health?.quotes != null ? ` ${health.quotes.toLocaleString()} tracked quotes.` : ""} Connect a live fare API when you want real inventory.
        </p>
      </footer>
      {toast && <div className="toast" role="status">{toast}</div>}
    </div>
  );
}
