import os
import re
from Models.TravelSearchState import TravelSearchState
from langchain.schema import HumanMessage
from Utils.getLLM import get_text_llm
from Prompts.cabin_prompt import get_cabin_type_prompt
from Prompts.airport_prompt import airport_prompt


def normalize_info_node(state: TravelSearchState) -> TravelSearchState:
    """Normalize extracted information for Amadeus API format using LLM for intelligent mapping."""

    def normalize_location_to_airport_code(location: str) -> str:
        if not location:
            return ""
        if len(location.strip()) == 3 and location.isalpha():
            return location.upper()

        try:
            if os.getenv("OPENAI_API_KEY"):
                response = get_text_llm().invoke([HumanMessage(content=airport_prompt(location))])
                airport_code = response.content.strip().upper()
                codes = re.findall(r'\b[A-Z]{3}\b', airport_code)
                if codes:
                    return codes[0]
                elif len(airport_code) == 3 and airport_code.isalpha():
                    return airport_code
        except Exception as e:
            print(f"Error getting airport code for {location}: {e}")

        airport_mappings = {
            'new york': 'JFK', 'nyc': 'JFK', 'los angeles': 'LAX', 'la': 'LAX',
            'chicago': 'ORD', 'london': 'LHR', 'paris': 'CDG', 'tokyo': 'NRT',
            'dubai': 'DXB', 'amsterdam': 'AMS', 'frankfurt': 'FRA', 'madrid': 'MAD',
            'rome': 'FCO', 'barcelona': 'BCN', 'milan': 'MXP', 'zurich': 'ZRH',
        }
        if location.lower().strip() in airport_mappings:
            return airport_mappings[location.lower().strip()]
        return location[:3].upper()

    def normalize_cabin_class(cabin: str) -> str:
        if not cabin:
            return 'ECONOMY'

        try:
            if os.getenv("OPENAI_API_KEY"):
                response = get_text_llm().invoke([HumanMessage(content=get_cabin_type_prompt(cabin))])
                return response.content.strip().upper()
        except Exception as e:
            print(f"Error getting cabin type for {cabin}: {e}")

        cabin_lower = cabin.lower()
        if 'economy' in cabin_lower or 'eco' in cabin_lower or 'coach' in cabin_lower:
            return 'ECONOMY'
        elif 'business' in cabin_lower or 'biz' in cabin_lower:
            return 'BUSINESS'
        elif 'first' in cabin_lower:
            return 'FIRST'
        return 'ECONOMY'

    try:
        if state.get('origin'):
            state['origin_location_code'] = normalize_location_to_airport_code(state['origin'])
        if state.get('destination'):
            state['destination_location_code'] = normalize_location_to_airport_code(state['destination'])
        if state.get('departure_date'):
            state['normalized_departure_date'] = state['departure_date']
        if state.get('cabin_class'):
            state['normalized_cabin'] = normalize_cabin_class(state['cabin_class'])

        state['normalized_trip_type'] = 'round_trip'
        state['current_node'] = 'normalize_info'
    except Exception as e:
        print(f"Error in normalization: {e}")
        state["followup_question"] = "Sorry, I had trouble processing your flight information. Please try again."
        state["needs_followup"] = True

    return state
