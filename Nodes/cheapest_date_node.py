# Nodes/cheapest_date_node.py
import os
import json
import re
import requests
from typing import Dict, Any, List
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from Utils.getLLM import get_text_llm, get_llm_json
from Models.TravelSearchState import TravelSearchState
from datetime import datetime, timedelta

# Load environment variables
load_dotenv()


def normalize_location_to_airport_code(location: str) -> str:
    """Convert location name to IATA airport code using OpenAI LLM"""
    if not location:
        return ""
    if len(location.strip()) == 3 and location.isalpha():
        return location.upper()
    try:
        llm = get_text_llm()
        airport_prompt = f"""
        Convert this location to a 3-letter IATA airport code: {location}

        Common mappings:
        - New York/NYC -> JFK
        - Los Angeles/LA -> LAX
        - London -> LHR
        - Paris -> CDG
        - Chicago -> ORD

        Return only the 3-letter airport code, nothing else.
        """
        response = llm.invoke(airport_prompt).content
        airport_code = response.strip().upper()
        codes = re.findall(r'\b[A-Z]{3}\b', airport_code)
        if codes:
            return codes[0]
        elif len(airport_code) == 3 and airport_code.isalpha():
            return airport_code
    except Exception as e:
        print(f"Error getting airport code for {location}: {e}")

    # Fallback mappings
    airport_mappings = {
        'new york': 'JFK', 'nyc': 'JFK', 'los angeles': 'LAX', 'la': 'LAX',
        'chicago': 'ORD', 'london': 'LHR', 'paris': 'CDG', 'tokyo': 'NRT',
        'dubai': 'DXB', 'amsterdam': 'AMS', 'frankfurt': 'FRA', 'madrid': 'MAD',
        'rome': 'FCO', 'barcelona': 'BCN', 'milan': 'MXP', 'zurich': 'ZRH',
    }
    if location.lower().strip() in airport_mappings:
        return airport_mappings[location.lower().strip()]

    return location[:3].upper()


def parse_date_range(date_input: str) -> str:
    """Parse various date range formats to API format (YYYY-MM-DD,YYYY-MM-DD)"""
    try:
        llm = get_text_llm()
        today = datetime.now().strftime("%Y-%m-%d")

        date_prompt = f"""
        Convert this date or date range to the format YYYY-MM-DD,YYYY-MM-DD for an API call.
        Today's date is: {today}

        User input: "{date_input}"

        Examples of what to convert:
        - "from September 20th to September 25th 2025" -> 2025-09-20,2025-09-25
        - "next week" -> specific 7-day range starting from next Monday
        - "December 2024" -> 2024-12-01,2024-12-31
        - "Christmas week" -> 2024-12-22,2024-12-29
        - "January 15 to January 25" -> 2025-01-15,2025-01-25
        - "next month" -> full next month range
        - "winter 2024" -> 2024-12-21,2025-03-20

        Return only the date range in YYYY-MM-DD,YYYY-MM-DD format, nothing else.
        If it's a single date, make it a 7-day range around that date.
        """

        response = llm.invoke(date_prompt).content.strip()

        # Validate the response format
        if re.match(r'^\d{4}-\d{2}-\d{2},\d{4}-\d{2}-\d{2}$', response):
            return response
        else:
            # Fallback: create a 30-day range from today
            start_date = datetime.now()
            end_date = start_date + timedelta(days=30)
            return f"{start_date.strftime('%Y-%m-%d')},{end_date.strftime('%Y-%m-%d')}"

    except Exception as e:
        print(f"Error parsing date range: {e}")
        # Fallback: create a 30-day range from today
        start_date = datetime.now()
        end_date = start_date + timedelta(days=30)
        return f"{start_date.strftime('%Y-%m-%d')},{end_date.strftime('%Y-%m-%d')}"


