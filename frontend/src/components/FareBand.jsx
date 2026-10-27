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
      <p className="level">
        {band.confidence === "low" ? "Low confidence" : band.estimate === "model" ? "US DOT model" : "US DOT tickets"}
      </p>
      {band.available ? (
        <>
          <h2>
            {band.estimate === "model"
              ? <>Paid-fare model range for this route is {money(band.low)}–{money(band.high)}.</>
              : <>Real tickets for this route usually paid {money(band.low)}–{money(band.high)}.</>}
          </h2>
          <p className="fine">{band.note}</p>
        </>
      ) : (
        <p>{band.note}</p>
      )}
    </section>
  );
}
