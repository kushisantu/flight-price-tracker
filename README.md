# Flight Price Tracker

A flight search board in the style of Google Flights. Compare fares across airlines and dates, read a price history chart, and set an alert when the fare hits your number.

The React app talks to a FastAPI service. The flight board uses a sample fare model (distance, season, weekday, cabin, and how far out you book) so the same search always returns the same number. Those sample prices are saved in PostgreSQL, which is what the charts and alerts read back. Docker and AWS are not part of this local setup.

Next to that, US DOT DB1B tickets supply a paid-fare range from a LightGBM quantile model. The model is trained on earlier quarters and conformal-adjusted on a later quarter. It is not a booking-date forecast. The sample board stays labeled as a sample. If a route has no training tickets, the API and the page say the DOT sample does not cover it.

Fares on the flight board are sample data for planning. They are not live airline inventory.

## What you can do

- Search round trip or one way by city or airport, dates, passengers, and cabin
- Sort by best, cheapest, fastest, or departure, and filter stops, airlines, time of day, and price
- Scan a date strip and a month calendar colored from cheaper to pricier
- Read a Chart.js history of the cheapest fare, plus a short “book or wait” note
- Type a trip in plain language, such as `New York to London in December under $700`
- Save a price alert and see whether the current fare is under your target
- Read a DOT paid-fare range for routes in the ticket sample, including a low-confidence flag when the route is thin

## Paid fares from DOT

`make load` reads four DB1B Market quarters (2024 Q3 through 2025 Q2) and keeps every airport in those files. OpenFlights supplies names and coordinates. Airports missing from OpenFlights show the code only.

`make train` fits seven LightGBM quantiles (5, 10, 25, 50, 75, 90, 95) on 2024 Q3 and 2024 Q4. Features are origin, destination, airline, distance, quarter, coupons, stops, nonstop, and the airline’s share of that route in the training quarters. Predictions are sorted so the quantiles cannot cross. 2025 Q1 is the conformal calibration quarter. 2025 Q2 is the holdout and is not used for training, tuning, or calibration. Rolling-origin tuning scores 2024 Q4 from a 2024 Q3 fit, then scores 2025 Q1 from a 2024 Q3–Q4 fit. The seed is 1. MLflow records the runs in the local folder `backend/mlruns`.

A route with training tickets is served from that model. Fewer than 50 training passengers is labeled low confidence. A route with none stays uncovered. The sample flight board still only builds itineraries for its original airport list.

`make eval` scores 2025 Q2. On this machine, without GNU make:

```powershell
cd backend
.\.venv\Scripts\python.exe -m scripts.load_db1b
.\.venv\Scripts\python.exe -m scripts.train_phase2
.\.venv\Scripts\python.exe -m scripts.eval_phase2
```

The earlier empirical table is still reproducible with `python -m scripts.train` and `python -m scripts.eval`. Dependency versions are pinned in `backend/requirements.txt`. Details and the SHAP summary are in `MODEL_CARD.md`.

Holdout results for `lgbm-2024q3-2024q4` on 7,884,075 tickets that both the model and the empirical table can score:

| Estimate | MAE | 10–90 coverage |
| --- | ---: | ---: |
| Phase 2 median | $89.93 | 81.9% |
| Empirical median | $97.42 | 81.1% |
| Route average | $102.13 |  |
| Linear model | $118.76 |  |

The model’s 10–90 band covered 78.7% of those tickets before the conformal shift and 81.9% after it. On the 2,101,471 tickets the sample formula can price, the median errors are model $97.04, empirical $106.12, route average $112.15, linear $126.89, and sample formula $109.49.

Coverage stays near 80% on thick and thin routes. The median error is higher below 50 training passengers ($125.38), which is why those routes are labeled low confidence.

Limitations: DB1B has no booking date, so this is not a forecast of a purchase. Each row is a directional market, and the file has no round-trip flag. The quarterly file is a 10% sample. The sample flight board does not invent itineraries for airports outside its original list.

## Run it

You need Node.js 18 or newer and Python 3.12. PostgreSQL is optional for the first run. If it is not running, the API stores data in `backend/flight_tracker.db` instead.

Open two terminals from the project folder.

**API**

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

If `python` is not recognized, close the terminal and open it again so the new Python install is on your PATH. You can also call the installer path directly:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m venv .venv
```

The API docs are at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

**Website**

```powershell
cd frontend
npm install
npm run dev
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173).

## Use PostgreSQL

1. Install PostgreSQL and start it on port 5432.
2. The default login the app expects is user `postgres`, password `postgres`.
3. Copy `backend/.env.example` to `backend/.env` if you need a different password or host.
4. Restart the API. It creates a database named `flight_tracker` if that server is reachable.

```text
DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/flight_tracker
```

To require PostgreSQL and refuse the SQLite fallback, set `ALLOW_SQLITE_FALLBACK=false`.

Check which database is live at [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health). The page footer shows the same thing.

## Project layout

```text
backend/app/catalog.py          sample-board airports, cities, airlines
backend/app/services/flights.py sample fare model, search, charts, deals
backend/app/services/empirical.py earlier DOT percentile table
backend/app/services/phase2.py LightGBM quantiles and conformal band
backend/app/fare_model/phase2 saved boosters and MODEL_CARD.md
backend/app/services/smart.py   plain-language search
backend/app/routers/api.py      HTTP API
frontend/src                    React UI and Chart.js
```

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Database in use, quote count, alert count |
| GET | `/api/airports?q=` | Airports from the DOT extract, plus sample-board cities |
| GET | `/api/fare-band?origin=&destination=` | Paid-fare range, or a not-covered response |
| POST | `/api/search` | Flights, date strip, history, booking note |
| GET | `/api/outlook` | History and booking note for a route |
| GET | `/api/calendar` | Cheapest fare for each day in a month |
| GET | `/api/deals?origin=` | Sample trips from a city |
| POST | `/api/smart-search` | Turn a sentence into a search |
| GET, POST | `/api/alerts` | List or create alerts |
| DELETE | `/api/alerts/{id}` | Remove an alert |

## Ideas worth adding next

These are the upgrades that would make the product more useful. None of them are required to run what is here.

1. **Live fares.** Create a free Amadeus test account and replace the sample fare model with their flight-offers search. The UI can stay as it is.
2. **A real trip assistant.** The sentence search only understands a fixed set of phrases. A model API could handle “somewhere warm next month under $400” and explain the tradeoff.
3. **Email or text alerts.** Alerts are checked when you open the Alerts page or search that route. A scheduler plus Resend, SendGrid, or Twilio would message you when the fare actually drops.
4. **Accounts.** Alerts are shared in one local database. Sign-in would keep each person’s watches separate.
5. **A price forecast.** The chart already has 90 days of history. A small model could add “likely to rise this week” on top of the current book-or-wait note.
6. **Multi-city trips and a map.** Useful once live fares exist, so the extra clicks return real itineraries.
