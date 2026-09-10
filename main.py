import os
import random
import requests

TRANSITLAND_API_KEY = os.environ.get("TRANSITLAND_API_KEY")
TRMNL_WEBHOOK_URL = os.environ.get("TRMNL_WEBHOOK_URL")

CITIES = {
    "Amsterdam": {"bbox": [4.72, 52.27, 5.05, 52.44], "center": [4.89, 52.36], "zoom": 11},
    "Lyon": {"bbox": [4.74, 45.69, 4.96, 45.83], "center": [4.85, 45.76], "zoom": 11.5},
    "Athens": {"bbox": [23.59, 37.88, 23.90, 38.09], "center": [23.72, 37.98], "zoom": 11}
}

# GTFS route_type reference: 0=tram, 1=subway/metro, 2=rail, 3=bus...
# Set to "1" only if you want strictly metro/subway, no commuter/regional rail.
ROUTE_TYPES = "1,2"


def get_transit_data(bbox):
    url = "https://transit.land/api/v2/rest/routes"
    params = {
        "bbox": ",".join(map(str, bbox)),
        "route_types": ROUTE_TYPES,
        "include_geometry": "true",
        "format": "geojson",
        "limit": 100,  # polyline encoding buys back the headroom the old format spent on decimation
        "apikey": TRANSITLAND_API_KEY,
    }
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    return resp.json()


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
    coords: list of [lon, lat] GeoJSON points.
    Drops points closer than ~150-160m to the last kept point, always
    keeping the first and last point of the line. Polyline encoding is
    compact enough that this can be loosened well below the old 500m cut
    (or removed entirely) if you want smoother curves.
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


def optimize_to_polyline_string(geojson_data, min_delta=0.0015, precision=5):
    """
    Converts GeoJSON into ';'-joined Google encoded polylines, one per line
    geometry. ';' is outside the polyline character range (ASCII 63-126)
    so it's a safe separator.
    """
    lines_encoded = []
    for feature in geojson_data.get("features", []):
        geom = feature.get("geometry")
        if not geom:
            continue

        coords = geom["coordinates"]
        lines = coords if geom["type"] == "MultiLineString" else [coords]

        for line in lines:
            sublines = line if isinstance(line[0][0], list) else [line]
            for subline in sublines:
                simplified = simplify_line(subline, min_delta=min_delta)
                if len(simplified) < 2:
                    continue
                # GeoJSON is [lon, lat]; polyline encoding wants (lat, lon)
                lat_lon_pairs = [(pt[1], pt[0]) for pt in simplified]
                lines_encoded.append(encode_polyline(lat_lon_pairs, precision=precision))

    return ";".join(lines_encoded)


def run_daily_update():
    city_name, city_data = random.choice(list(CITIES.items()))
    print(f"Fetching transit data for {city_name}...")

    raw_geojson = get_transit_data(city_data["bbox"])
    encoded_string = optimize_to_polyline_string(raw_geojson)

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