def cheapest_date_llm_node(state: TravelSearchState) -> TravelSearchState:
    """LLM node to extract and normalize cheapest date search information"""
    try:
        user_message = state.get("current_message", "")

        extraction_prompt = f"""
        Extract flight cheapest date search information from this user message: "{user_message}"

        Return a JSON object with these fields:
        - origin
        - destination
        - departure_date_range
        - non_stop_preference
        - needs_followup
        - followup_question
        - ready_to_search
        """

        llm = get_llm_json()
        response = llm.invoke(extraction_prompt).content
        print(f"DEBUG: LLM extraction response: {response}")

        # Clean the response
        response_clean = response.strip().replace("```json", "").replace("```", "").strip()

        result = json.loads(response_clean)
        print(f"DEBUG: Parsed extraction result: {result}")

        # Update state with extracted info
        new_state = state.copy()
        if result.get("origin"):
            new_state["cheapest_date_origin"] = result["origin"]
            new_state["origin_location_code"] = normalize_location_to_airport_code(result["origin"])

        if result.get("destination"):
            new_state["cheapest_date_destination"] = result["destination"]
            new_state["destination_location_code"] = normalize_location_to_airport_code(result["destination"])

        if result.get("departure_date_range"):
            new_state["cheapest_date_departure_range"] = result["departure_date_range"]
            new_state["cheapest_date_normalized_range"] = parse_date_range(result["departure_date_range"])

        if "cheapest_date_normalized_range" not in new_state:
            start_date = datetime.now()
            end_date = start_date + timedelta(days=30)
            new_state["cheapest_date_normalized_range"] = f"{start_date.strftime('%Y-%m-%d')},{end_date.strftime('%Y-%m-%d')}"

        # Handle non_stop_preference
        non_stop_pref = result.get("non_stop_preference")
        if non_stop_pref is not None:
            new_state["cheapest_date_non_stop"] = bool(non_stop_pref)

        new_state["needs_followup"] = result.get("needs_followup", True)
        new_state["followup_question"] = result.get("followup_question")
        new_state["ready_to_search"] = result.get("ready_to_search", False)

        print(f"DEBUG: Updated state -> Origin: {new_state.get('origin_location_code')} | Destination: {new_state.get('destination_location_code')}")
        print(f"DEBUG: Date range: {new_state.get('cheapest_date_normalized_range')} | Non-stop: {new_state.get('cheapest_date_non_stop')}")

        return new_state
    except Exception as e:
        print(f"Error in cheapest date LLM node: {e}")
        new_state = state.copy()
        new_state["needs_followup"] = True
        new_state["followup_question"] = "I need your departure city, destination, travel date range, and whether you prefer direct flights or are okay with layovers."
        new_state["ready_to_search"] = False
        return new_state


def cheapest_date_search_node(state: TravelSearchState) -> TravelSearchState:
    """Search cheapest dates using Amadeus Flight Cheapest Date Search API"""
    print("DEBUG: Entering cheapest_date_search_node")
    new_state = state.copy()
    try:
        origin = new_state.get("origin_location_code")
        destination = new_state.get("destination_location_code")
        departure_date_range = new_state.get("cheapest_date_normalized_range")
        non_stop = new_state.get("cheapest_date_non_stop", False)
        access_token = new_state.get("access_token")

        # Validate
        if not all([origin, destination, departure_date_range, access_token]):
            raise ValueError("Missing required params for API call")

        print(f"Searching cheapest dates: {origin} -> {destination} | Dates: {departure_date_range} | Non-stop: {non_stop}")

        base_url = "https://test.api.amadeus.com/v1/shopping/flight-dates"
        headers = {"Authorization": f"Bearer {access_token}"}

        params = {
            "origin": origin,
            "destination": destination,
            "departureDate": departure_date_range,
            "oneWay": False,
            "nonStop": non_stop
        }

        # Debug full URL
        prepared = requests.Request("GET", base_url, params=params).prepare()
        print(f"DEBUG FULL URL: {prepared.url}")

        response = requests.get(base_url, headers=headers, params=params, timeout=30)
        print("DEBUG STATUS:", response.status_code)
        print("DEBUG RAW RESPONSE:", response.text[:500])

        response.raise_for_status()
        data = response.json()

        cheapest_dates = [
            {
                "departure_date": offer.get("departureDate"),
                "return_date": offer.get("returnDate"),
                "price": offer.get("price", {}),
                "origin": origin,
                "destination": destination
            }
            for offer in data.get("data", [])
        ]

        new_state["cheapest_date_results"] = cheapest_dates
        new_state["cheapest_date_error"] = None
        print(f"DEBUG: Found {len(cheapest_dates)} cheapest date options")

    except requests.exceptions.RequestException as e:
        error_message = f"Amadeus API error: {e}"
        print(error_message)
        new_state["cheapest_date_results"] = []
        try:
            new_state["cheapest_date_error"] = e.response.json()
        except:
            new_state["cheapest_date_error"] = str(e)

    except Exception as e:
        print(f"Unexpected error in cheapest_date_search_node: {e}")
        new_state["cheapest_date_results"] = []
        new_state["cheapest_date_error"] = str(e)

    print("DEBUG: Exiting cheapest_date_search_node")
    return new_state


