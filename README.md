# Flight Price Tracker

A flight search board in the style of Google Flights. Compare fares across airlines and dates, read a price history chart, and set an alert when the fare hits your number.

The React app talks to a FastAPI service. Prices come from a fare model (distance, season, weekday, cabin, and how far out you book) so the same search always returns the same number. Those prices are saved in PostgreSQL, which is what the charts and alerts read back. Docker and AWS are not part of this local setup.

Fares are sample data for planning. They are not live airline inventory.

## What you can do

- Search round trip or one way by city or airport, dates, passengers, and cabin
- Sort by best, cheapest, fastest, or departure, and filter stops, airlines, time of day, and price
- Scan a date strip and a month calendar colored from cheaper to pricier
- Read a Chart.js history of the cheapest fare, plus a short “book or wait” note
- Type a trip in plain language, such as `New York to London in December under $700`
- Save a price alert and see whether the current fare is under your target

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
backend/app/catalog.py          airports, cities, airlines
backend/app/services/flights.py fare model, search, charts, deals
backend/app/services/smart.py   plain-language search
backend/app/routers/api.py      HTTP API
frontend/src                    React UI and Chart.js
```

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Database in use, quote count, alert count |
| GET | `/api/airports?q=` | City and airport search |
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
