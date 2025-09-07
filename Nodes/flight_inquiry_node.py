import os
import json
import re
from typing import Dict, Any, List
from amadeus import Client, ResponseError
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from Utils.getLLM import get_text_llm, get_llm_json
from Models.TravelSearchState import TravelSearchState

# Load environment variables
load_dotenv()

def normalize_location_to_airport_code(location: str) -> str:
    """Convert location name to IATA airport code using OpenAI LLM"""
    if not location:
        return ""
    if len(location.strip()) == 3 and location.isalpha():
        return location.upper()

    try:
        llm = get_text_llm()  # Use text-mode LLM for simple text response
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

def flight_inquiry_llm_node(state: TravelSearchState) -> TravelSearchState:
    """LLM node to extract and normalize flight inquiry information"""
    try:
        user_message = state.get("current_message", "")
        
        extraction_prompt = f"""
        Extract flight search information from this user message: "{user_message}"
        
        Return a JSON object with these fields:
        - origin: departure city/airport (extract from message)
        - destination: arrival city/airport (extract from message) 
        - departure_date: travel date in YYYY-MM-DD format
        - needs_followup: true if any required info is missing
        - followup_question: what to ask if info is missing
        - ready_to_search: true if we have origin, destination, and date
        
        Example response:
        {{
            "origin": "New York",
            "destination": "Los Angeles", 
            "departure_date": "2025-09-15",
            "needs_followup": false,
            "followup_question": null,
            "ready_to_search": true
        }}
        
        If information is missing, set needs_followup to true and provide a helpful followup_question.
        Return only valid JSON, nothing else.
        """
        
        llm = get_llm_json()  # Use JSON-mode LLM for structured output
        response = llm.invoke(extraction_prompt).content
        print(f"DEBUG: LLM extraction response: {response}")
        
        # Clean the response to extract JSON
        response_clean = response.strip()
        if response_clean.startswith('```json'):
            response_clean = response_clean.replace('```json', '').replace('```', '').strip()
        elif response_clean.startswith('```'):
            response_clean = response_clean.replace('```', '').strip()
            
        result = json.loads(response_clean)
        print(f"DEBUG: Parsed extraction result: {result}")
        
        # Update state with extracted info
        new_state = state.copy()  # Create a copy to ensure immutability
        if result.get("origin"):
            new_state["origin"] = result["origin"]
            new_state["origin_location_code"] = normalize_location_to_airport_code(result["origin"])
        
        if result.get("destination"):
            new_state["destination"] = result["destination"]  
            new_state["destination_location_code"] = normalize_location_to_airport_code(result["destination"])
            
        if result.get("departure_date"):
            new_state["departure_date"] = result["departure_date"]
            new_state["normalized_departure_date"] = result["departure_date"]
            
        new_state["needs_followup"] = result.get("needs_followup", True)
        new_state["followup_question"] = result.get("followup_question")
        new_state["ready_to_search"] = result.get("ready_to_search", False)
        
        print(f"DEBUG: Updated state - origin: {new_state.get('origin')}, destination: {new_state.get('destination')}, date: {new_state.get('departure_date')}")
        print(f"DEBUG: Airport codes - from: {new_state.get('origin_location_code')}, to: {new_state.get('destination_location_code')}")
        
        return new_state
    except Exception as e:
        print(f"Error in flight inquiry LLM node: {e}")
        new_state = state.copy()
        new_state["needs_followup"] = True
        new_state["followup_question"] = "I need your departure city, destination, and travel date to search for flights."
        new_state["ready_to_search"] = False
        return new_state

