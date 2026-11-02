import { useEffect, useState } from "react";
import { api } from "../api";

function percent(value) {
  if (value == null) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

function dollars(value) {
  if (value == null) return "—";
  return `$${Number(value).toFixed(2)}`;
}

export default function About() {
  const [metrics, setMetrics] = useState(undefined);
  const [error, setError] = useState("");

  useEffect(() => {
    api.modelMetrics()
      .then(setMetrics)
      .catch((err) => setError(err.message));
  }, []);

  if (error) return <p className="form-error">{error}</p>;
  if (!metrics) return <p className="muted">Loading model details…</p>;
  const comparison = metrics.comparison || {};

  return (
    <section className="panel about-model">
      <h2>About the model</h2>
      <p>
        Paid-fare ranges come from US DOT DB1B Market tickets, version {metrics.model_version}.
        The holdout quarter is {metrics.holdout || "not scored yet"}. Training quarters are {(metrics.train_periods || []).join(", ") || "—"}.
        {metrics.calibration_period ? ` ${metrics.calibration_period} is used only to calibrate the band.` : ""}
      </p>
      {metrics.available && (
        <table>
          <thead>
            <tr><th>Estimate</th><th>Median error</th><th>10–90 coverage</th></tr>
          </thead>
          <tbody>
            <tr><td>Phase 2 median</td><td>{dollars(comparison.model_mae)}</td><td>{percent(comparison.conformal_10_90_coverage)}</td></tr>
            <tr><td>Empirical median</td><td>{dollars(comparison.empirical_mae)}</td><td>{percent(comparison.empirical_coverage)}</td></tr>
            <tr><td>Route average</td><td>{dollars(comparison.route_average_mae)}</td><td></td></tr>
            <tr><td>Linear model</td><td>{dollars(comparison.linear_mae)}</td><td></td></tr>
          </tbody>
        </table>
      )}
      {!metrics.available && <p>{metrics.note}</p>}
      <h3>Limitations</h3>
      <ul>
        {(metrics.limitations || []).map((item) => <li key={item}>{item}</li>)}
      </ul>
      <p className="fine">
        A learned book-or-wait model would need a dataset with a booking date, or days until departure, on each ticket.
        DB1B only records the quarter of travel and the fare paid, so that model is not trained here.
      </p>
    </section>
  );
}
