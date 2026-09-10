import os
import random
import time
import requests

TRMNL_WEBHOOK_URL = os.environ.get("TRMNL_WEBHOOK_URL")

CITIES = {
    "Amsterdam": {"bbox": [4.72, 52.27, 5.05, 52.44], "center": [4.89, 52.36], "zoom": 11},
    "Lyon": {"bbox": [4.74, 45.69, 4.96, 45.83], "center": [4.85, 45.76], "zoom": 11.5},
    "Athens": {"bbox": [23.59, 37.88, 23.90, 38.09], "center": [23.72, 37.98], "zoom": 11}
}

# OSM route=* values to include. "subway" alone is the closest match to
# "metro". Add "light_rail" and/or "tram" to widen the net per city.
ROUTE_TAGS = ["subway"]

# overpass-api.de has been actively rate-limiting/banning automated traffic
# (shared CI IP ranges look like "large scale" abuse to it), returning 406 or
# 504 even for well-formed queries. Try several mirrors in order and fall
# back automatically instead of depending on one instance staying up.
OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

# A real, identifying User-Agent (and Referer) is required by Overpass's
# current usage policy -- generic/library-default headers get blocked.
# Put a real repo/contact URL here; GitHub Actions can inject one via env.
CONTACT_URL = os.environ.get("OVERPASS_CONTACT_URL", "https://github.com/your-org/trmnl-random-metro-map")
REQUEST_HEADERS = {
    "User-Agent": f"trmnl-random-metro-map/1.0 ({CONTACT_URL})",
    "Referer": CONTACT_URL,
    "Content-Type": "text/plain",
}


def get_transit_data(bbox):
    """
    bbox: [west, south, east, north] (same convention the CITIES dict already uses).
    Overpass wants (south, west, north, east) in its bbox filter.
    Tries each mirror in OVERPASS_MIRRORS until one succeeds.
    """
    west, south, east, north = bbox
    tag_filter = "|".join(ROUTE_TAGS)

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
            time.sleep(2)  # brief backoff before trying the next mirror

    raise RuntimeError(f"All Overpass mirrors failed. Last error: {last_error}")


def _encode_signed_number(value):
    """Encode a single delta as Google polyline chars."""
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
    """
    Standard Google Encoded Polyline Algorithm (same format Strava uses,
    and what TRMNLMaps.decodePolyline() expects on the render side).
    lat_lon_pairs: list of (lat, lon) tuples, in that order.
    """
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
    """
    coords: list of [lon, lat] points.
    Drops points closer than ~150-160m to the last kept point, always
    keeping the first and last point of the line.
    """
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


def optimize_to_polyline_string(overpass_data, min_delta=0.0015, precision=5):
    """
    Converts Overpass 'out geom' relations into ';'-joined Google encoded
    polylines, one per way segment. Ways shared by multiple route variants
    (common where lines share trunk track) are only encoded once.
    """
    lines_encoded = []
    seen_way_ids = set()

    for element in overpass_data.get("elements", []):
        if element.get("type") != "relation":
            continue

        for member in element.get("members", []):
            if member.get("type") != "way" or "geometry" not in member:
                continue  # skip station/platform node members etc.

            way_id = member.get("ref")
            if way_id in seen_way_ids:
                continue
            seen_way_ids.add(way_id)

            coords = [[pt["lon"], pt["lat"]] for pt in member["geometry"]]
            if len(coords) < 2:
                continue

            simplified = simplify_line(coords, min_delta=min_delta)
            if len(simplified) < 2:
                continue

            # polyline encoding wants (lat, lon)
            lat_lon_pairs = [(pt[1], pt[0]) for pt in simplified]
            lines_encoded.append(encode_polyline(lat_lon_pairs, precision=precision))

    return ";".join(lines_encoded)


def run_daily_update():
    city_name, city_data = random.choice(list(CITIES.items()))
    print(f"Fetching OSM transit data for {city_name}...")

    overpass_data = get_transit_data(city_data["bbox"])
    encoded_string = optimize_to_polyline_string(overpass_data)

    payload = {
        "merge_variables": {
            "city_name": city_name,
            "lon": city_data["center"][0],
            "lat": city_data["center"][1],
            "zoom": city_data["zoom"],
            "map_data": encoded_string,
        }
    }

    headers = {"Content-Type": "application/json"}
    resp = requests.post(TRMNL_WEBHOOK_URL, json=payload, headers=headers)
    print(f"TRMNL Updated: Status {resp.status_code}, payload size {len(encoded_string)} bytes")

    if resp.status_code != 200:
        print("Error response:", resp.text)


if __name__ == "__main__":
    run_daily_update()