def flight_search_node(state: TravelSearchState) -> TravelSearchState:
    """Search flights using Amadeus API"""
    print("DEBUG: Entering flight_search_node")
    new_state = state.copy()  # Create a copy to ensure immutability
    try:
        client = Client(
            client_id=os.getenv("AMADEUS_CLIENT_ID"),
            client_secret=os.getenv("AMADEUS_CLIENT_SECRET")
        )

        origin = new_state.get("origin_location_code")
        destination = new_state.get("destination_location_code")
        departure_date = new_state.get("normalized_departure_date")

        # Validate input parameters
        if not all([origin, destination, departure_date]):
            raise ValueError(f"Missing required parameters: origin={origin}, destination={destination}, departure_date={departure_date}")

        # Validate date format (YYYY-MM-DD)
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", departure_date):
            raise ValueError(f"Invalid departure_date format: {departure_date}")

        print(f"Searching flights: {origin} -> {destination} on {departure_date}")
        print(f"DEBUG: API credentials exist - Client ID: {bool(os.getenv('AMADEUS_CLIENT_ID'))}, Secret: {bool(os.getenv('AMADEUS_CLIENT_SECRET'))}")

        response = client.shopping.flight_offers_search.get(
            originLocationCode=origin,
            destinationLocationCode=destination,
            departureDate=departure_date,
            adults=1,
            max=10
        )

        flight_options = []
        for offer in response.data[:10]:
            itinerary = offer["itineraries"][0]
            segments = itinerary["segments"]

            # Calculate total duration
            total_duration = itinerary.get("duration", "N/A")
            
            flight_options.append({
                "airline": segments[0].get("carrierCode", "N/A"),
                "flight_number": segments[0].get("number", "N/A"),
                "from": segments[0]["departure"]["iataCode"],
                "to": segments[-1]["arrival"]["iataCode"],
                "departure_time": segments[0]["departure"]["at"],
                "arrival_time": segments[-1]["arrival"]["at"],
                "duration": total_duration,
                "stops": len(segments) - 1,
                "price": offer["price"]["total"],
                "currency": offer["price"]["currency"],
                "booking_class": segments[0].get("cabin", "ECONOMY")
            })

        new_state["flight_options"] = flight_options
        new_state["search_error"] = None
        print(f"DEBUG: Found {len(flight_options)} flights, setting in state")
        if flight_options:
            print(f"DEBUG: Sample flight option: {flight_options[0]}")
        
    except ResponseError as e:
        error_message = f"Amadeus API error: {e}"
        print(error_message)
        print(f"DEBUG: Full error details: {e.response.result if hasattr(e, 'response') else 'No details'}")
        new_state["flight_options"] = []
        new_state["search_error"] = error_message
        
    except ValueError as e:
        error_message = f"Invalid input parameters: {str(e)}"
        print(error_message)
        new_state["flight_options"] = []
        new_state["search_error"] = error_message
        
    except Exception as e:
        error_message = f"Unexpected error in flight search: {str(e)}"
        print(error_message)
        new_state["flight_options"] = []
        new_state["search_error"] = error_message
        
    print("DEBUG: Exiting flight_search_node")
    return new_state

def format_flights_to_html(state: TravelSearchState) -> TravelSearchState:
    """Convert flight options to a simple HTML table for frontend display"""
    new_state = state.copy()
    flight_options = new_state.get("flight_options", [])
    search_error = new_state.get("search_error")

    # If there's an error, return as plain text inside a simple table
    if search_error:
        html_content = f"""
        <table border="1" cellpadding="5" cellspacing="0">
            <tr><th>Error</th></tr>
            <tr><td>{search_error}</td></tr>
        </table>
        """
        new_state["flight_inquiry_html"] = html_content
        return new_state

    # If no flights found
    if not flight_options:
        html_content = """
        <table border="1" cellpadding="5" cellspacing="0">
            <tr><th>Info</th></tr>
            <tr><td>No flights found for the given criteria.</td></tr>
        </table>
        """
        new_state["flight_inquiry_html"] = html_content
        return new_state

    # Build a clean HTML table
    html_parts = ["""
    <table border="1" cellpadding="5" cellspacing="0">
        <thead>
            <tr>
                <th>Flight</th>
                <th>From</th>
                <th>To</th>
                <th>Departure</th>
                <th>Arrival</th>
                <th>Duration</th>
                <th>Stops</th>
                <th>Price</th>
            </tr>
        </thead>
        <tbody>
    """]

    for flight in flight_options:
        dep_time = flight.get("departure_time", "").replace("T", " ").replace("Z", "")[:16]
        arr_time = flight.get("arrival_time", "").replace("T", " ").replace("Z", "")[:16]
        duration = flight.get("duration", "N/A")

        # Clean up ISO duration format
        if duration.startswith("PT"):
            duration = duration.replace("PT", "").replace("H", "h ").replace("M", "m")

        html_parts.append(f"""
            <tr>
                <td>{flight.get('airline', 'N/A')} {flight.get('flight_number', 'N/A')}</td>
                <td>{flight.get('from', 'N/A')}</td>
                <td>{flight.get('to', 'N/A')}</td>
                <td>{dep_time}</td>
                <td>{arr_time}</td>
                <td>{duration}</td>
                <td>{flight.get('stops', 0)}</td>
                <td>{flight.get('currency', 'USD')} {flight.get('price', 'N/A')}</td>
            </tr>
        """)

    html_parts.append("""
        </tbody>
    </table>
    """)

    new_state["flight_inquiry_html"] = "".join(html_parts)
    return new_state


