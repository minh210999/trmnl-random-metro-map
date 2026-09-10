import math
import os
import random
import time
import requests

TRMNL_WEBHOOK_URL = os.environ.get("TRMNL_WEBHOOK_URL")

DEFAULT_ROUTE_TAGS = ["subway", "light_rail", "tram"]

OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

CONTACT_URL = os.environ.get("OVERPASS_CONTACT_URL", "https://github.com/your-org/trmnl-random-metro-map")
REQUEST_HEADERS = {
    "User-Agent": f"trmnl-random-metro-map/1.0 ({CONTACT_URL})",
    "Referer": CONTACT_URL,
    "Content-Type": "text/plain",
}

# Raw city registry: "City Name": (longitude, latitude, radius_km, [optional_custom_tags])
CITY_TARGETS = {
    # --- East Asia ---
    "Tokyo, Japan": (139.6917, 35.6895, 35),
    "Osaka, Japan": (135.5023, 34.6937, 25),
    "Hong Kong": (114.1694, 22.3193, 22),
    "Seoul, South Korea": (126.9780, 37.5665, 35),
    "Singapore": (103.8198, 1.3521, 20),
    "Shanghai, China": (121.4737, 31.2304, 35),
    "Beijing, China": (116.4074, 39.9042, 35),
    "Shenzhen, China": (114.0579, 22.5431, 30),
    "Guangzhou, China": (113.2644, 23.1291, 30),
    "Taipei, Taiwan": (121.5654, 25.0330, 20),
    "Nagoya, Japan": (136.9066, 35.1815, 22),
    "Kyoto, Japan": (135.7681, 35.0116, 16),
    "Busan, South Korea": (129.0756, 35.1796, 25),
    "Chengdu, China": (104.0665, 30.5728, 30),
    "Wuhan, China": (114.3054, 30.5928, 30),

    # --- Southeast & South Asia ---
    "Kuala Lumpur, Malaysia": (101.6869, 3.1390, 25),
    "Bangkok, Thailand": (100.5018, 13.7563, 25),
    "Jakarta, Indonesia": (106.8456, -6.2088, 25),
    "Delhi, India": (77.2090, 28.6139, 35),
    "Mumbai, India": (72.8777, 19.0760, 30),
    "Ho Chi Minh City, Vietnam": (106.6297, 10.8231, 20),

    # --- Europe ---
    "Zurich, Switzerland": (8.5417, 47.3769, 15, ["subway", "light_rail", "tram"]),
    "Vienna, Austria": (16.3738, 48.2082, 20),
    "Munich, Germany": (11.5820, 48.1351, 22),
    "Berlin, Germany": (13.4050, 52.5200, 25),
    "Paris, France": (2.3522, 48.8566, 25),
    "London, UK": (-0.1276, 51.5072, 35),
    "Madrid, Spain": (-3.7038, 40.4168, 25),
    "Barcelona, Spain": (2.1734, 41.3851, 20),
    "Amsterdam, Netherlands": (4.9041, 52.3676, 18),
    "Copenhagen, Denmark": (12.5683, 55.6761, 18),
    "Stockholm, Sweden": (18.0686, 59.3293, 22),
    "Helsinki, Finland": (24.9384, 60.1699, 18),
    "Oslo, Norway": (10.7522, 59.9139, 18),
    "Prague, Czech Republic": (14.4378, 50.0755, 20),
    "Budapest, Hungary": (19.0402, 47.4979, 20),
    "Warsaw, Poland": (21.0122, 52.2297, 20),
    "Milan, Italy": (9.1900, 45.4642, 22),
    "Rome, Italy": (12.4964, 41.9028, 22),
    "Lisbon, Portugal": (-9.1393, 38.7223, 18),
    "Brussels, Belgium": (4.3517, 50.8503, 18),
    "Geneva, Switzerland": (6.1432, 46.2044, 15, ["subway", "light_rail", "tram"]),
    "Basel, Switzerland": (7.5886, 47.5596, 15, ["subway", "light_rail", "tram"]),
    "Hamburg, Germany": (9.9937, 53.5511, 22),
    "Frankfurt, Germany": (8.6821, 50.1109, 20),
    "Stuttgart, Germany": (9.1829, 48.7758, 20),
    "Cologne, Germany": (6.9603, 50.9375, 20),
    "Rotterdam, Netherlands": (4.4777, 51.9244, 18),
    "Gothenburg, Sweden": (11.9746, 57.7089, 18, ["subway", "light_rail", "tram"]),
    "Bergen, Norway": (5.3221, 60.3913, 15, ["subway", "light_rail", "tram"]),
    "Lyon, France": (4.8357, 45.7640, 18),
    "Marseille, France": (5.3698, 43.2965, 18),
    "Bilbao, Spain": (-2.9350, 43.2630, 16),
    "Turin, Italy": (7.6869, 45.0703, 18),
    "Naples, Italy": (14.2681, 40.8518, 18),
    "Athens, Greece": (23.7275, 37.9838, 20),
    "Bucharest, Romania": (26.1025, 44.4268, 20),
    "Sofia, Bulgaria": (23.3219, 42.6977, 18),
    "Moscow, Russia": (37.6173, 55.7558, 35),
    "Saint Petersburg, Russia": (30.3351, 59.9343, 28),
    "Kyiv, Ukraine": (30.5234, 50.4501, 25),
    "Minsk, Belarus": (27.5615, 53.9045, 20),
    "Edinburgh, UK": (-3.1883, 55.9533, 16, ["subway", "light_rail", "tram"]),
    "Manchester, UK": (-2.2426, 53.4808, 20, ["subway", "light_rail", "tram"]),
    "Dublin, Ireland": (-6.2603, 53.3498, 18, ["subway", "light_rail", "train", "tram"]),
    "Luxembourg City, Luxembourg": (6.1319, 49.6116, 12, ["subway", "light_rail", "tram"]),
    "Ljubljana, Slovenia": (14.5058, 46.0569, 12, ["train", "bus"]),
    "Zagreb, Croatia": (15.9819, 45.8150, 16, ["subway", "light_rail", "tram"]),

    # --- North America ---
    "New York City, USA": (-74.0060, 40.7128, 30),
    "Toronto, Canada": (-79.3832, 43.6532, 25),
    "Montreal, Canada": (-73.5673, 45.5017, 22),
    "Vancouver, Canada": (-123.1207, 49.2827, 25),
    "Washington, D.C., USA": (-77.0369, 38.9072, 25),
    "Chicago, USA": (-87.6298, 41.8781, 28),
    "Boston, USA": (-71.0589, 42.3601, 22),
    "San Francisco, USA": (-122.4194, 37.7749, 25),
    "Philadelphia, USA": (-75.1652, 39.9526, 25),
    "Mexico City, Mexico": (-99.1332, 19.4326, 30),
    "Ottawa, Canada": (-75.6972, 45.4215, 20),

    # --- South America ---
    "Santiago, Chile": (-70.6693, -33.4489, 25),
    "Buenos Aires, Argentina": (-58.3816, -34.6037, 25),
    "Bogotá, Colombia": (-74.0721, 4.7110, 25, ["bus", "subway", "light_rail"]),
    "Medellín, Colombia": (-75.5644, 6.2518, 18, ["subway", "light_rail", "aerialway"]),
    "São Paulo, Brazil": (-46.6333, -23.5505, 30),
    "Curitiba, Brazil": (-49.2731, -25.4284, 20, ["bus", "subway", "light_rail"]),
    "Rio de Janeiro, Brazil": (-43.1729, -22.9068, 25),
    "Quito, Ecuador": (-78.4678, -0.1807, 20),
    "Lima, Peru": (-77.0428, -12.0464, 25),

    # --- Middle East & Africa ---
    "Dubai, UAE": (55.2708, 25.2048, 25),
    "Doha, Qatar": (51.5310, 25.2854, 20),
    "Tel Aviv, Israel": (34.7818, 32.0853, 20),
    "Istanbul, Turkey": (28.9784, 41.0082, 30),
    "Cairo, Egypt": (31.2357, 30.0444, 25),
    "Cape Town, South Africa": (18.4241, -33.9249, 25, ["train", "subway", "light_rail"]),
    "Addis Ababa, Ethiopia": (38.7578, 9.0192, 18, ["light_rail", "subway"]),

    # --- Oceania ---
    "Melbourne, Australia": (144.9631, -37.8136, 25, ["train", "tram", "subway", "light_rail"]),
    "Sydney, Australia": (151.2093, -33.8688, 28, ["subway", "train", "light_rail", "tram"]),
    "Brisbane, Australia": (153.0251, -27.4698, 25, ["train", "bus", "subway", "light_rail", "tram"]),
    "Auckland, New Zealand": (174.7633, -36.8485, 22, ["train", "bus", "subway", "light_rail"]),
}


