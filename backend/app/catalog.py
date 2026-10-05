"""Airports, metro areas, and airlines used by the sample fare engine."""

# code, city, name, country, lat, lon, tz offset hours
_AIRPORT_ROWS = [
    ("JFK", "New York", "John F. Kennedy International", "United States", 40.6413, -73.7781, -5),
    ("EWR", "New York", "Newark Liberty International", "United States", 40.6895, -74.1745, -5),
    ("LGA", "New York", "LaGuardia", "United States", 40.7769, -73.8740, -5),
    ("LHR", "London", "Heathrow", "United Kingdom", 51.4700, -0.4543, 0),
    ("LGW", "London", "Gatwick", "United Kingdom", 51.1537, -0.1821, 0),
    ("CDG", "Paris", "Charles de Gaulle", "France", 49.0097, 2.5479, 1),
    ("ORY", "Paris", "Orly", "France", 48.7262, 2.3652, 1),
    ("HND", "Tokyo", "Haneda", "Japan", 35.5494, 139.7798, 9),
    ("NRT", "Tokyo", "Narita", "Japan", 35.7720, 140.3929, 9),
    ("ORD", "Chicago", "O'Hare International", "United States", 41.9742, -87.9073, -6),
    ("MDW", "Chicago", "Midway", "United States", 41.7868, -87.7522, -6),
    ("IAD", "Washington", "Dulles International", "United States", 38.9531, -77.4565, -5),
    ("DCA", "Washington", "Reagan National", "United States", 38.8512, -77.0402, -5),
    ("LAX", "Los Angeles", "Los Angeles International", "United States", 33.9416, -118.4085, -8),
    ("SFO", "San Francisco", "San Francisco International", "United States", 37.6213, -122.3790, -8),
    ("SEA", "Seattle", "Seattle-Tacoma International", "United States", 47.4502, -122.3088, -8),
    ("MIA", "Miami", "Miami International", "United States", 25.7959, -80.2870, -5),
    ("FLL", "Fort Lauderdale", "Fort Lauderdale-Hollywood", "United States", 26.0726, -80.1527, -5),
    ("ATL", "Atlanta", "Hartsfield-Jackson Atlanta", "United States", 33.6407, -84.4277, -5),
    ("DFW", "Dallas", "Dallas/Fort Worth International", "United States", 32.8998, -97.0403, -6),
    ("DEN", "Denver", "Denver International", "United States", 39.8561, -104.6737, -7),
    ("BOS", "Boston", "Logan International", "United States", 42.3656, -71.0096, -5),
    ("MCO", "Orlando", "Orlando International", "United States", 28.4312, -81.3081, -5),
    ("LAS", "Las Vegas", "Harry Reid International", "United States", 36.0840, -115.1537, -8),
    ("SAN", "San Diego", "San Diego International", "United States", 32.7338, -117.1933, -8),
    ("AUS", "Austin", "Austin-Bergstrom International", "United States", 30.1975, -97.6664, -6),
    ("BWI", "Baltimore", "Baltimore/Washington International", "United States", 39.1774, -76.6684, -5),
    ("BNA", "Nashville", "Nashville International", "United States", 36.1263, -86.6774, -6),
    ("PDX", "Portland", "Portland International", "United States", 45.5898, -122.5951, -8),
    ("CLT", "Charlotte", "Charlotte Douglas International", "United States", 35.2140, -80.9431, -5),
    ("PHX", "Phoenix", "Phoenix Sky Harbor", "United States", 33.4373, -112.0078, -7),
    ("PHL", "Philadelphia", "Philadelphia International", "United States", 39.8744, -75.2424, -5),
    ("IAH", "Houston", "George Bush Intercontinental", "United States", 29.9902, -95.3368, -6),
    ("MSP", "Minneapolis", "Minneapolis-Saint Paul", "United States", 44.8848, -93.2223, -6),
    ("DTW", "Detroit", "Detroit Metropolitan", "United States", 42.2162, -83.3554, -5),
    ("SLC", "Salt Lake City", "Salt Lake City International", "United States", 40.7899, -111.9791, -7),
    ("HNL", "Honolulu", "Daniel K. Inouye International", "United States", 21.3187, -157.9225, -10),
    ("CUN", "Cancun", "Cancun International", "Mexico", 21.0365, -86.8771, -5),
    ("MEX", "Mexico City", "Mexico City International", "Mexico", 19.4361, -99.0719, -6),
    ("YYZ", "Toronto", "Toronto Pearson International", "Canada", 43.6777, -79.6248, -5),
    ("YVR", "Vancouver", "Vancouver International", "Canada", 49.1947, -123.1792, -8),
    ("YUL", "Montreal", "Montreal-Trudeau International", "Canada", 45.4706, -73.7408, -5),
    ("FRA", "Frankfurt", "Frankfurt Airport", "Germany", 50.0379, 8.5622, 1),
    ("MUC", "Munich", "Munich Airport", "Germany", 48.3537, 11.7750, 1),
    ("AMS", "Amsterdam", "Schiphol", "Netherlands", 52.3105, 4.7683, 1),
    ("MAD", "Madrid", "Adolfo Suarez Madrid-Barajas", "Spain", 40.4983, -3.5676, 1),
    ("BCN", "Barcelona", "Barcelona-El Prat", "Spain", 41.2974, 2.0833, 1),
    ("DUB", "Dublin", "Dublin Airport", "Ireland", 53.4213, -6.2701, 0),
    ("FCO", "Rome", "Leonardo da Vinci Fiumicino", "Italy", 41.8003, 12.2389, 1),
    ("LIS", "Lisbon", "Humberto Delgado Airport", "Portugal", 38.7742, -9.1342, 0),
    ("IST", "Istanbul", "Istanbul Airport", "Turkey", 41.2753, 28.7519, 3),
    ("DXB", "Dubai", "Dubai International", "United Arab Emirates", 25.2532, 55.3657, 4),
    ("DOH", "Doha", "Hamad International", "Qatar", 25.2731, 51.6080, 3),
    ("SIN", "Singapore", "Changi", "Singapore", 1.3644, 103.9915, 8),
    ("HKG", "Hong Kong", "Hong Kong International", "Hong Kong", 22.3080, 113.9185, 8),
    ("ICN", "Seoul", "Incheon International", "South Korea", 37.4602, 126.4407, 9),
    ("DEL", "Delhi", "Indira Gandhi International", "India", 28.5562, 77.1000, 5.5),
    ("BOM", "Mumbai", "Chhatrapati Shivaji Maharaj", "India", 19.0896, 72.8656, 5.5),
    ("SYD", "Sydney", "Sydney Kingsford Smith", "Australia", -33.9399, 151.1753, 10),
    ("MEL", "Melbourne", "Melbourne Airport", "Australia", -37.6690, 144.8410, 10),
    ("AKL", "Auckland", "Auckland Airport", "New Zealand", -37.0082, 174.7850, 12),
    ("GRU", "Sao Paulo", "Guarulhos International", "Brazil", -23.4356, -46.4731, -3),
    ("EZE", "Buenos Aires", "Ezeiza International", "Argentina", -34.8222, -58.5358, -3),
    ("JNB", "Johannesburg", "O. R. Tambo International", "South Africa", -26.1392, 28.2460, 2),
    ("CAI", "Cairo", "Cairo International", "Egypt", 30.1129, 31.4000, 2),
]

