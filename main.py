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
    "Paris, France": (2.3522, 48.8566, 25),
    "Tokyo, Japan": (139.6917, 35.6895, 35),
     "New York City, USA": (-74.0060, 40.7128, 30),
 
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
    it's a real branch point worth preserving as one. Ways are only merged
    within the same is_shared group, never across it, since individual and
    shared track are drawn in different colors downstream.

    Input/output shape: [{"coords": [[lon, lat], ...], "is_shared": bool}, ...]
    """
    remaining = {i: dict(w) for i, w in enumerate(ways)}
    next_id = len(remaining)

    while True:
        endpoints = {}
        for wid, w in remaining.items():
            coords = w["coords"]
            for which, pt in (("start", coords[0]), ("end", coords[-1])):
                key = (_endpoint_key(pt), w["is_shared"])
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

            remaining[next_id] = {"coords": merged_coords, "is_shared": wa["is_shared"]}
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
    but every relation that references it is tracked, so a way used by two
    or more distinct route relations -- i.e. physical track shared by
    multiple lines -- can be flagged via is_shared and drawn differently
    (see run_daily_update, which splits the final way list into a red
    "individual track" payload and a yellow "shared track" payload).
    Contiguous ways are then merged (see merge_contiguous_ways) so a
    physical corridor OSM happened to split into many short ways is
    treated as one line, each merged way is split on any implausible
    node-to-node gap (see split_on_large_gaps, which guards against
    isolated bad OSM data), and finally clipped to the city bbox (see
    clip_line_to_bbox) so geometry outside the visible area never reaches
    simplification/encoding -- one way can yield zero, one, or several runs.
    """
    way_geometry = {}   # way_id -> [[lon, lat], ...], first-seen geometry only
    way_relations = {}  # way_id -> set of relation ids that reference it
    unique_lines = set()

    for element in overpass_data.get("elements", []):
        if element.get("type") != "relation":
            continue

        tags = element.get("tags", {})
        line_identifier = tags.get("ref") or tags.get("name") or str(element.get("id"))
        unique_lines.add(line_identifier)
        relation_id = element.get("id")

        for member in element.get("members", []):
            if member.get("type") != "way" or "geometry" not in member:
                continue

            way_id = member.get("ref")
            if way_id not in way_geometry:
                coords = [[pt["lon"], pt["lat"]] for pt in member["geometry"]]
                if len(coords) < 2:
                    continue
                way_geometry[way_id] = coords

            way_relations.setdefault(way_id, set()).add(relation_id)

    ways = [
        {"coords": coords, "is_shared": len(way_relations.get(way_id, ())) > 1}
        for way_id, coords in way_geometry.items()
    ]
    merged_ways = merge_contiguous_ways(ways)

    raw_ways = []  # [{"coords": [...], "length_km": float, "is_shared": bool}, ...]
    for way in merged_ways:
        is_shared = way["is_shared"]

        for clean_run in split_on_large_gaps(way["coords"]):
            for run in clip_line_to_bbox(clean_run, bbox):
                run_km = 0.0
                for i in range(len(run) - 1):
                    run_km += haversine_distance(
                        run[i][0], run[i][1],
                        run[i + 1][0], run[i + 1][1]
                    )
                raw_ways.append({"coords": run, "length_km": run_km, "is_shared": is_shared})

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

# Budget for the combined encoded route geometry (map_data + map_data_shared
# together), not the whole JSON payload. TRMNL's free-tier limit is ~5KB for
# the whole payload; this leaves headroom for city_name/lon/lat/zoom/
# total_lines and JSON structure overhead.
TARGET_MAP_DATA_BYTES = 4200


def fit_map_data(raw_ways, target_bytes=TARGET_MAP_DATA_BYTES):
    """
    Finds the largest subset of raw_ways (and the simplification tolerance
    to use) whose *combined* polyline encoding fits under target_bytes --
    combined because the budget applies to the total payload regardless of
    how the surviving ways later get split into separate red/yellow
    strings by is_shared (see run_daily_update). This function doesn't do
    that split or the final encoding itself; it just decides what survives.

    First tries increasingly aggressive Douglas-Peucker simplification
    (MIN_DELTA_STEPS), which is capped well short of the tolerance that
    visibly mangles line shape. If the network still doesn't fit at the
    safest max tolerance, switches strategy entirely: instead of
    simplifying further, it drops ways one at a time -- at that same
    fixed, safe tolerance -- until it fits. This keeps every *remaining*
    line looking like a real line, trading completeness for shape rather
    than trading shape for completeness.

    On very large networks (e.g. NYC's subway), dropping can mean removing
    the majority of ways, which risks leaving a scatter of disconnected
    fragments rather than a recognizable network. To keep what's left
    coherent, drop priority favors keeping shared track (is_shared, the
    physically-shared trunk corridors used by multiple lines -- the "spine"
    of the system) over individual/branch track, and only within each of
    those two groups does length break ties, shortest dropped first.

    Returns (final_ways, min_delta_used, ways_dropped).
    """
    for min_delta in MIN_DELTA_STEPS:
        encoded_string = ";".join(encode_ways(raw_ways, min_delta))
        if len(encoded_string.encode("utf-8")) <= target_bytes:
            return raw_ways, min_delta, 0

    max_delta = MIN_DELTA_STEPS[-1]
    # Sort so shared/trunk track and longer ways come first; dropping from
    # the end (shortest cutoff first) removes individual/branch track and
    # short ways before ever touching shared track.
    ways_by_priority = sorted(
        raw_ways, key=lambda w: (not w["is_shared"], -w["length_km"])
    )
    for cutoff in range(len(ways_by_priority) - 1, 0, -1):
        subset = ways_by_priority[:cutoff]
        encoded_string = ";".join(encode_ways(subset, max_delta))
        if len(encoded_string.encode("utf-8")) <= target_bytes:
            return subset, max_delta, len(ways_by_priority) - cutoff

    # Nothing got it under budget -- return the most-reduced attempt we
    # have (the single highest-priority way). TRMNL will likely still
    # reject it, but that's now a rare, loud edge case (visible in the
    # printed payload size / error response) rather than a silent one.
    return ways_by_priority[:1], max_delta, len(ways_by_priority) - 1


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

    # Split the surviving ways by whether their physical track is used by
    # more than one route relation -- shared track (map_data_shared) is
    # drawn in yellow on top of individual track (map_data) in red. Both
    # are encoded at the same min_delta_used so the combined size still
    # matches what fit_map_data() already confirmed fits the budget.
    individual_ways = [w for w in final_ways if not w["is_shared"]]
    shared_ways = [w for w in final_ways if w["is_shared"]]
    map_data = ";".join(encode_ways(individual_ways, min_delta_used))
    map_data_shared = ";".join(encode_ways(shared_ways, min_delta_used))

    if shared_ways:
        print(f"{len(shared_ways)} way segment(s) are shared by multiple lines (drawn in yellow)")

    payload = {
        "merge_variables": {
            "city_name": city_name,
            "lon": city_data["center"][0],
            "lat": city_data["center"][1],
            "zoom": city_data["zoom"],
            "map_data": map_data,
            "map_data_shared": map_data_shared,
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
