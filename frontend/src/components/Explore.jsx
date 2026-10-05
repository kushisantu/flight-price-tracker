import { useEffect, useState } from "react";
import { api } from "../api";
import { formatLong, money } from "../format";
import PriceChart from "./PriceChart";
import SearchForm from "./SearchForm";

const EXAMPLES = [
  "New York to London in December under $700",
  "One way San Francisco to Tokyo next Friday",
  "Miami to Chicago this weekend",
  "Flights to Paris for 5 nights",
];

function Sparkline({ points }) {
  if (!points?.length) return null;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const width = 140;
  const height = 36;
  const path = points.map((price, index) => {
    const x = (index / (points.length - 1 || 1)) * width;
    const y = height - 4 - ((price - min) / (max - min || 1)) * (height - 8);
    return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return (
    <svg className="spark" viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
      <path d={path} />
    </svg>
  );
}

export default function Explore({ criteria, onChange, onSearch, busy, onSmart }) {
  const [deals, setDeals] = useState([]);
  const [outlook, setOutlook] = useState(null);
  const [smartText, setSmartText] = useState("");
  const [smartError, setSmartError] = useState("");

  useEffect(() => {
    let ignore = false;
    api.deals(criteria.origin.code)
      .then((data) => {
        if (!ignore) setDeals(data.deals);
      })
      .catch(() => {
        if (!ignore) setDeals([]);
      });
    return () => {
      ignore = true;
    };
  }, [criteria.origin.code]);

  useEffect(() => {
    if (!criteria.origin || !criteria.destination || criteria.origin.code === criteria.destination.code) return undefined;
    let ignore = false;
    const handle = setTimeout(() => {
      api.outlook(criteria)
        .then((data) => {
          if (!ignore) setOutlook(data);
        })
        .catch(() => {
          if (!ignore) setOutlook(null);
        });
    }, 350);
    return () => {
      ignore = true;
      clearTimeout(handle);
    };
  }, [criteria]);

  async function submitSmart(event) {
    event.preventDefault();
    setSmartError("");
    try {
      await onSmart(smartText);
    } catch (error) {
      setSmartError(error.message);
    }
  }

  const insight = outlook?.insight;

  return (
    <div className="explore">
      <section className="hero">
        <p className="eyebrow">Compare fares across airlines and dates</p>
        <h1>Find the fare worth booking.</h1>
        <p className="lede">
          Search like a flight board, then watch the price. Charts show how the cheapest fare has moved, and alerts fire when it drops to your number.
        </p>
        <SearchForm value={criteria} onChange={onChange} onSubmit={onSearch} busy={busy} />
        <form className="smart" onSubmit={submitSmart}>
          <label>
            <span>Or describe the trip</span>
            <input
              value={smartText}
              placeholder='Try "Chicago to Miami this weekend"'
              onChange={(event) => setSmartText(event.target.value)}
            />
          </label>
          <button className="secondary" type="submit">Find dates</button>
        </form>
        {smartError && <p className="form-error">{smartError}</p>}
        <div className="examples">
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              className="example"
              onClick={() => onSmart(example).catch((error) => setSmartError(error.message))}
            >
              {example}
            </button>
          ))}
        </div>
      </section>

      <section className="outlook">
        <div className="panel">
          <div className="panel-head">
            <h2>Price history</h2>
            <p>{criteria.origin.city} to {criteria.destination.city}</p>
          </div>
          <PriceChart history={outlook?.history} />
          <p className="fine">Cheapest modeled fare for these dates over the last 90 days. The dashed line is the average.</p>
        </div>
        <aside className={`insight ${insight?.level || ""}`}>
          {insight ? (
            <>
              <p className="level">{insight.level === "low" ? "Lower than usual" : insight.level === "high" ? "Higher than usual" : "Typical"}</p>
              <h2>{insight.title}</h2>
              <p>{insight.summary}</p>
              <p>{insight.advice}</p>
              {insight.alternative && (
                <button
                  type="button"
                  className="secondary"
                  onClick={() => onSearch({
                    ...criteria,
                    departDate: insight.alternative.depart_date,
                    returnDate: insight.alternative.return_date || criteria.returnDate,
                  })}
                >
                  Save {money(insight.alternative.savings)} on {formatLong(insight.alternative.depart_date)}
                </button>
              )}
            </>
          ) : (
            <p className="muted">Pick two cities to see whether this is a good time to book.</p>
          )}
        </aside>
      </section>

      <section>
        <div className="panel-head">
          <h2>Popular from {criteria.origin.city}</h2>
          <p>Round trips about five weeks out. Green means the fare is under its recent average.</p>
        </div>
        <div className="deals">
          {deals.map((deal) => (
            <button
              key={deal.destination.code}
              type="button"
              className="deal"
              onClick={() => onSearch({
                ...criteria,
                destination: deal.destination,
                departDate: deal.depart_date,
                returnDate: deal.return_date,
                tripType: "round",
              })}
            >
              <div className="deal-top">
                <strong>{deal.destination.city}</strong>
                <span>{money(deal.price)}</span>
              </div>
              <small>{formatLong(deal.depart_date)} – {formatLong(deal.return_date)}</small>
              <Sparkline points={deal.history} />
              <em className={`pill ${deal.level}`}>{deal.level === "low" ? "Low" : deal.level === "high" ? "High" : "Typical"}</em>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
