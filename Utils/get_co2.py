import requests
import json

def get_co2_emissions(flight_data, access_token):
    """Calculate CO2 emissions for a given flight data."""
    
    url = "https://test.api.amadeus.com/v1/shopping/flight-offers/pricing"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # day_number, search_date, body = flight_data

    # print("================ body in get_co2", body)

    response = requests.post(url, headers=headers, json=flight_data)

    with open("co2.txt", "w") as f:
        f.write(str(response.content))

    print(response.content)
    
    return response