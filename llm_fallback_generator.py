"""
LLM-Based Fallback Data Generator
Uses Watson LLM with real schema examples to generate realistic travel data
"""

import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from Utils.watson_config import llm_extraction, ModelType, llm_generic
import sqlite3


class LLMFallbackGenerator:
    """Generate realistic flight and hotel data using LLM with schema templates"""
    
    def __init__(self, db_path: str = "travel_data.db"):
        self.db_path = db_path
        self.flight_template = None
        self.hotel_template = None
        self._load_templates()
    
    def _load_templates(self):
        """Load real examples from database to use as templates"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get a real flight example
            cursor.execute("""
                SELECT offer_data FROM flight_offers 
                WHERE cabin_class = 'ECONOMY'
                LIMIT 1
            """)
            result = cursor.fetchone()
            if result:
                self.flight_template = json.loads(result[0])
            
            # Get a real hotel example
            cursor.execute("""
                SELECT hotel_data FROM hotel_offers 
                LIMIT 1
            """)
            result = cursor.fetchone()
            if result:
                hotels = json.loads(result[0])
                if hotels:
                    self.hotel_template = hotels[0]
            
            conn.close()
            print("✓ Loaded schema templates from database")
            
        except Exception as e:
            print(f"⚠️  Could not load templates: {e}")
            # Fallback to hardcoded minimal templates
            self._use_minimal_templates()
    
    def _use_minimal_templates(self):
        """Use minimal hardcoded templates if DB not available"""
        self.flight_template = {
            "type": "flight-offer",
            "id": "1",
            "itineraries": [
                {
                    "segments": [
                        {
                            "departure": {"iataCode": "CAI", "at": "2025-11-01T10:00:00"},
                            "arrival": {"iataCode": "DXB", "at": "2025-11-01T14:30:00"},
                            "carrierCode": "MS",
                            "number": "123",
                            "aircraft": {"code": "738"}
                        }
                    ]
                }
            ],
            "price": {
                "currency": "EGP",
                "total": "12000",
                "base": "10000"
            }
        }
        
        self.hotel_template = {
            "hotel": {"name": "Sample Hotel", "hotelId": "HOTEL123"},
            "offers": [
                {
                    "room": {"type": "STANDARD"},
                    "price": {"currency": "EGP", "total": "2000"}
                }
            ]
        }
    
    def generate_flight_offers(self,
                               origin: str,
                               destination: str,
                               departure_date: str,
                               cabin_class: str = "ECONOMY",
                               duration: int = 5,
                               num_offers: int = 3) -> List[Dict[str, Any]]:
        """
        Generate realistic flight offers using LLM
        
        Args:
            origin: Origin airport code (e.g., "CAI")
            destination: Destination airport code (e.g., "LHR")
            departure_date: Departure date (YYYY-MM-DD)
            cabin_class: ECONOMY or BUSINESS
            duration: Trip duration in nights
            num_offers: Number of flight offers to generate
        
        Returns:
            List of flight offers in Amadeus format
        """
        
        # Calculate return date
        dep_date = datetime.strptime(departure_date, "%Y-%m-%d")
        ret_date = dep_date + timedelta(days=duration)
        
        prompt = f"""You are a travel data generator. Generate {num_offers} realistic flight offers in JSON format.

USER QUERY:
- Route: {origin} → {destination}
- Departure: {departure_date}
- Return: {ret_date.strftime('%Y-%m-%d')}
- Cabin: {cabin_class}
- Duration: {duration} nights

SCHEMA TEMPLATE (follow this exact structure):
{json.dumps(self.flight_template, indent=2)}

INSTRUCTIONS:
1. Generate {num_offers} different flight offers with varying prices and airlines
2. Use realistic airline codes for this route (e.g., MS for EgyptAir, BA for British Airways, LH for Lufthansa)
3. Use realistic aircraft codes (787/777 for long-haul, 320/321/738 for short/medium)
4. Flight numbers should be 3-4 digits
5. Departure times should be realistic (morning/afternoon/evening, not 2am)
6. Flight duration should be realistic for the distance
7. Prices in EGP:
   - Short-haul (<1500km): Economy 8k-15k, Business 25k-45k
   - Medium-haul (1500-4000km): Economy 12k-25k, Business 35k-65k
   - Long-haul (4000km+): Economy 25k-50k, Business 60k-120k
