import os
import json
import re
from typing import Dict, Any, List
from amadeus import Client, ResponseError
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langchain.schema import HumanMessage
from Utils.getLLM import get_text_llm, get_llm_json
from Models.TravelSearchState import TravelSearchState

# Load environment variables
load_dotenv()

def normalize_location_to_airport_code(location: str) -> str:
    """Convert location name to IATA airport code using LLM"""
    if not location:
        return ""
    if len(location.strip()) == 3 and location.isalpha():
        return location.upper()

    try:
        if os.getenv("OPENAI_API_KEY"):
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
            response = get_text_llm().invoke([HumanMessage(content=airport_prompt)])
            airport_code = response.content.strip().upper()
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
        """
        
        response = get_llm_json().invoke([HumanMessage(content=extraction_prompt)])
        result = json.loads(response.content)
        
        # Update state with extracted info
        if result.get("origin"):
            state["origin"] = result["origin"]
            state["origin_location_code"] = normalize_location_to_airport_code(result["origin"])
        
        if result.get("destination"):
            state["destination"] = result["destination"]  
            state["destination_location_code"] = normalize_location_to_airport_code(result["destination"])
            
        if result.get("departure_date"):
            state["departure_date"] = result["departure_date"]
            state["normalized_departure_date"] = result["departure_date"]
            
        state["needs_followup"] = result.get("needs_followup", True)
        state["followup_question"] = result.get("followup_question")
        state["ready_to_search"] = result.get("ready_to_search", False)
        
    except Exception as e:
        print(f"Error in flight inquiry LLM node: {e}")
        state["needs_followup"] = True
        state["followup_question"] = "I need your departure city, destination, and travel date to search for flights."
        state["ready_to_search"] = False
        
    return state

def flight_search_node(state: TravelSearchState) -> TravelSearchState:
    """Search flights using Amadeus API"""
    try:
        client = Client(
            client_id=os.getenv("AMADEUS_CLIENT_ID"),
            client_secret=os.getenv("AMADEUS_CLIENT_SECRET")
        )

        origin = state.get("origin_location_code")
        destination = state.get("destination_location_code")
        departure_date = state.get("normalized_departure_date")

        print(f"Searching flights: {origin} -> {destination} on {departure_date}")

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

        state["flight_options"] = flight_options
        state["search_error"] = None
        
    except ResponseError as e:
        print(f"Amadeus API error: {e}")
        state["flight_options"] = []
        state["search_error"] = f"Flight search error: {str(e)}"
        
    except Exception as e:
        print(f"Unexpected error in flight search: {e}")
        state["flight_options"] = []
        state["search_error"] = f"Unexpected error: {str(e)}"
        
    return state

def format_flights_to_html(state: TravelSearchState) -> TravelSearchState:
    """Convert flight options to HTML format for frontend display"""
    flight_options = state.get("flight_options", [])
    search_error = state.get("search_error")
    
    if search_error:
        html_content = f"""
        <div class="p-6 bg-red-50 border border-red-200 rounded-lg">
            <h3 class="text-lg font-semibold text-red-800 mb-2">Search Error</h3>
            <p class="text-red-600">{search_error}</p>
        </div>
        """
        state["flight_inquiry_html"] = html_content
        return state
    
    if not flight_options:
        html_content = """
        <div class="p-6 bg-yellow-50 border border-yellow-200 rounded-lg">
            <h3 class="text-lg font-semibold text-yellow-800 mb-2">No Flights Found</h3>
            <p class="text-yellow-600">No flights found for your search criteria. Please try different dates or destinations.</p>
        </div>
        """
        state["flight_inquiry_html"] = html_content
        return state

    # Build HTML table for flight results
    html_parts = ["""
    <div class="bg-white rounded-lg shadow-lg overflow-hidden">
        <div class="bg-blue-600 text-white p-4">
            <h2 class="text-xl font-bold">Flight Search Results</h2>
            <p class="text-blue-100">Found """ + str(len(flight_options)) + """ flights from """ + 
            state.get("origin", "Unknown") + """ to """ + state.get("destination", "Unknown") + """</p>
        </div>
        <div class="overflow-x-auto">
            <table class="min-w-full divide-y divide-gray-200">
                <thead class="bg-gray-50">
                    <tr>
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Flight</th>
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Route</th>
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Departure</th>
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Arrival</th>
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Duration</th>
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Stops</th>
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Price</th>
                    </tr>
                </thead>
                <tbody class="bg-white divide-y divide-gray-200">
    """]
    
    for i, flight in enumerate(flight_options):
        # Format times
        dep_time = flight.get("departure_time", "").replace("T", " ").replace("Z", "")[:16]
        arr_time = flight.get("arrival_time", "").replace("T", " ").replace("Z", "")[:16]
        
        # Format duration
        duration = flight.get("duration", "N/A")
        if duration != "N/A" and duration.startswith("PT"):
            # Parse ISO 8601 duration format
            duration = duration.replace("PT", "").replace("H", "h ").replace("M", "m")
        
        stops_text = "Direct" if flight.get("stops", 0) == 0 else f"{flight.get('stops')} stop(s)"
        
        row_class = "bg-gray-50" if i % 2 == 1 else "bg-white"
        
        html_parts.append(f"""
                    <tr class="{row_class}">
                        <td class="px-6 py-4 whitespace-nowrap">
                            <div class="text-sm font-medium text-gray-900">{flight.get('airline', 'N/A')} {flight.get('flight_number', 'N/A')}</div>
                            <div class="text-sm text-gray-500">{flight.get('booking_class', 'Economy')}</div>
                        </td>
                        <td class="px-6 py-4 whitespace-nowrap">
                            <div class="text-sm text-gray-900">{flight.get('from', 'N/A')} → {flight.get('to', 'N/A')}</div>
                        </td>
                        <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{dep_time}</td>
                        <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{arr_time}</td>
                        <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{duration}</td>
                        <td class="px-6 py-4 whitespace-nowrap">
                            <span class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full {'bg-green-100 text-green-800' if flight.get('stops', 0) == 0 else 'bg-yellow-100 text-yellow-800'}">{stops_text}</span>
                        </td>
                        <td class="px-6 py-4 whitespace-nowrap">
                            <div class="text-sm font-medium text-gray-900">{flight.get('currency', 'USD')} {flight.get('price', 'N/A')}</div>
                        </td>
                    </tr>
        """)
    
    html_parts.append("""
                </tbody>
            </table>
        </div>
    </div>
    """)
    
    state["flight_inquiry_html"] = "".join(html_parts)
    return state

def create_flight_inquiry_graph():
    """Create a separate graph for flight inquiries"""
    graph = StateGraph(TravelSearchState)
    
    # Add nodes
    graph.add_node("flight_inquiry_llm", flight_inquiry_llm_node)
    graph.add_node("flight_search", flight_search_node)  
    graph.add_node("format_html", format_flights_to_html)
    
    # Set entry point
    graph.set_entry_point("flight_inquiry_llm")
    
    # Add conditional routing
    def should_search_flights(state: TravelSearchState) -> str:
        """Route based on whether we have enough info to search"""
        if state.get("ready_to_search", False) and not state.get("needs_followup", True):
            return "search_flights"
        else:
            return "format_followup"
    
    def format_followup_html(state: TravelSearchState) -> TravelSearchState:
        """Format followup question as HTML"""
        followup = state.get("followup_question", "Please provide your departure city, destination, and travel date.")
        
        html_content = f"""
        <div class="p-6 bg-blue-50 border border-blue-200 rounded-lg">
            <h3 class="text-lg font-semibold text-blue-800 mb-2">Need More Information</h3>
            <p class="text-blue-600">{followup}</p>
        </div>
        """
        state["flight_inquiry_html"] = html_content
        return state
    
    graph.add_node("format_followup", format_followup_html)
    
    # Add edges
    graph.add_conditional_edges(
        "flight_inquiry_llm",
        should_search_flights,
        {
            "search_flights": "flight_search",
            "format_followup": "format_followup"
        }
    )
    
    graph.add_edge("flight_search", "format_html")
    graph.add_edge("format_html", END)
    graph.add_edge("format_followup", END)
    
    return graph