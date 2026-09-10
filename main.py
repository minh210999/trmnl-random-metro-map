import os
import math
import random
import requests

# 1. Configuration - Reading from GitHub Secrets securely
TRANSITLAND_API_KEY = os.environ.get("TRANSITLAND_API_KEY")
TRMNL_WEBHOOK_URL = os.environ.get("TRMNL_WEBHOOK_URL")

# Bounding boxes for cities: [min_lon, min_lat, max_lon, max_lat]
CITIES = {
    "Amsterdam": [4.72, 52.27, 5.05, 52.44],
    "Lyon": [4.74, 45.69, 4.96, 45.83],
    "Athens": [23.59, 37.88, 23.90, 38.09]
}

def get_transit_data(bbox):
    """Fetches Subway and Rail data from Transitland API"""
    url = "https://transit.land/api/v2/rest/routes"
    params = {
        "bbox": ",".join(map(str, bbox)),
        "route_types": "1,2", # 1 = Subway, 2 = Rail
        "include_geometry": "true",
        "format": "geojson",
        "limit": 200,
        "apikey": TRANSITLAND_API_KEY
    }
    
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()

def geojson_to_svg(geojson_data, width=800, height=480, padding=30):
    """Converts GeoJSON coordinates into an SVG scaled to fit the TRMNL screen"""
    min_x, max_x = float('inf'), float('-inf')
    min_y, max_y = float('inf'), float('-inf')

    # 1. Find boundaries of the data
    for feature in geojson_data.get('features', []):
        geom = feature.get('geometry')
        if not geom: continue
        coords = geom['coordinates']
        lines = coords if geom['type'] == 'MultiLineString' else [coords]
        
        for line in lines:
            for pt in line:
                # Handle possible deeply nested coordinate arrays from MultiLineStrings
                pts = pt if isinstance(pt[0], list) else [pt]
                for p in pts:
                    min_x, max_x = min(min_x, p[0]), max(max_x, p[0])
                    min_y, max_y = min(min_y, p[1]), max(max_y, p[1])

    # 2. Handle map distortion (adjust width scale by latitude)
    lat_rad = math.radians((min_y + max_y) / 2) if max_y != float('-inf') else 1
    aspect_correction = math.cos(lat_rad)

    range_x = (max_x - min_x) * aspect_correction or 1
    range_y = max_y - min_y or 1
    
    # Calculate scale to fit within the TRMNL screen
    scale = min((width - 2 * padding) / range_x, (height - 2 * padding) / range_y)
    
    # Center the map
    x_offset = (width - (range_x * scale)) / 2
    y_offset = (height - (range_y * scale)) / 2

    # 3. Map Coordinates to SVG paths
    svg_paths = []
    for feature in geojson_data.get('features', []):
        geom = feature.get('geometry')
        if not geom: continue
        coords = geom['coordinates']
        lines = coords if geom['type'] == 'MultiLineString' else [coords]
        
        for line in lines:
            sublines = line if isinstance(line[0][0], list) else [line]
            for subline in sublines:
                path_d = []
                for i, pt in enumerate(subline):
                    px = ((pt[0] - min_x) * aspect_correction) * scale + x_offset
                    py = height - ((pt[1] - min_y) * scale + y_offset) # Invert Y for SVG (0,0 is top-left)
                    
                    cmd = "M" if i == 0 else "L"
                    path_d.append(f"{cmd} {px:.2f} {py:.2f}")
                    
                svg_paths.append(f'<path d="{" ".join(path_d)}" fill="none" stroke="black" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>')

    paths_str = "\n".join(svg_paths)
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">\n{paths_str}\n</svg>'

def run_daily_update():
    """Main execution block"""
    if not TRANSITLAND_API_KEY or not TRMNL_WEBHOOK_URL:
        print("Error: Missing Environment Variables. Check your GitHub Secrets.")
        return

    # Pick a random city for today's map
    city_name, bbox = random.choice(list(CITIES.items()))
    print(f"Generating transit map for {city_name}...")
    
    # Fetch data and generate SVG
    geojson = get_transit_data(bbox)
    svg_str = geojson_to_svg(geojson)
    
    # Prepare payload for TRMNL
    payload = {
        "merge_variables": {
            "city_name": city_name,
            "map_svg": svg_str
        }
    }
    
    headers = {"Content-Type": "application/json"}
    
    # Send to TRMNL Webhook
    resp = requests.post(TRMNL_WEBHOOK_URL, json=payload, headers=headers)
    print(f"TRMNL Updated: Status {resp.status_code}")
    
    if resp.status_code != 200:
        print(f"Response: {resp.text}")

if __name__ == "__main__":
    run_daily_update()