AIRPORTS = {
    code: {
        "code": code,
        "city": city,
        "name": name,
        "country": country,
        "lat": lat,
        "lon": lon,
        "tz": tz,
    }
    for code, city, name, country, lat, lon, tz in _AIRPORT_ROWS
}

CITIES = {
    "NYC": {"city": "New York", "country": "United States", "airports": ["JFK", "EWR", "LGA"]},
    "LON": {"city": "London", "country": "United Kingdom", "airports": ["LHR", "LGW"]},
    "PAR": {"city": "Paris", "country": "France", "airports": ["CDG", "ORY"]},
    "TYO": {"city": "Tokyo", "country": "Japan", "airports": ["HND", "NRT"]},
    "CHI": {"city": "Chicago", "country": "United States", "airports": ["ORD", "MDW"]},
    "WAS": {"city": "Washington", "country": "United States", "airports": ["IAD", "DCA"]},
}

_METRO_CITY_NAMES = {city["city"].lower() for city in CITIES.values()}

AIRLINES = {
    "DL": {"code": "DL", "name": "Delta Air Lines", "color": "#C8102E", "hubs": ["ATL", "DTW", "MSP", "SLC", "SEA", "JFK", "LAX"], "factor": 1.0},
    "UA": {"code": "UA", "name": "United Airlines", "color": "#002244", "hubs": ["EWR", "ORD", "DEN", "IAH", "SFO", "IAD"], "factor": 1.0},
    "AA": {"code": "AA", "name": "American Airlines", "color": "#0078D2", "hubs": ["DFW", "CLT", "MIA", "ORD", "PHX", "PHL", "JFK"], "factor": 1.0},
    "WN": {"code": "WN", "name": "Southwest Airlines", "color": "#304CB2", "hubs": ["DEN", "MDW", "BWI", "LAS", "PHX", "BNA", "MCO"], "factor": 0.88},
    "B6": {"code": "B6", "name": "JetBlue", "color": "#003876", "hubs": ["JFK", "BOS", "FLL", "MCO", "LAX"], "factor": 0.96},
    "AS": {"code": "AS", "name": "Alaska Airlines", "color": "#01426A", "hubs": ["SEA", "PDX", "SFO", "LAX"], "factor": 0.97},
    "NK": {"code": "NK", "name": "Spirit Airlines", "color": "#111111", "hubs": ["FLL", "MCO", "LAS", "DFW", "ATL", "ORD"], "factor": 0.72},
    "F9": {"code": "F9", "name": "Frontier Airlines", "color": "#248837", "hubs": ["DEN", "MCO", "LAS", "PHL", "ATL"], "factor": 0.74},
    "AC": {"code": "AC", "name": "Air Canada", "color": "#F01428", "hubs": ["YYZ", "YVR", "YUL"], "factor": 1.02},
    "BA": {"code": "BA", "name": "British Airways", "color": "#075AAA", "hubs": ["LHR"], "factor": 1.08},
    "LH": {"code": "LH", "name": "Lufthansa", "color": "#05164D", "hubs": ["FRA", "MUC"], "factor": 1.08},
    "AF": {"code": "AF", "name": "Air France", "color": "#002157", "hubs": ["CDG"], "factor": 1.07},
    "KL": {"code": "KL", "name": "KLM", "color": "#00A1DE", "hubs": ["AMS"], "factor": 1.05},
    "IB": {"code": "IB", "name": "Iberia", "color": "#DA291C", "hubs": ["MAD"], "factor": 1.04},
    "EK": {"code": "EK", "name": "Emirates", "color": "#D71921", "hubs": ["DXB"], "factor": 1.14},
    "QR": {"code": "QR", "name": "Qatar Airways", "color": "#5C0632", "hubs": ["DOH"], "factor": 1.12},
    "TK": {"code": "TK", "name": "Turkish Airlines", "color": "#C70A0C", "hubs": ["IST"], "factor": 1.05},
    "SQ": {"code": "SQ", "name": "Singapore Airlines", "color": "#1B3A6B", "hubs": ["SIN"], "factor": 1.16},
    "JL": {"code": "JL", "name": "Japan Airlines", "color": "#E10600", "hubs": ["HND", "NRT"], "factor": 1.1},
    "NH": {"code": "NH", "name": "ANA", "color": "#1D2088", "hubs": ["HND", "NRT"], "factor": 1.1},
    "QF": {"code": "QF", "name": "Qantas", "color": "#E0001B", "hubs": ["SYD", "MEL"], "factor": 1.1},
    "KE": {"code": "KE", "name": "Korean Air", "color": "#004B87", "hubs": ["ICN"], "factor": 1.08},
    "CX": {"code": "CX", "name": "Cathay Pacific", "color": "#006564", "hubs": ["HKG"], "factor": 1.1},
    "LA": {"code": "LA", "name": "LATAM", "color": "#1B0088", "hubs": ["GRU", "MIA"], "factor": 1.02},
}

