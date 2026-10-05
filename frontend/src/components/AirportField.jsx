import { useEffect, useRef, useState } from "react";
import { api } from "../api";

function labelFor(place) {
  if (!place) return "";
  return `${place.city} (${place.code})`;
}

export default function AirportField({ label, place, onSelect }) {
  const [query, setQuery] = useState(labelFor(place));
  const [open, setOpen] = useState(false);
  const [options, setOptions] = useState([]);
  const [active, setActive] = useState(0);
  const box = useRef(null);

  useEffect(() => {
    setQuery(labelFor(place));
  }, [place]);

  useEffect(() => {
    if (!open) return undefined;
    let ignore = false;
    api.airports(query === labelFor(place) ? "" : query)
      .then((data) => {
        if (!ignore) {
          setOptions(data.places);
          setActive(0);
        }
      })
      .catch(() => {
        if (!ignore) setOptions([]);
      });
    return () => {
      ignore = true;
    };
  }, [open, query, place]);

  useEffect(() => {
    function onDoc(event) {
      if (box.current && !box.current.contains(event.target)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  function choose(next) {
    onSelect(next);
    setQuery(labelFor(next));
    setOpen(false);
  }

  function onKeyDown(event) {
    if (!open && (event.key === "ArrowDown" || event.key === "Enter")) {
      setOpen(true);
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((index) => Math.min(options.length - 1, index + 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((index) => Math.max(0, index - 1));
    } else if (event.key === "Enter" && open && options[active]) {
      event.preventDefault();
      choose(options[active]);
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <label className="field" ref={box}>
      <span>{label}</span>
      <input
        value={query}
        autoComplete="off"
        aria-label={label}
        onFocus={(event) => {
          setOpen(true);
          event.target.select();
        }}
        onChange={(event) => {
          setQuery(event.target.value);
          setOpen(true);
        }}
        onKeyDown={onKeyDown}
      />
      {open && (
        <ul className="menu" role="listbox">
          {options.length === 0 && <li className="menu-empty">No matches</li>}
          {options.map((option, index) => (
            <li key={`${option.type}-${option.code}`}>
              <button
                type="button"
                className={index === active ? "active" : ""}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => choose(option)}
              >
                <strong>{option.city}</strong>
                <em>{option.code}</em>
                <small>{option.type === "city" ? "All airports" : option.name} · {option.country}</small>
              </button>
            </li>
          ))}
        </ul>
      )}
    </label>
  );
}
