import { useEffect, useState } from "react";
import { api } from "../api";

function quarterOf(date) {
  const month = Number(String(date).slice(5, 7));
  if (!month) return null;
  return Math.floor((month - 1) / 3) + 1;
}

export default function DealLabel({ origin, destination, airline, departDate, fare }) {
  const [score, setScore] = useState(undefined);
  const quarter = quarterOf(departDate);

  useEffect(() => {
    if (!origin || !destination || !airline || !quarter || !fare) {
      setScore(null);
      return undefined;
    }
    let ignore = false;
    setScore(undefined);
    api.dealScore({ origin, destination, airline, quarter, fare, fareKind: "sample" })
      .then((data) => {
        if (!ignore) setScore(data);
      })
      .catch(() => {
        if (!ignore) setScore(null);
      });
    return () => {
      ignore = true;
    };
  }, [origin, destination, airline, quarter, fare]);

  if (!score?.available) return null;
  const tone = score.label === "High" ? "high" : score.label === "Typical" ? "typical" : "low";

  return (
    <p className="deal-score">
      <em className={`pill ${tone}`}>{score.label}</em>
      <span className="fine">{score.note}</span>
    </p>
  );
}