COUNTRY_REGION = {
    "United States": "na",
    "Canada": "na",
    "Mexico": "na",
    "United Kingdom": "eu",
    "France": "eu",
    "Germany": "eu",
    "Netherlands": "eu",
    "Spain": "eu",
    "Ireland": "eu",
    "Italy": "eu",
    "Portugal": "eu",
    "Turkey": "eu",
    "United Arab Emirates": "me",
    "Qatar": "me",
    "Japan": "asia",
    "Singapore": "asia",
    "South Korea": "asia",
    "Hong Kong": "asia",
    "India": "asia",
    "Australia": "oc",
    "New Zealand": "oc",
    "Brazil": "latam",
    "Argentina": "latam",
    "South Africa": "af",
    "Egypt": "af",
}

POPULAR_CODES = ["NYC", "LON", "PAR", "TYO", "LAX", "SFO", "MIA", "CHI", "DXB", "HNL", "DUB", "SYD"]


def region_of(airport: dict) -> str:
    return COUNTRY_REGION.get(airport["country"], "other")


def get_place(code: str) -> dict:
    key = (code or "").strip().upper()
    if key in CITIES:
        city = CITIES[key]
        return {
            "code": key,
            "type": "city",
            "city": city["city"],
            "name": "All airports",
            "country": city["country"],
            "airports": list(city["airports"]),
        }
    airport = AIRPORTS.get(key)
    if airport is None:
        raise ValueError(f"No airport or city matches {code}.")
    return {
        "code": key,
        "type": "airport",
        "city": airport["city"],
        "name": airport["name"],
        "country": airport["country"],
        "airports": [key],
    }