def format_cheapest_dates_to_html(state: TravelSearchState) -> TravelSearchState:
    """Convert cheapest date options to HTML table for frontend display"""
    new_state = state.copy()
    cheapest_dates = new_state.get("cheapest_date_results", [])
    search_error = new_state.get("cheapest_date_error")

    # If there's an error, return as plain text inside a simple table
    if search_error:
        html_content = f"""
        <table border="1" cellpadding="5" cellspacing="0">
            <tr><th>Error</th></tr>
            <tr><td>{search_error}</td></tr>
        </table>
        """
        new_state["cheapest_date_html"] = html_content
        return new_state

    # If no cheapest dates found
    if not cheapest_dates:
        html_content = """
        <table border="1" cellpadding="5" cellspacing="0">
            <tr><th>Info</th></tr>
            <tr><td>No cheapest dates found for the given criteria.</td></tr>
        </table>
        """
        new_state["cheapest_date_html"] = html_content
        return new_state

    # Build a clean HTML table
    html_parts = ["""
    <table border="1" cellpadding="5" cellspacing="0">
        <thead>
            <tr>
                <th>Departure Date</th>
                <th>Return Date</th>
                <th>Route</th>
                <th>Price</th>
                <th>Flight Type</th>
            </tr>
        </thead>
        <tbody>
    """]

    for date_option in cheapest_dates:
        departure_date = date_option.get("departure_date", "N/A")
        return_date = date_option.get("return_date", "N/A")
        price_info = date_option.get("price", {})
        price = price_info.get("total", "N/A")
        currency = price_info.get("currency", "EUR")

        route = f"{date_option.get('origin', 'N/A')} → {date_option.get('destination', 'N/A')}"
        flight_type = "Direct" if new_state.get("cheapest_date_non_stop") else "With stops allowed"
        html_parts.append(f"""
            <tr>
                <td>{departure_date}</td>
                <td>{return_date}</td>
                <td>{route}</td>
                <td>{currency} {price}</td>
                <td>{flight_type}</td>
            </tr>
        """)

    html_parts.append("""
        </tbody>
    </table>
    """)
    new_state["cheapest_date_html"] = "".join(html_parts)
    return new_state

def create_cheapest_date_graph():
    """Create a graph for cheapest date searches"""
    print("DEBUG: Creating cheapest date search graph")

    graph = StateGraph(TravelSearchState)

    # Define format_followup_html before adding nodes
    def format_followup_html(state: TravelSearchState) -> TravelSearchState:
        """Format followup question as HTML"""
        print("DEBUG: format_followup_html called")
        print(f"DEBUG: State keys in followup: {list(state.keys())}")
        new_state = state.copy()
        followup = new_state.get("followup_question", "Please provide your departure city, destination, travel date range, and stop preference.")

        html_content = f"""
        <div class="p-6 bg-blue-50 border border-blue-200 rounded-lg">
            <h3 class="text-lg font-semibold text-blue-800 mb-2">Need More Information</h3>
            <p class="text-blue-600">{followup}</p>
        </div>
        """
        new_state["cheapest_date_html"] = html_content
        print("DEBUG: Set followup HTML, length:", len(html_content))
        print(f"DEBUG: State after setting HTML: {list(new_state.keys())}")
        return new_state

    # Add nodes
    graph.add_node("cheapest_date_llm", cheapest_date_llm_node)
    graph.add_node("cheapest_date_search", cheapest_date_search_node)
    graph.add_node("format_html", format_cheapest_dates_to_html)
    graph.add_node("format_followup", format_followup_html)

    # Set entry point
    graph.set_entry_point("cheapest_date_llm")

    # Add conditional routing
    def should_search_cheapest_dates(state: TravelSearchState) -> str:
        """Route based on whether we have enough info to search"""
        ready = state.get("ready_to_search", False)
        needs_followup = state.get("needs_followup", True)
        # Manual check as backup
        has_origin = bool(state.get("origin_location_code"))
        has_destination = bool(state.get("destination_location_code"))
        has_date_range = bool(state.get("cheapest_date_normalized_range"))
        has_non_stop_pref = state.get("cheapest_date_non_stop") is not None

        print(f"DEBUG: Routing - ready_to_search: {ready}, needs_followup: {needs_followup}")
        print(f"DEBUG: Manual check - origin: {has_origin}, destination: {has_destination}, date_range: {has_date_range}, non_stop: {has_non_stop_pref}")
        print(f"DEBUG: State keys: {list(state.keys())}")
        print(f"DEBUG: State values - normalized_departure_date_range: {state.get('cheapest_date_normalized_range')}, non_stop: {state.get('cheapest_date_non_stop')}")

        if (ready and not needs_followup) or (has_origin and has_destination and has_date_range and has_non_stop_pref):
            print("DEBUG: Routing to cheapest_date_search")
            return "cheapest_date_search"
        else:
            print("DEBUG: Routing to format_followup")
            return "format_followup"

    # Add edges
    print("DEBUG: Adding graph edges")
    graph.add_conditional_edges(
        "cheapest_date_llm",
        should_search_cheapest_dates,
        {
            "cheapest_date_search": "cheapest_date_search",
            "format_followup": "format_followup"
        }
    )
    graph.add_edge("cheapest_date_search", "format_html")
    graph.add_edge("format_html", END)
    graph.add_edge("format_followup", END)
    print("DEBUG: Cheapest date search graph created successfully")
    return graph