def build_city_data(lon, lat, radius_km, route_tags=None):
    delta_lat = radius_km / 111.0
    delta_lon = radius_km / (111.0 * math.cos(math.radians(lat)))

    bbox = [
        round(lon - delta_lon, 4),
        round(lat - delta_lat, 4),
        round(lon + delta_lon, 4),
        round(lat + delta_lat, 4),
    ]
    zoom = round(15.2 - math.log2(radius_km), 1)

    return {
        "bbox": bbox,
        "center": [lon, lat],
        "zoom": zoom,
        "route_tags": route_tags or DEFAULT_ROUTE_TAGS,
    }


CITIES = {
    name: build_city_data(
        data[0],
        data[1],
        data[2],
        data[3] if len(data) > 3 else None
    )
    for name, data in CITY_TARGETS.items()
}


def get_transit_data(bbox, route_tags):
    west, south, east, north = bbox
    tag_filter = "|".join(route_tags)

    query = f"""
    [out:json][timeout:25];
    relation["route"~"^({tag_filter})$"]({south},{west},{north},{east});
    out geom;
    """

    last_error = None
    for mirror_url in OVERPASS_MIRRORS:
        try:
            resp = requests.post(
                mirror_url,
                data={"data": query},
                headers=REQUEST_HEADERS,
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as exc:
            print(f"Overpass mirror failed ({mirror_url}): {exc}")
            last_error = exc
            time.sleep(2)

    raise RuntimeError(f"All Overpass mirrors failed. Last error: {last_error}")


def haversine_distance(lon1, lat1, lon2, lat2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def _encode_signed_number(value):
    value = value << 1
    if value < 0:
        value = ~value
    chunks = []
    while value >= 0x20:
        chunks.append(chr((0x20 | (value & 0x1F)) + 63))
        value >>= 5
    chunks.append(chr(value + 63))
    return "".join(chunks)


def encode_polyline(lat_lon_pairs, precision=5):
    factor = 10 ** precision
    out = []
    prev_lat = 0
    prev_lng = 0
    for lat, lng in lat_lon_pairs:
        lat_i = round(lat * factor)
        lng_i = round(lng * factor)
        out.append(_encode_signed_number(lat_i - prev_lat))
        out.append(_encode_signed_number(lng_i - prev_lng))
        prev_lat, prev_lng = lat_i, lng_i
    return "".join(out)


def simplify_line(coords, min_delta=0.0015):
    if len(coords) < 3:
        return coords
    simplified = [coords[0]]
    last = coords[0]
    for pt in coords[1:-1]:
        if abs(pt[0] - last[0]) < min_delta and abs(pt[1] - last[1]) < min_delta:
            continue
        simplified.append(pt)
        last = pt
    simplified.append(coords[-1])
    return simplified


def process_transit_data(overpass_data, min_delta=0.0015, precision=5):
    """
    Parses OSM relations and separates them into 'metro' (subway, light_rail, train) 
    and 'tram' categories, calculating individual lengths and encoded polylines.
    """
    categories = {
        "metro": {"lines_encoded": [], "seen_ways": set(), "total_km": 0.0, "unique_lines": set()},
        "tram": {"lines_encoded": [], "seen_ways": set(), "total_km": 0.0, "unique_lines": set()}
    }

    for element in overpass_data.get("elements", []):
        if element.get("type") != "relation":
            continue

        tags = element.get("tags", {})
        route_type = tags.get("route", "").lower()
        line_identifier = tags.get("ref") or tags.get("name") or str(element.get("id"))

        # Categorize relation type
        if route_type == "tram":
            target = categories["tram"]
        else:
            target = categories["metro"]

        target["unique_lines"].add(line_identifier)

        for member in element.get("members", []):
            if member.get("type") != "way" or "geometry" not in member:
                continue

            way_id = member.get("ref")
            if way_id in target["seen_ways"]:
                continue
            target["seen_ways"].add(way_id)

            coords = [[pt["lon"], pt["lat"]] for pt in member["geometry"]]
            if len(coords) < 2:
                continue

            for i in range(len(coords) - 1):
                target["total_km"] += haversine_distance(
                    coords[i][0], coords[i][1],
                    coords[i + 1][0], coords[i + 1][1]
                )

            simplified = simplify_line(coords, min_delta=min_delta)
            if len(simplified) < 2:
                continue

            lat_lon_pairs = [(pt[1], pt[0]) for pt in simplified]
            target["lines_encoded"].append(encode_polyline(lat_lon_pairs, precision=precision))

    # Format output for each category
    result = {}
    for key, data in categories.items():
        result[key] = {
            "map_data": ";".join(data["lines_encoded"]),
            "total_km": round(data["total_km"], 1),
            "total_lines": len(data["unique_lines"])
        }

    return result


def run_daily_update():
    city_name, city_data = random.choice(list(CITIES.items()))
    print(f"Selected: {city_name} (zoom: {city_data['zoom']}, bbox: {city_data['bbox']})")
    print(f"Fetching OSM transit data...")

    overpass_data = get_transit_data(city_data["bbox"], city_data["route_tags"])
    processed = process_transit_data(overpass_data)

    metro_data = processed["metro"]
    tram_data = processed["tram"]

    # Combined totals for backward compatibility
    combined_km = round(metro_data["total_km"] + tram_data["total_km"], 1)
    combined_lines = metro_data["total_lines"] + tram_data["total_lines"]
    combined_map_data = f"{metro_data['map_data']};{tram_data['map_data']}".strip(";")

    payload = {
        "merge_variables": {
            "city_name": city_name,
            "lon": city_data["center"][0],
            "lat": city_data["center"][1],
            "zoom": city_data["zoom"],
            
            # --- Separated Data ---
            "metro_map_data": metro_data["map_data"],
            "metro_total_km": metro_data["total_km"],
            "metro_total_lines": metro_data["total_lines"],
            
            "tram_map_data": tram_data["map_data"],
            "tram_total_km": tram_data["total_km"],
            "tram_total_lines": tram_data["total_lines"],
            
            # --- Combined Data (Backward Compatible) ---
            "map_data": combined_map_data,
            "total_km": combined_km,
            "total_lines": combined_lines,
        }
    }

    headers = {"Content-Type": "application/json"}
    resp = requests.post(TRMNL_WEBHOOK_URL, json=payload, headers=headers)

    print(f"TRMNL Updated: {city_name} | Metro: {metro_data['total_lines']} lines ({metro_data['total_km']} km) | Tram: {tram_data['total_lines']} lines ({tram_data['total_km']} km)")
    print(f"Status {resp.status_code}, payload size {len(combined_map_data)} bytes")

    if resp.status_code != 200:
        print("Error response:", resp.text)


if __name__ == "__main__":
    run_daily_update()
