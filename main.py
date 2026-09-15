import json
import math
import os
import random
import time
import requests

TRMNL_WEBHOOK_URL = os.environ.get("TRMNL_WEBHOOK_URL")

DEFAULT_ROUTE_TAGS = ["subway", "light_rail"]

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
# Radius determines both the spatial bounding box and the auto-calculated map zoom.
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
    "Zurich, Switzerland": (8.5417, 47.3769, 15, 
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
    "Geneva, Switzerland": (6.1432, 46.2044, 15, 
    "Basel, Switzerland": (7.5886, 47.5596, 15, 
    "Hamburg, Germany": (9.9937, 53.5511, 22),
    "Frankfurt, Germany": (8.6821, 50.1109, 20),
    "Stuttgart, Germany": (9.1829, 48.7758, 20),
    "Cologne, Germany": (6.9603, 50.9375, 20),
    "Rotterdam, Netherlands": (4.4777, 51.9244, 18),
    "Gothenburg, Sweden": (11.9746, 57.7089, 18, 
    "Bergen, Norway": (5.3221, 60.3913, 15, 
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
    "Edinburgh, UK": (-3.1883, 55.9533, 16, 
    "Manchester, UK": (-2.2426, 53.4808, 20, 
    "Dublin, Ireland": (-6.2603, 53.3498, 18, 
    "Luxembourg City, Luxembourg": (6.1319, 49.6116, 12, 
    "Ljubljana, Slovenia": (14.5058, 46.0569, 12, ["train", "bus"]),
    "Zagreb, Croatia": (15.9819, 45.8150, 16, 

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
    "Bogotá, Colombia": (-74.0721, 4.7110, 25, 
    "Medellín, Colombia": (-75.5644, 6.2518, 18, 
    "São Paulo, Brazil": (-46.6333, -23.5505, 30),
    "Curitiba, Brazil": (-49.2731, -25.4284, 20, 
    "Rio de Janeiro, Brazil": (-43.1729, -22.9068, 25),
    "Quito, Ecuador": (-78.4678, -0.1807, 20),
    "Lima, Peru": (-77.0428, -12.0464, 25),

    # --- Middle East & Africa ---
    "Dubai, UAE": (55.2708, 25.2048, 25),
    "Doha, Qatar": (51.5310, 25.2854, 20),
    "Tel Aviv, Israel": (34.7818, 32.0853, 20),
    "Istanbul, Turkey": (28.9784, 41.0082, 30),
    "Cairo, Egypt": (31.2357, 30.0444, 25),
    "Cape Town, South Africa": (18.4241, -33.9249, 25, 
    "Addis Ababa, Ethiopia": (38.7578, 9.0192, 18, 
    # --- Oceania ---
    "Melbourne, Australia": (144.9631, -37.8136, 25,  
    "Sydney, Australia": (151.2093, -33.8688, 28, 
    "Brisbane, Australia": (153.0251, -27.4698, 25, 
    "Auckland, New Zealand": (174.7633, -36.8485, 22, 
}


def build_city_data(lon, lat, radius_km, route_tags=None):
    """
    Derives [west, south, east, north] bounding box and zoom level dynamically
    from the center coordinate and network extent radius in kilometers.
    """
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
    """Calculate the great-circle distance between two points on Earth in kilometers."""
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
    # precision must stay at 5 -- the TRMNL plugin (transit_map.html) decodes
    # these with TRMNLMaps.decodePolyline(), which assumes the standard
    # Google polyline precision. Changing this number without also updating
    # the decoder will make every route render in the wrong place/shape.
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


def _perpendicular_distance(pt, line_start, line_end):
    x0, y0 = pt
    x1, y1 = line_start
    x2, y2 = line_end
    if (x1, y1) == (x2, y2):
        return math.hypot(x0 - x1, y0 - y1)
    num = abs((y2 - y1) * x0 - (x2 - x1) * y0 + x2 * y1 - y2 * x1)
    den = math.hypot(y2 - y1, x2 - x1)
    return num / den


def douglas_peucker(points, epsilon):
    """
    Douglas-Peucker line simplification (perpendicular-distance based).
    Iterative (stack-based) rather than recursive so it doesn't blow
    Python's recursion limit on very long, point-dense ways. epsilon is in
    degrees.
    """
    if len(points) < 3:
        return points

    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]

    while stack:
        start, end = stack.pop()
        if end - start < 2:
            continue
        dmax = 0.0
        index = start
        for i in range(start + 1, end):
            d = _perpendicular_distance(points[i], points[start], points[end])
            if d > dmax:
                dmax = d
                index = i
        if dmax > epsilon:
            keep[index] = True
            stack.append((start, index))
            stack.append((index, end))

    return [points[i] for i in range(len(points)) if keep[i]]


def _clip_segment_to_bbox(p0, p1, bbox):
    """Liang-Barsky clip of one line segment against an axis-aligned bbox
    [west, south, east, north]. Returns ((x0,y0), (x1,y1)) for the portion
    of the segment inside the box, or None if none of it is inside."""
    x0, y0 = p0
    x1, y1 = p1
    west, south, east, north = bbox
    dx = x1 - x0
    dy = y1 - y0
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x0 - west), (dx, east - x0), (-dy, y0 - south), (dy, north - y0)):
        if p == 0:
            if q < 0:
                return None  # segment parallel to this edge and outside it
        else:
            t = q / p
            if p < 0:
                if t > t1:
                    return None
                if t > t0:
                    t0 = t
            else:
                if t < t0:
                    return None
                if t < t1:
                    t1 = t
    if t0 > t1:
        return None
    return (x0 + t0 * dx, y0 + t0 * dy), (x0 + t1 * dx, y0 + t1 * dy)


# Max plausible distance (km) between two *consecutive* geometry nodes of
# the same OSM way. Overpass normally returns rail/tram way geometry with
# nodes every few dozen to a few hundred meters; a gap far beyond that is
# almost always a data glitch (a mis-digitized or misplaced node) rather
# than a real stretch of track.
MAX_NODE_GAP_KM = 1.5


def split_on_large_gaps(coords, max_gap_km=MAX_NODE_GAP_KM):
    """
    Splits a way's coordinate list wherever two consecutive nodes are
    implausibly far apart. This has to run *before* Douglas-Peucker
    simplification, not after: DP specifically keeps whichever point
    deviates most from its neighbors and discards the ones that agree with
    it, which is exactly backwards for a single glitchy node -- it doesn't
    get smoothed away, it gets preserved and everything around it gets
    thinned out, leaving one long spurious straight line pointing at it.

    Splitting the way here means a bad node just breaks its way into two
    clean runs instead of producing a stray line cutting across the map.

    Returns a list of coordinate runs, each internally within the gap
    threshold (each run has >= 2 points, or the list is empty).
    """
    if len(coords) < 2:
        return []

    runs = []
    current = [coords[0]]
    for i in range(1, len(coords)):
        gap_km = haversine_distance(
            coords[i - 1][0], coords[i - 1][1], coords[i][0], coords[i][1]
        )
        if gap_km > max_gap_km:
            if len(current) >= 2:
                runs.append(current)
            current = [coords[i]]
        else:
            current.append(coords[i])
    if len(current) >= 2:
        runs.append(current)
    return runs


def clip_line_to_bbox(coords, bbox, pad_ratio=0.25):
    """
    Clips a way's coordinate list against the city bbox, dropping the
    portions that fall outside it. Overpass's relation bbox filter only
    guarantees *some part* of a route relation intersects the query box --
    regional/mainline routes that merely clip a corner of the city can come
    back with geometry stretching for hundreds of km outside it, all of
    which would otherwise get simplified/encoded/sent for no visual benefit
    (it's off-screen).

    Returns a list of contiguous coordinate runs (a way that exits and
    re-enters the box becomes multiple runs, since there's no line to draw
    across the gap). Each run has >= 2 points, or the list is empty.

    The box is padded by pad_ratio (default 25% of its width/height) before
    clipping, since the actual rendered viewport (MapLibre center+zoom) can
    show a bit more than the nominal query bbox depending on device aspect
    ratio -- better to keep a little extra geometry than to visibly clip a
    line that's still on screen.
    """
    west, south, east, north = bbox
    pad_lon = (east - west) * pad_ratio
    pad_lat = (north - south) * pad_ratio
    padded_bbox = [west - pad_lon, south - pad_lat, east + pad_lon, north + pad_lat]

    runs = []
    current = []
    for i in range(len(coords) - 1):
        clipped = _clip_segment_to_bbox(coords[i], coords[i + 1], padded_bbox)
        if clipped is None:
            if len(current) >= 2:
                runs.append(current)
            current = []
            continue

        (cx0, cy0), (cx1, cy1) = clipped
        if not current or abs(current[-1][0] - cx0) > 1e-9 or abs(current[-1][1] - cy0) > 1e-9:
            if len(current) >= 2:
                runs.append(current)
            current = [[cx0, cy0]]
        current.append([cx1, cy1])

    if len(current) >= 2:
        runs.append(current)
    return runs


def _endpoint_key(pt):
    # Round to ~1cm precision. Two ways share a real OSM node when their
    # endpoint coordinates are exact matches (Overpass emits the same
    # underlying node data for both), so this is just enough rounding to
    # absorb float formatting noise without ever conflating two genuinely
    # distinct, merely-nearby points (parallel tracks are meters apart, not
    # centimeters).
    return (round(pt[0], 7), round(pt[1], 7))


def merge_contiguous_ways(ways):
    """
    Merges ways that are physically continuous -- one way's endpoint
    exactly matches another's -- into a single longer polyline.

    OSM digitizes one physical line as many short ways, broken wherever
    roads/tracks intersect or a tag changes slightly -- an artifact of how
    the map was edited, not a real boundary in the track. Left alone, every
    one of those arbitrary breaks pays its own polyline "first point"
    encoding cost and gets Douglas-Peucker'd in isolation, unable to see
    the shape of the corridor as a whole. Merging them first is a pure
    efficiency/quality win: no geometry is lost or altered, it's just
    represented as fewer, longer lines.

    Two ways are merged only at a point where *exactly* two way-ends meet
    (a simple pass-through) -- a junction where three or more ways meet is
    left alone, since there's no single unambiguous line to continue, and
    it's a real branch point worth preserving as one.

    Input/output shape: [{"coords": [[lon, lat], ...]}, ...]
    """
    remaining = {i: dict(w) for i, w in enumerate(ways)}
    next_id = len(remaining)

    while True:
        endpoints = {}
        for wid, w in remaining.items():
            coords = w["coords"]
            for which, pt in (("start", coords[0]), ("end", coords[-1])):
                key = _endpoint_key(pt)
                endpoints.setdefault(key, []).append((wid, which))

        merged_any = False
        for touching in endpoints.values():
            if len(touching) != 2:
                continue  # 0/1: a dead end; 3+: a real junction -- leave alone

            (wid_a, end_a), (wid_b, end_b) = touching
            if wid_a == wid_b:
                continue  # a loop way meeting itself -- not a merge

            wa = remaining[wid_a]
            wb = remaining[wid_b]

            a_coords = wa["coords"][:]
            b_coords = wb["coords"][:]
            if end_a == "start":
                a_coords.reverse()
            if end_b == "end":
                b_coords.reverse()
            # a_coords now ends where b_coords begins
            merged_coords = a_coords + b_coords[1:]

            remaining[next_id] = {"coords": merged_coords}
            next_id += 1
            del remaining[wid_a]
            del remaining[wid_b]
            merged_any = True
            break  # ids changed -- rebuild the endpoint index before continuing

        if not merged_any:
            break

    return list(remaining.values())


def collect_transit_ways(overpass_data, bbox):
    """
    Extracts deduped, bbox-clipped way geometries plus the unique line count
    from a raw Overpass response. Geometry is returned unsimplified/
    unencoded, along with each run's own length -- fit_map_data() uses that
    length to decide what to drop if the network doesn't fit the byte
    budget even at the safest simplification tolerance (total km is not
    tracked here since it's no longer part of the displayed payload).

    A way is deduped to a single geometry (seen once, keyed by OSM way id)
    because multiple transit lines often share physical track, and without
    dedup that shared track would be counted and drawn multiple times.
    Contiguous ways are then merged (see merge_contiguous_ways) so a
    physical corridor OSM happened to split into many short ways is
    treated as one line, each merged way is split on any implausible
    node-to-node gap (see split_on_large_gaps, which guards against
    isolated bad OSM data), and finally clipped to the city bbox (see
    clip_line_to_bbox) so geometry outside the visible area never reaches
    simplification/encoding -- one way can yield zero, one, or several runs.
    """
    way_geometry = {}  # way_id -> [[lon, lat], ...], first-seen geometry only
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
            if way_id in way_geometry:
                continue

            coords = [[pt["lon"], pt["lat"]] for pt in member["geometry"]]
            if len(coords) < 2:
                continue
            way_geometry[way_id] = coords

    ways = [{"coords": coords} for coords in way_geometry.values()]
    merged_ways = merge_contiguous_ways(ways)

    raw_ways = []  # [{"coords": [...], "length_km": float}, ...]
    for way in merged_ways:
        for clean_run in split_on_large_gaps(way["coords"]):
            for run in clip_line_to_bbox(clean_run, bbox):
                run_km = 0.0
                for i in range(len(run) - 1):
                    run_km += haversine_distance(
                        run[i][0], run[i][1],
                        run[i + 1][0], run[i + 1][1]
                    )
                raw_ways.append({"coords": run, "length_km": run_km})

    return raw_ways, len(unique_lines)


def encode_ways(raw_ways, min_delta, precision=5):
    """
    Simplify (Douglas-Peucker) then polyline-encode a set of way geometries
    at a given simplification tolerance.

    Coordinates are encoded as standard absolute WGS84 lat/lng pairs, at the
    standard Google polyline precision (5), so the plugin side can decode
    them with a stock, unmodified TRMNLMaps.decodePolyline() call -- no
    center-offset compensation needed on the HTML side.
    """
    encoded = []
    for way in raw_ways:
        simplified = douglas_peucker(way["coords"], min_delta)
        if len(simplified) < 2:
            continue
        lat_lon_pairs = [(pt[1], pt[0]) for pt in simplified]
        encoded.append(encode_polyline(lat_lon_pairs, precision=precision))
    return encoded


# Simplification tolerances to try, in increasing order (degrees). Capped at
# 0.006 (~650m) -- well below the point where Douglas-Peucker starts
# collapsing lines into a handful of straight chords (the "everything looks
# triangulated" failure mode seen on dense networks like Copenhagen's radial
# S-train system). If the network still doesn't fit at this tolerance,
# fit_map_data() drops whole ways instead of simplifying further.
MIN_DELTA_STEPS = [0.0015, 0.0025, 0.004, 0.006]

# Budget for the encoded map_data string alone, not the whole JSON payload.
# TRMNL's free-tier limit is ~5KB for the whole payload; this leaves
# headroom for city_name/lon/lat/zoom/total_lines and JSON structure
# overhead.
TARGET_MAP_DATA_BYTES = 4200


def fit_map_data(raw_ways, target_bytes=TARGET_MAP_DATA_BYTES):
    """
    Finds the largest subset of raw_ways (and the simplification tolerance
    to use) whose combined polyline encoding fits under target_bytes. This
    function doesn't do the final encoding itself; it just decides what
    survives.

    First tries increasingly aggressive Douglas-Peucker simplification
    (MIN_DELTA_STEPS), which is capped well short of the tolerance that
    visibly mangles line shape. If the network still doesn't fit at the
    safest max tolerance, switches strategy entirely: instead of
    simplifying further, it drops the shortest way geometries (usually
    spurs/branches) one at a time -- at that same fixed, safe tolerance --
    until it fits. This keeps every *remaining* line looking like a real
    line, trading completeness for shape rather than trading shape for
    completeness.

    Returns (final_ways, min_delta_used, ways_dropped).
    """
    for min_delta in MIN_DELTA_STEPS:
        encoded_string = ";".join(encode_ways(raw_ways, min_delta))
        if len(encoded_string.encode("utf-8")) <= target_bytes:
            return raw_ways, min_delta, 0

    max_delta = MIN_DELTA_STEPS[-1]
    ways_by_length = sorted(raw_ways, key=lambda w: w["length_km"], reverse=True)
    for cutoff in range(len(ways_by_length) - 1, 0, -1):
        subset = ways_by_length[:cutoff]
        encoded_string = ";".join(encode_ways(subset, max_delta))
        if len(encoded_string.encode("utf-8")) <= target_bytes:
            return subset, max_delta, len(ways_by_length) - cutoff

    # Nothing got it under budget -- return the most-reduced attempt we
    # have (the single longest way). TRMNL will likely still reject it,
    # but that's now a rare, loud edge case (visible in the printed
    # payload size / error response) rather than a silent one.
    return ways_by_length[:1], max_delta, len(ways_by_length) - 1


def run_daily_update():
    city_name, city_data = random.choice(list(CITIES.items()))
    print(f"Selected: {city_name} (zoom: {city_data['zoom']}, bbox: {city_data['bbox']})")
    print("Fetching OSM transit data...")

    overpass_data = get_transit_data(city_data["bbox"], city_data["route_tags"])
    raw_ways, total_lines = collect_transit_ways(overpass_data, city_data["bbox"])
    final_ways, min_delta_used, ways_dropped = fit_map_data(raw_ways)

    if min_delta_used != MIN_DELTA_STEPS[0]:
        print(f"Simplification tolerance raised to {min_delta_used} to fit payload budget")
    if ways_dropped:
        print(f"Warning: dropped {ways_dropped} short way segment(s) to fit payload budget")

    map_data = ";".join(encode_ways(final_ways, min_delta_used))

    payload = {
        "merge_variables": {
            "city_name": city_name,
            "lon": city_data["center"][0],
            "lat": city_data["center"][1],
            "zoom": city_data["zoom"],
            "map_data": map_data,
            "total_lines": total_lines,
        }
    }

    # Compact separators shave a few bytes off the JSON body.
    body = json.dumps(payload, separators=(",", ":"))
    headers = {"Content-Type": "application/json"}
    resp = requests.post(TRMNL_WEBHOOK_URL, data=body, headers=headers)

    print(f"TRMNL Updated: {city_name} | {total_lines} lines")
    print(f"Status {resp.status_code}, payload size {len(body.encode('utf-8'))} bytes")

    if resp.status_code != 200:
        print("Error response:", resp.text)


if __name__ == "__main__":
    run_daily_update()
