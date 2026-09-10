import os
import random
import time
import requests
import math

TRMNL_WEBHOOK_URL = os.environ.get("TRMNL_WEBHOOK_URL")

# Cleaned list of 99 unique cities
CITIES_LIST = [
    "Tokyo, Japan", "Osaka, Japan", "Hong Kong", "Seoul, South Korea", "Singapore", 
    "Shanghai, China", "Beijing, China", "Shenzhen, China", "Guangzhou, China", 
    "Taipei, Taiwan", "Nagoya, Japan", "Kyoto, Japan", "Busan, South Korea", 
    "Chengdu, China", "Wuhan, China", "Kuala Lumpur, Malaysia", "Bangkok, Thailand", 
    "Jakarta, Indonesia", "Delhi, India", "Mumbai, India", "Ho Chi Minh City, Vietnam",
    "Zurich, Switzerland", "Vienna, Austria", "Munich, Germany", "Berlin, Germany", 
    "Paris, France", "London, UK", "Madrid, Spain", "Barcelona, Spain", 
    "Amsterdam, Netherlands", "Copenhagen, Denmark", "Stockholm, Sweden", 
    "Helsinki, Finland", "Oslo, Norway", "Prague, Czech Republic", "Budapest, Hungary", 
    "Warsaw, Poland", "Milan, Italy", "Rome, Italy", "Lisbon, Portugal", 
    "Brussels, Belgium", "Geneva, Switzerland", "Basel, Switzerland", "Hamburg, Germany", 
    "Frankfurt, Germany", "Stuttgart, Germany", "Cologne, Germany", "Rotterdam, Netherlands", 
    "Gothenburg, Sweden", "Bergen, Norway", "Lyon, France", "Marseille, France", 
    "Bilbao, Spain", "Turin, Italy", "Naples, Italy", "Athens, Greece", 
    "Bucharest, Romania", "Sofia, Bulgaria", "Moscow, Russia", "Saint Petersburg, Russia", 
    "Kyiv, Ukraine", "Minsk, Belarus", "Edinburgh, UK", "Manchester, UK", "Dublin, Ireland", 
    "Luxembourg City, Luxembourg", "Ljubljana, Slovenia", "Zagreb, Croatia",
    "New York City, USA", "Toronto, Canada", "Montreal, Canada", "Vancouver, Canada", 
    "Washington, D.C., USA", "Chicago, USA", "Boston, USA", "San Francisco, USA", 
    "Philadelphia, USA", "Mexico City, Mexico", "Ottawa, Canada",
    "Santiago, Chile", "Buenos Aires, Argentina", "Bogotá, Colombia", "Medellín, Colombia", 
    "São Paulo, Brazil", "Curitiba, Brazil", "Rio de Janeiro, Brazil", "Quito, Ecuador", 
    "Lima, Peru", "Dubai, UAE", "Doha, Qatar", "Tel Aviv, Israel", "Istanbul, Turkey", 
    "Cairo, Egypt", "Cape Town, South Africa", "Addis Ababa, Ethiopia",
    "Melbourne, Australia", "Sydney, Australia", "Brisbane, Australia", "Auckland, New Zealand"
]

# Expanded to catch light rail and trams since some listed cities don't have heavy subways
ROUTE_TAGS = ["subway", "light_rail", "tram", "monorail"]

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

def geocode_city(city_name):
    """
    Uses OSM Nominatim to fetch the bounding box and center coordinates for a city name.
    """
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": city_name,
        "format": "json",
        "limit": 1
    }
    resp = requests.get(url, params=params, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    
    if not data:
        raise ValueError(f"Could not find coordinates for {city_name}")
        
    place = data[0]
    # Nominatim bbox format: [south, north, west, east]
    south, north, west, east = place["boundingbox"]
    
    return {
        "bbox": [float(west), float(south), float(east), float(north)],
        "center": [float(place["lon"]), float(place["lat"])],
        "zoom": 11.5 # Default zoom level for city-scale view
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
    R = 6371.0 
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
    lines_encoded = []
    seen_way_ids = set()
    total_km = 0.0
    unique_lines = set()

    for element in overpass_data.get("elements", []):
        if element.get("type") != "relation":
            continue

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

            for i in range(len(coords) - 1):
                total_km += haversine_distance(
                    coords[i][0], coords[i][1],
                    coords[i+1][0], coords[i+1][1]
                )

            simplified = simplify_line(coords, min_delta=min_delta)
            if len(simplified) < 2:
                continue

            lat_lon_pairs = [(pt[1], pt[0]) for pt in simplified]
            lines_encoded.append(encode_polyline(lat_lon_pairs, precision=precision))

    encoded_string = ";".join(lines_encoded)
    return encoded_string, round(total_km, 1), len(unique_lines)


def run_daily_update():
    max_retries = 3
    
    # Retry loop in case a randomly selected city throws a geocoding error or has no transit
    for attempt in range(max_retries):
        city_name = random.choice(CITIES_LIST)
        print(f"\nAttempt {attempt + 1}: Fetching OSM transit data for {city_name}...")
        
        try:
            city_data = geocode_city(city_name)
            overpass_data = get_transit_data(city_data["bbox"])
            encoded_string, total_km, total_lines = process_transit_data(overpass_data)
            
            # If the query succeeded but returned 0 lines, pick another city
            if total_lines == 0:
                print(f"No valid transit routes found in {city_name}. Retrying...")
                continue
                
            payload = {
                "merge_variables": {
                    # Strip the country part so the title is cleaner (e.g. just "Tokyo")
                    "city_name": city_name.split(",")[0],
                    "lon": city_data["center"][0],
                    "lat": city_data["center"][1],
                    "zoom": city_data["zoom"],
                    "map_data": encoded_string,
                    "total_km": total_km,
                    "total_lines": total_lines
                }
            }

            headers = {"Content-Type": "application/json"}
            resp = requests.post(TRMNL_WEBHOOK_URL, json=payload, headers=headers)
            
            print(f"Success! Map of {city_name.split(',')[0]} generated.")
            print(f"Lines: {total_lines} | Length: {total_km}km | Payload: {len(encoded_string)} bytes")
            
            if resp.status_code != 200:
                print("TRMNL Error response:", resp.text)
                
            break # Exit the retry loop on success

        except Exception as e:
            print(f"Error processing {city_name}: {e}")
            time.sleep(2)

if __name__ == "__main__":
    run_daily_update()
