import requests
import random
import json

def fetch_trmnl_subway_data():
    # Define a pool of cities with their default center coordinates [Longitude, Latitude]
    cities = [
        {"name": "Tokyo", "lon": 139.6917, "lat": 35.6895},
        {"name": "London", "lon": -0.1278, "lat": 51.5074},
        {"name": "Paris", "lon": 2.3522, "lat": 48.8566},
        {"name": "Seoul", "lon": 126.9780, "lat": 37.5665}
    ]
    
    city = random.choice(cities)
    
    # Overpass QL query to find subway stations in the chosen city
    overpass_url = "http://overpass-api.de/api/interpreter"
    overpass_query = f"""
    [out:json];
    area[name="{city['name']}"]->.searchArea;
    node["railway"="station"]["station"="subway"](area.searchArea);
    out center 30; // Limit to 30 stations for clean display
    """
    
    response = requests.post(overpass_url, data={'data': overpass_query})
    elements = response.json().get('elements', [])
    
    # Format the data for the TRMNL frontend
    stations = []
    for el in elements:
        stations.append({
            "name": el.get('tags', {}).get('name', 'Unknown'),
            "lon": el['lon'],
            "lat": el['lat']
        })
        
    # Construct the TRMNL plugin payload
    trmnl_payload = {
        "merge_variables": {
            "city_name": city['name'],
            "map_center": [city['lon'], city['lat']],
            "stations": stations
        }
    }
    
    return json.dumps(trmnl_payload)

# When sent to TRMNL, the payload will inject these variables into your Liquid template
print(fetch_trmnl_subway_data())
