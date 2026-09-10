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

def get_transit_data(bbox):
    url = "https://transit.land/api/v2/rest/routes"
    params = {
        "bbox": ",".join(map(str, bbox)),
        "route_types": "1,2",
        "include_geometry": "true",
        "format": "geojson",
        "limit": 25,  # Dropped from 100 to 25 to guarantee we stay under 5KB
        "apikey": TRANSITLAND_API_KEY
    }
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    return resp.json()

def optimize_to_string(geojson_data):
    # Converts GeoJSON into a custom compressed string: lon,lat|lon,lat;lon,lat|lon,lat
    lines_str = []
    for feature in geojson_data.get('features', []):
        geom = feature.get('geometry')
        if not geom: continue
        
        coords = geom['coordinates']
        lines = coords if geom['type'] == 'MultiLineString' else [coords]
        
        for line in lines:
            sublines = line if isinstance(line[0][0], list) else [line]
            for subline in sublines:
                opt_sub = []
                last_pt = None
                for i, pt in enumerate(subline):
                    rx, ry = round(pt[0], 3), round(pt[1], 3)
                    
                    # Decimate nodes closer than ~500m to save massive amounts of space
                    if last_pt and abs(rx - last_pt[0]) < 0.005 and abs(ry - last_pt[1]) < 0.005 and i != len(subline)-1:
                        continue
                        
                    opt_sub.append(f"{rx},{ry}")
                    last_pt = (rx, ry)
                
                if len(opt_sub) > 1:
                    lines_str.append("|".join(opt_sub))
                    
    return ";".join(lines_str)

def run_daily_update():
    city_name, city_data = random.choice(list(CITIES.items()))
    print(f"Fetching transit data for {city_name}...")
    
    raw_geojson = get_transit_data(city_data["bbox"])
    compressed_string = optimize_to_string(raw_geojson)
    
    payload = {
        "merge_variables": {
            "city_name": city_name,
            "lon": city_data["center"][0],
            "lat": city_data["center"][1],
            "zoom": city_data["zoom"],
            "map_data": compressed_string # Sending the raw string instead of JSON
        }
    }
    
    headers = {"Content-Type": "application/json"}
    resp = requests.post(TRMNL_WEBHOOK_URL, json=payload, headers=headers)
    print(f"TRMNL Updated: Status {resp.status_code}")
    
    if resp.status_code != 200:
        print("Error response:", resp.text)

if __name__ == "__main__":
    run_daily_update()