8. Add small price variations between offers
9. Each offer should have BOTH outbound and return itineraries
10. Return flight should depart {duration} days after arrival

OUTPUT FORMAT:
Return a valid JSON array of {num_offers} flight offers. Each offer must follow the schema template exactly.
Only return the JSON array, no additional text.

Example output structure:
[
  {{flight_offer_1}},
  {{flight_offer_2}},
  {{flight_offer_3}}
]
"""

        try:
            print(f"🤖 Generating {num_offers} flights via LLM...")
            response = llm_generic.generate(
                prompt,
                model_type=ModelType.GENERIC,
                params={'max_tokens': 8192, 'temperature': 0.3}
            )
            
            generated_text = response['results'][0]['generated_text']
            
            # Extract JSON from response
            # Sometimes LLM wraps it in ```json blocks
            if "```json" in generated_text:
                generated_text = generated_text.split("```json")[1].split("```")[0]
            elif "```" in generated_text:
                generated_text = generated_text.split("```")[1].split("```")[0]
            
            flights = json.loads(generated_text.strip())
            
            # Validate it's a list
            if not isinstance(flights, list):
                flights = [flights]
            
            # Add metadata
            for i, flight in enumerate(flights):
                flight["_from_llm"] = True
                flight["_generated_for"] = f"{origin}-{destination}"
            
            print(f"✓ Generated {len(flights)} flight offers")
            return flights
            
        except Exception as e:
            print(f"✗ LLM generation failed: {e}")
            # Fallback to rule-based for this specific case
            return self._rule_based_flight_fallback(
                origin, destination, departure_date, cabin_class, duration, num_offers
            )
    
    def generate_hotel_offers(self,
                             city_code: str,
                             checkin_date: str,
                             checkout_date: str,
                             num_offers: int = 5) -> List[Dict[str, Any]]:
        """
        Generate realistic hotel offers using LLM
        
        Args:
            city_code: City/destination code (e.g., "LHR", "DXB")
            checkin_date: Check-in date (YYYY-MM-DD)
            checkout_date: Check-out date (YYYY-MM-DD)
            num_offers: Number of hotel offers to generate
        
        Returns:
            List of hotel offers in Amadeus format
        """
        
        # Calculate nights
        checkin_dt = datetime.strptime(checkin_date, "%Y-%m-%d")
        checkout_dt = datetime.strptime(checkout_date, "%Y-%m-%d")
        nights = (checkout_dt - checkin_dt).days
        
        prompt = f"""You are a travel data generator. Generate {num_offers} realistic hotel offers in JSON format.

USER QUERY:
- City: {city_code}
- Check-in: {checkin_date}
- Check-out: {checkout_date}
- Nights: {nights}

SCHEMA TEMPLATE (follow this exact structure):
{json.dumps(self.hotel_template, indent=2)}

INSTRUCTIONS:
1. Generate {num_offers} different hotels with varying prices and star ratings
2. Use realistic hotel names (e.g., "Hilton Downtown", "Radisson Blu", "Marriott Suites")
3. Hotel IDs should be alphanumeric (e.g., "HTLHR001")
4. Star ratings: 3-5 stars
5. Room types: STANDARD, SUPERIOR, DELUXE, SUITE
6. Prices in EGP per night:
   - 3-star: 800-1500 per night
   - 4-star: 1500-3000 per night
   - 5-star: 3000-6000 per night
   - Premium cities (Dubai, London, NYC): Add 50% to prices
7. Total price should be: (price per night × {nights} nights)
8. Include base price (90% of total) and taxes/fees (10%)
9. Sort hotels from cheapest to most expensive

