import { useEffect, useState } from "react";
import { api } from "../api";
import { money } from "../format";

export function useFareBand(origin, destination) {
  const [band, setBand] = useState(undefined);

  useEffect(() => {
    if (!origin || !destination || origin === destination) {
      setBand(null);
      return undefined;
    }
    let ignore = false;
    setBand(undefined);
    api.fareBand(origin, destination)
      .then((data) => {
        if (!ignore) setBand(data);
      })
      .catch(() => {
        if (!ignore) setBand(null);
      });
    return () => {
      ignore = true;
    };
  }, [origin, destination]);

  return band;
}

export default function FareBand({ origin, destination, band }) {
  const managed = band === undefined;
  const loaded = useFareBand(managed ? origin : "", managed ? destination : "");
  const shown = managed ? loaded : band;

  if (shown === undefined || shown === null) return null;

  return (
    <section className="fare-band">
      <p className="level">
        {shown.confidence === "low" ? "Low confidence" : shown.estimate === "model" ? "US DOT model" : "US DOT tickets"}
      </p>
      {shown.available ? (
        <>
          <h2>
            {shown.estimate === "model"
              ? <>Paid-fare model range for this route is {money(shown.low)}–{money(shown.high)}.</>
              : <>Real tickets for this route usually paid {money(shown.low)}–{money(shown.high)}.</>}
          </h2>
          <p className="fine">{shown.note}</p>
        </>
      ) : (
        <p>{shown.note}</p>
      )}
    </section>
  );
}
