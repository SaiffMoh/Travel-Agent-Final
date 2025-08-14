import os
from Models.TravelSearchState import TravelSearchState
import requests
from dotenv import load_dotenv
load_dotenv()
def get_access_token_node(state: TravelSearchState) -> TravelSearchState:
    """Get access token from Amadeus API"""

    url = "https://test.api.amadeus.com/v1/security/oauth2/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "client_credentials",
        "client_id": os.getenv("AMADEUS_CLIENT_ID"),
        "client_secret": os.getenv("AMADEUS_CLIENT_SECRET")
    }
    response = requests.post(url, headers=headers, data=data, timeout=100)
    response.raise_for_status()
    token_json = response.json()
    state["access_token"] = token_json.get("access_token")
    if state.get("access_token"):
        print("get_access_token_node: acquired access token")
    return state