def create_flight_inquiry_graph():
    """Create a separate graph for flight inquiries"""
    print("DEBUG: Creating flight inquiry graph")
    
    graph = StateGraph(TravelSearchState)
    
    # Define format_followup_html before adding nodes
    def format_followup_html(state: TravelSearchState) -> TravelSearchState:
        """Format followup question as HTML"""
        print("DEBUG: format_followup_html called")
        print(f"DEBUG: State keys in followup: {list(state.keys())}")
        new_state = state.copy()  # Create a copy to ensure immutability
        followup = new_state.get("followup_question", "Please provide your departure city, destination, and travel date.")
        
        html_content = f"""
        <div class="p-6 bg-blue-50 border border-blue-200 rounded-lg">
            <h3 class="text-lg font-semibold text-blue-800 mb-2">Need More Information</h3>
            <p class="text-blue-600">{followup}</p>
        </div>
        """
        new_state["flight_inquiry_html"] = html_content
        print("DEBUG: Set followup HTML, length:", len(html_content))
        print(f"DEBUG: State after setting HTML: {list(new_state.keys())}")
        return new_state
    
    # Add nodes
    graph.add_node("flight_inquiry_llm", flight_inquiry_llm_node)
    graph.add_node("flight_search", flight_search_node)  
    graph.add_node("format_html", format_flights_to_html)
    graph.add_node("format_followup", format_followup_html)
    
    # Set entry point
    graph.set_entry_point("flight_inquiry_llm")
    
    # Add conditional routing
    def should_search_flights(state: TravelSearchState) -> str:
        """Route based on whether we have enough info to search"""
        ready = state.get("ready_to_search", False)
        needs_followup = state.get("needs_followup", True)
        
        # Check if we have the essential info manually as backup
        has_origin = bool(state.get("origin_location_code"))
        has_destination = bool(state.get("destination_location_code"))  
        has_date = bool(state.get("normalized_departure_date"))
        
        print(f"DEBUG: Routing - ready_to_search: {ready}, needs_followup: {needs_followup}")
        print(f"DEBUG: Manual check - origin: {has_origin}, destination: {has_destination}, date: {has_date}")
        
        # Use manual check as backup if LLM flags are inconsistent
        if (ready and not needs_followup) or (has_origin and has_destination and has_date):
            print("DEBUG: Routing to flight_search")
            return "flight_search"
        else:
            print("DEBUG: Routing to format_followup")
            return "format_followup"
    
    # Add edges
    print("DEBUG: Adding graph edges")
    graph.add_conditional_edges(
        "flight_inquiry_llm",
        should_search_flights,
        {
            "flight_search": "flight_search",
            "format_followup": "format_followup"
        }
    )
    
    graph.add_edge("flight_search", "format_html")
    graph.add_edge("format_html", END)
    graph.add_edge("format_followup", END)
    
    print("DEBUG: Flight inquiry graph created successfully")
    return graph