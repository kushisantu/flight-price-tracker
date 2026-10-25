import { useEffect, useState } from "react";
import { api } from "../api";
import { money } from "../format";

export default function FareBand({ origin, destination }) {
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

  if (band === undefined || band === null) return null;

  return (
    <section className="fare-band">
      <p className="level">US DOT tickets</p>
      {band.available ? (
        <>
          <h2>Real US tickets for this route usually paid {money(band.low)}–{money(band.high)}.</h2>
          <p>
            Median estimate {money(band.mid)} per person in {band.year} Q{band.quarter}, from{" "}
            {band.passengers.toLocaleString("en-US")} passengers in the 10% sample.
          </p>
          <p className="fine">
            {band.source}, model {band.model_version}. Passenger-weighted 10th to 90th percentile across airlines.
            This is not a forecast, and it is separate from the sample fare chart.
          </p>
        </>
      ) : (
        <p>{band.note}</p>
      )}
    </section>
  );
}