OUTPUT FORMAT:
Return a valid JSON array of {num_offers} hotel offers. Each offer must follow the schema template exactly.
Only return the JSON array, no additional text.
"""

        try:
            print(f"🤖 Generating {num_offers} hotels via LLM...")
            response = llm_generic.generate(
                prompt,
                model_type=ModelType.GENERIC,
                params={'max_tokens': 8192, 'temperature': 0.4}
            )
            
            generated_text = response['results'][0]['generated_text']
            
            # Extract JSON from response
            if "```json" in generated_text:
                generated_text = generated_text.split("```json")[1].split("```")[0]
            elif "```" in generated_text:
                generated_text = generated_text.split("```")[1].split("```")[0]
            
            hotels = json.loads(generated_text.strip())
            
            # Validate it's a list
            if not isinstance(hotels, list):
                hotels = [hotels]
            
            # Add metadata
            for hotel in hotels:
                hotel["_from_llm"] = True
                hotel["_generated_for"] = city_code
            
            print(f"✓ Generated {len(hotels)} hotel offers")
            return hotels
            
        except Exception as e:
            print(f"✗ LLM generation failed: {e}")
            # Fallback to rule-based
            return self._rule_based_hotel_fallback(
                city_code, checkin_date, checkout_date, num_offers
            )
    
    def _rule_based_flight_fallback(self, origin, destination, departure_date, 
                                     cabin_class, duration, num_offers):
        """Emergency rule-based fallback if LLM fails"""
        print("🔄 Using emergency rule-based generation...")
        
        import random
        
        dep_date = datetime.strptime(departure_date, "%Y-%m-%d")
        ret_date = dep_date + timedelta(days=duration)
        
        # Simple price ranges
        if cabin_class == "BUSINESS":
            base_price = random.randint(35000, 80000)
        else:
            base_price = random.randint(10000, 30000)
        
        flights = []
        for i in range(num_offers):
            price_variation = random.uniform(0.9, 1.1)
            final_price = int(base_price * price_variation)
            
            flight = {
                "type": "flight-offer",
                "id": f"EMERGENCY_{i+1}",
                "price": {
                    "currency": "EGP",
                    "total": str(final_price),
                    "base": str(int(final_price * 0.85))
                },
                "itineraries": [
                    {
                        "segments": [{
                            "departure": {"iataCode": origin, "at": f"{departure_date}T10:00:00"},
                            "arrival": {"iataCode": destination, "at": f"{departure_date}T14:00:00"},
                            "carrierCode": "MS",
                            "number": str(random.randint(100, 999))
                        }]
                    },
                    {
                        "segments": [{
                            "departure": {"iataCode": destination, "at": f"{ret_date.strftime('%Y-%m-%d')}T15:00:00"},
                            "arrival": {"iataCode": origin, "at": f"{ret_date.strftime('%Y-%m-%d')}T19:00:00"},
                            "carrierCode": "MS",
                            "number": str(random.randint(100, 999))
                        }]
                    }
                ],
                "_emergency_fallback": True
            }
            flights.append(flight)
        
        return flights
    
    def _rule_based_hotel_fallback(self, city_code, checkin_date, checkout_date, num_offers):
        """Emergency rule-based fallback if LLM fails"""
        print("🔄 Using emergency rule-based generation...")
        
        import random
        
        checkin_dt = datetime.strptime(checkin_date, "%Y-%m-%d")
        checkout_dt = datetime.strptime(checkout_date, "%Y-%m-%d")
        nights = (checkout_dt - checkin_dt).days
        
        hotels = []
        for i in range(num_offers):
            rate_per_night = random.randint(1000, 3500)
            total_price = rate_per_night * nights
            
            hotel = {
                "hotel": {
                    "name": f"Hotel {city_code} {i+1}",
                    "hotelId": f"EMERGENCY{i:03d}"
                },
                "offers": [{
                    "room": {"type": "STANDARD"},
                    "price": {
                        "currency": "EGP",
                        "total": str(total_price),
                        "base": str(int(total_price * 0.9))
                    },
                    "checkInDate": checkin_date,
                    "checkOutDate": checkout_date
                }],
                "_emergency_fallback": True
            }
            hotels.append(hotel)
        
        return hotels


# Testing
if __name__ == "__main__":
    generator = LLMFallbackGenerator()
    
    print("\n=== Testing Flight Generation ===")
    flights = generator.generate_flight_offers(
        origin="CAI",
        destination="LHR",
        departure_date="2025-11-20",
        cabin_class="BUSINESS",
        duration=7,
        num_offers=3
    )
    print(f"\nGenerated {len(flights)} flights")
    if flights:
        print(f"Sample price: {flights[0]['price']['total']} {flights[0]['price']['currency']}")
    
    print("\n=== Testing Hotel Generation ===")
    hotels = generator.generate_hotel_offers(
        city_code="LHR",
        checkin_date="2025-11-20",
        checkout_date="2025-11-27",
        num_offers=5
    )
    print(f"\nGenerated {len(hotels)} hotels")
    if hotels and hotels[0].get('offers'):
        print(f"Sample price: {hotels[0]['offers'][0]['price']['total']} EGP")