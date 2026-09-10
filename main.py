import os
import json
import random
import requests

TRANSITLAND_API_KEY = os.environ.get("TRANSITLAND_API_KEY")
TRMNL_WEBHOOK_URL = os.environ.get("TRMNL_WEBHOOK_URL")

# Bounding boxes, center points [lon, lat], and ideal zoom level
CITIES = {
    "Amsterdam": {"bbox": [4.72, 52.27, 5.05, 52.44], "center": [4.89, 52.36], "zoom": 11},
    "Lyon": {"bbox": [4.74, 45.69, 4.96, 45.83], "center": [4.85, 45.76], "zoom": 11.5},
    "Athens": {"bbox": [23.59, 37.88, 23.90, 38.09], "center": [23.72, 37.98], "zoom": 11}
}

def get_transit_data(bbox):
    url = "https://transit.land/api/v2/rest/routes"
    params = {
        "bbox": ",".join(map(str, bbox)),
        "route_types": "1,2",
        "include_geometry": "true",
        "format": "geojson",
        "limit": 100,
        "apikey": TRANSITLAND_API_KEY
    }
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    return resp.json()

def optimize_geojson(geojson_data):
    # Massively compress the JSON payload to fit TRMNL's 5KB limit
    # Strips out heavy metadata and rounds coordinates
    features = []
    for feature in geojson_data.get('features', []):
        geom = feature.get('geometry')
        if not geom: continue
        
        coords = geom['coordinates']
        lines = coords if geom['type'] == 'MultiLineString' else [coords]
        
        opt_lines = []
        for line in lines:
            sublines = line if isinstance(line[0][0], list) else [line]
            for subline in sublines:
                opt_sub = []
                last_pt = None
                for i, pt in enumerate(subline):
                    # Round coordinates to 3 decimals (~111 meter precision)
                    rx, ry = round(pt[0], 3), round(pt[1], 3)
                    
                    # Decimate nodes that are too close together
                    if last_pt and abs(rx - last_pt[0]) < 0.003 and abs(ry - last_pt[1]) < 0.003 and i != len(subline)-1:
                        continue
                        
                    opt_sub.append([rx, ry])
                    last_pt = (rx, ry)
                
                if len(opt_sub) > 1:
                    opt_lines.append(opt_sub)
                
        if opt_lines:
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "MultiLineString",
                    "coordinates": opt_lines
                },
                "properties": {} # Strip names and colors
            })
            
    return {"type": "FeatureCollection", "features": features}

def run_daily_update():
    city_name, city_data = random.choice(list(CITIES.items()))
    print(f"Fetching transit data for {city_name}...")
    
    raw_geojson = get_transit_data(city_data["bbox"])
    optimized_geojson = optimize_geojson(raw_geojson)
    
    payload = {
        "merge_variables": {
            "city_name": city_name,
            "lon": city_data["center"][0],
            "lat": city_data["center"][1],
            "zoom": city_data["zoom"],
            "map_geojson": json.dumps(optimized_geojson)
        }
    }
    
    headers = {"Content-Type": "application/json"}
    resp = requests.post(TRMNL_WEBHOOK_URL, json=payload, headers=headers)
    print(f"TRMNL Updated: Status {resp.status_code}")
    
    if resp.status_code != 200:
        print("Error response:", resp.text)

if __name__ == "__main__":
    run_daily_update()
