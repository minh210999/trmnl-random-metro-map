import os
import random
import time
import requests
import math

TRMNL_WEBHOOK_URL = os.environ.get("TRMNL_WEBHOOK_URL")

CITIES = {
    "Amsterdam": {"bbox": [4.72, 52.27, 5.05, 52.44], "center": [4.89, 52.36], "zoom": 11},
    "Lyon": {"bbox": [4.74, 45.69, 4.96, 45.83], "center": [4.85, 45.76], "zoom": 11.5},
    "Athens": {"bbox": [23.59, 37.88, 23.90, 38.09], "center": [23.72, 37.98], "zoom": 11}
}

ROUTE_TAGS = ["subway"]

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

def get_transit_data(bbox):
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
            time.sleep(2)

    raise RuntimeError(f"All Overpass mirrors failed. Last error: {last_error}")


def haversine_distance(lon1, lat1, lon2, lat2):
    """Calculate the great-circle distance between two points on Earth in kilometers."""
    R = 6371.0 # Earth radius in kilometers
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2)**2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2)
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
    Parses OSM relations, calculates total network km, counts unique lines,
    and returns encoded polylines for the TRMNL map component.
    """
    lines_encoded = []
    seen_way_ids = set()
    total_km = 0.0
    unique_lines = set()

    for element in overpass_data.get("elements", []):
        if element.get("type") != "relation":
            continue

        # 1. Count distinct lines based on 'ref' or 'name' tags
        tags = element.get("tags", {})
        line_identifier = tags.get("ref") or tags.get("name") or str(element.get("id"))
        unique_lines.add(line_identifier)

        for member in element.get("members", []):
            if member.get("type") != "way" or "geometry" not in member:
                continue 

            way_id = member.get("ref")
            if way_id in seen_way_ids:
                continue
            seen_way_ids.add(way_id)

            coords = [[pt["lon"], pt["lat"]] for pt in member["geometry"]]
            if len(coords) < 2:
                continue

            # 2. Calculate accurate distance BEFORE simplify_line drops points
            for i in range(len(coords) - 1):
                total_km += haversine_distance(
                    coords[i][0], coords[i][1],
                    coords[i+1][0], coords[i+1][1]
                )

            # 3. Simplify and encode for the map
            simplified = simplify_line(coords, min_delta=min_delta)
            if len(simplified) < 2:
                continue

            lat_lon_pairs = [(pt[1], pt[0]) for pt in simplified]
            lines_encoded.append(encode_polyline(lat_lon_pairs, precision=precision))

    encoded_string = ";".join(lines_encoded)
    return encoded_string, round(total_km, 1), len(unique_lines)


def run_daily_update():
    city_name, city_data = random.choice(list(CITIES.items()))
    print(f"Fetching OSM transit data for {city_name}...")

    overpass_data = get_transit_data(city_data["bbox"])
    
    # Unpack the three returned values
    encoded_string, total_km, total_lines = process_transit_data(overpass_data)

    payload = {
        "merge_variables": {
            "city_name": city_name,
            "lon": city_data["center"][0],
            "lat": city_data["center"][1],
            "zoom": city_data["zoom"],
            "map_data": encoded_string,
            "total_km": total_km,           # <-- NEW
            "total_lines": total_lines      # <-- NEW
        }
    }

    headers = {"Content-Type": "application/json"}
    resp = requests.post(TRMNL_WEBHOOK_URL, json=payload, headers=headers)
    
    print(f"TRMNL Updated: {city_name} | {total_lines} lines | {total_km} km")
    print(f"Status {resp.status_code}, payload size {len(encoded_string)} bytes")

    if resp.status_code != 200:
        print("Error response:", resp.text)


if __name__ == "__main__":
    run_daily_update()