def all_places() -> list[dict]:
    places = [get_place(code) for code in CITIES]
    places.extend(get_place(code) for code in AIRPORTS)
    return places


def search_places(query: str, limit: int = 8) -> list[dict]:
    needle = (query or "").strip().lower()
    if not needle:
        return [get_place(code) for code in POPULAR_CODES[:limit]]

    scored = []
    for place in all_places():
        code = place["code"].lower()
        city = place["city"].lower()
        name = place["name"].lower()
        country = place["country"].lower()
        if needle == code:
            score = 0
        elif city.startswith(needle) or code.startswith(needle):
            score = 1
        elif needle in city or needle in code or needle in name or needle in country:
            score = 2
        else:
            continue
        if place["type"] == "airport":
            score += 0.15
        scored.append((score, place["city"], place["code"], place))
    scored.sort(key=lambda item: (item[0], item[1], item[2]))
    return [item[3] for item in scored[:limit]]


def aliases() -> list[tuple[str, str]]:
    phrases: list[tuple[str, str]] = []
    for code, city in CITIES.items():
        phrases.append((city["city"].lower(), code))
        phrases.append((code.lower(), code))
    for airport in AIRPORTS.values():
        if airport["city"].lower() not in _METRO_CITY_NAMES:
            phrases.append((airport["city"].lower(), airport["code"]))
        phrases.append((airport["name"].lower(), airport["code"]))
        phrases.append((airport["code"].lower(), airport["code"]))
    phrases.sort(key=lambda item: len(item[0]), reverse=True)
    return phrases


PLACE_ALIASES = aliases()
