"""
Data Collection Script for Travel Agent API - Version 2
Collects real data from Amadeus API and stores it in SQLite database
UPDATES:
- Adds new cities: BCN, MAD, DMM, JFK, LAX (both ECONOMY and BUSINESS)
- Collects BUSINESS class for existing cities: DXB, ALG, RUH, AUH
"""
import requests
import sqlite3
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any
import time
import os
from dotenv import load_dotenv

load_dotenv()

class TravelDataCollector:
    def __init__(self, db_path: str = "travel_data.db"):
        self.db_path = db_path
        self.amadeus_client_id = os.getenv("AMADEUS_CLIENT_ID")
        self.amadeus_client_secret = os.getenv("AMADEUS_CLIENT_SECRET")
        self.access_token = None
        self.init_database()
    
    def init_database(self):
        """Initialize SQLite database with required tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Flight offers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS flight_offers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                origin TEXT NOT NULL,
                destination TEXT NOT NULL,
                departure_date TEXT NOT NULL,
                cabin_class TEXT,
                duration INTEGER,
                search_date TEXT,
                offer_data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Hotel offers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hotel_offers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                city_code TEXT NOT NULL,
                checkin_date TEXT NOT NULL,
                checkout_date TEXT NOT NULL,
                hotel_data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # City hotel IDs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS city_hotels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                city_code TEXT NOT NULL UNIQUE,
                hotel_ids TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_flight_route ON flight_offers(origin, destination)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_flight_date ON flight_offers(departure_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hotel_city ON hotel_offers(city_code)")
        
        conn.commit()
        conn.close()
        print(f"✓ Database initialized at {self.db_path}")
    
    def get_access_token(self) -> str:
        """Get Amadeus API access token"""
        url = "https://test.api.amadeus.com/v1/security/oauth2/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": self.amadeus_client_id,
            "client_secret": self.amadeus_client_secret
        }
        
        try:
            response = requests.post(url, data=data, timeout=10)
            response.raise_for_status()
            self.access_token = response.json()["access_token"]
            print("✓ Access token obtained")
            return self.access_token
        except Exception as e:
            print(f"✗ Error getting access token: {e}")
            raise
    
    def collect_flights_and_hotels(self, routes: List[Dict[str, Any]], date_range_days: int = 15):
        """
        Collect flight data AND corresponding hotel data for multiple routes and dates
        
        Args:
            routes: List of dicts with 'origin', 'destination', and 'cabins' keys
            date_range_days: How many days ahead to search
        """
        if not self.access_token:
            self.get_access_token()
        
        flight_url = "https://test.api.amadeus.com/v2/shopping/flight-offers"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        total_flights_collected = 0
        total_hotels_collected = 0
        
        for route in routes:
            origin = route["origin"]
            destination = route["destination"]
            cabins = route["cabins"]  # List of cabin classes to collect
            
            for cabin in cabins:
                print(f"\nCollecting data: {origin} → {destination} ({cabin})")
                
                # Generate dates
                start_date = datetime.now().date() + timedelta(days=7)  # Start from 7 days ahead
                
                for day_offset in range(0, date_range_days, 3):  # Every 3 days
                    for duration in [3, 5, 7]:  # Only 3, 5, and 7 nights
                        departure_date = (start_date + timedelta(days=day_offset)).strftime("%Y-%m-%d")
                        return_date = (start_date + timedelta(days=day_offset + duration)).strftime("%Y-%m-%d")
                        
                        # Step 1: Collect flights
                        body = {
                            "currencyCode": "EGP",
                            "originDestinations": [
                                {
                                    "id": "1",
                                    "originLocationCode": origin,
                                    "destinationLocationCode": destination,
                                    "departureDateTimeRange": {
                                        "date": departure_date,
                                        "time": "10:00:00"
                                    }
                                },
                                {
                                    "id": "2",
                                    "originLocationCode": destination,
                                    "destinationLocationCode": origin,
                                    "departureDateTimeRange": {
                                        "date": return_date,
                                        "time": "10:00:00"
                                    }
                                }
                            ],
                            "travelers": [{"id": "1", "travelerType": "ADULT"}],
                            "sources": ["GDS"],
                            "searchCriteria": {
                                "maxFlightOffers": 5,
                                "flightFilters": {
                                    "cabinRestrictions": [{
                                        "cabin": cabin,
                                        "coverage": "MOST_SEGMENTS",
                                        "originDestinationIds": ["1", "2"]
                                    }]
                                }
                            }
                        }
                        
                        try:
                            response = requests.post(flight_url, headers=headers, json=body, timeout=30)
                            
                            if response.status_code == 401:
                                print("Token expired, refreshing...")
                                self.get_access_token()
                                headers["Authorization"] = f"Bearer {self.access_token}"
                                response = requests.post(flight_url, headers=headers, json=body, timeout=30)
                            
                            if response.status_code == 200:
                                data = response.json()
                                flights = data.get("data", [])
                                
                                if flights:
                                    # Store each flight offer
                                    for flight in flights:
                                        cursor.execute("""
                                            INSERT INTO flight_offers 
                                            (origin, destination, departure_date, cabin_class, duration, search_date, offer_data)
                                            VALUES (?, ?, ?, ?, ?, ?, ?)
                                        """, (
                                            origin,
                                            destination,
                                            departure_date,
                                            cabin,
                                            duration,
                                            departure_date,
                                            json.dumps(flight)
                                        ))
                                    
                                    conn.commit()
                                    total_flights_collected += len(flights)
                                    print(f"  ✓ {departure_date} ({duration}n): {len(flights)} flights")
                                    
                                    # Step 2: Collect hotels for this destination and date (only once per destination/date combo)
                                    # Check if we need to collect hotels for this destination
                                    if cabin == cabins[0]:  # Only collect hotels once per route/date, not per cabin
                                        hotel_ids = self.get_hotel_ids_for_city(destination)
                                        if hotel_ids:
                                            checkin_date, checkout_date = self.extract_hotel_dates_from_flight(flight, duration)
                                            if checkin_date and checkout_date:
                                                hotels = self.get_hotels_for_dates(destination, hotel_ids, checkin_date, checkout_date)
                                                if hotels:
                                                    cursor.execute("""
                                                        INSERT INTO hotel_offers (city_code, checkin_date, checkout_date, hotel_data)
                                                        VALUES (?, ?, ?, ?)
                                                    """, (destination, checkin_date, checkout_date, json.dumps(hotels)))
                                                    conn.commit()
                                                    total_hotels_collected += len(hotels)
                                                    print(f"  ✓ {checkin_date} ({duration}n): {len(hotels)} hotels")
                                else:
                                    print(f"  ✗ {departure_date} ({duration}n): No flights")
                            else:
                                print(f"  ✗ Flight API Error {response.status_code}: {response.text[:100]}")
                            
                            time.sleep(1)  # Rate limiting
                            
                        except Exception as e:
                            print(f"  ✗ Flight Error: {e}")
                            time.sleep(2)
        
        conn.close()
        print(f"\n✓ Total flights collected: {total_flights_collected}")
        print(f"✓ Total hotels collected: {total_hotels_collected}")
    
    def get_hotel_ids_for_city(self, city_code: str) -> List[str]:
        """Get hotel IDs for a city and cache them"""
        # Check if already cached
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT hotel_ids FROM city_hotels WHERE city_code = ?", (city_code,))
        result = cursor.fetchone()
        
        if result:
            conn.close()
            return json.loads(result[0])
        
        conn.close()
        
        # Not cached, fetch from API
        if not self.access_token:
            self.get_access_token()
        
        url = "https://test.api.amadeus.com/v1/reference-data/locations/hotels/by-city"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.get(url, headers=headers, params={"cityCode": city_code}, timeout=30)
            
            if response.status_code == 401:
                self.get_access_token()
                headers["Authorization"] = f"Bearer {self.access_token}"
                response = requests.get(url, headers=headers, params={"cityCode": city_code}, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                hotels = data.get("data", [])
                hotel_ids = [h.get("hotelId") for h in hotels if h.get("hotelId")][:20]
                
                # Cache in database
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO city_hotels (city_code, hotel_ids)
                    VALUES (?, ?)
                """, (city_code, json.dumps(hotel_ids)))
                conn.commit()
                conn.close()
                
                return hotel_ids
            else:
                print(f"  ✗ Error getting hotel IDs: {response.status_code}")
                return []
        except Exception as e:
            print(f"  ✗ Exception getting hotel IDs: {e}")
            return []
    
    def extract_hotel_dates_from_flight(self, flight_offer: Dict, duration: int) -> tuple:
        """Extract check-in and check-out dates from flight offer"""
        try:
            itineraries = flight_offer.get("itineraries", [])
            if not itineraries:
                return None, None
            
            # Get outbound arrival (check-in)
            outbound_segments = itineraries[0].get("segments", [])
            if not outbound_segments:
                return None, None
            
            final_segment = outbound_segments[-1]
            arrival_iso = final_segment.get("arrival", {}).get("at")
            if not arrival_iso:
                return None, None
            
            checkin_dt = datetime.fromisoformat(arrival_iso.replace("Z", "+00:00"))
            checkin_date = checkin_dt.date().strftime("%Y-%m-%d")
            
            # Get return departure (check-out)
            checkout_date = None
            if len(itineraries) > 1:
                return_segments = itineraries[1].get("segments", [])
                if return_segments:
                    first_return = return_segments[0]
                    departure_iso = first_return.get("departure", {}).get("at")
                    if departure_iso:
                        checkout_dt = datetime.fromisoformat(departure_iso.replace("Z", "+00:00"))
                        checkout_date = checkout_dt.date().strftime("%Y-%m-%d")
            
            if not checkout_date:
                checkout_date = (checkin_dt.date() + timedelta(days=duration)).strftime("%Y-%m-%d")
            
            return checkin_date, checkout_date
        except Exception as e:
            print(f"  ✗ Error extracting dates: {e}")
            return None, None
    
    def get_hotels_for_dates(self, city_code: str, hotel_ids: List[str],
                            checkin: str, checkout: str) -> List[Dict]:
        """Get hotel offers for specific dates"""
        if not self.access_token:
            self.get_access_token()
        
        url = "https://test.api.amadeus.com/v3/shopping/hotel-offers"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        params = {
            "hotelIds": ",".join(hotel_ids[:10]),  # Use first 10 hotels
            "checkInDate": checkin,
            "checkOutDate": checkout
        }
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            
            if response.status_code == 401:
                self.get_access_token()
                headers["Authorization"] = f"Bearer {self.access_token}"
                response = requests.get(url, headers=headers, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                return data.get("data", [])
            elif response.status_code == 429:
                print(f"  ⚠️  Rate limited, waiting...")
                time.sleep(5)
                return self.get_hotels_for_dates(city_code, hotel_ids, checkin, checkout)
            else:
                print(f"  ✗ Hotel API error {response.status_code}")
                return []
        except Exception as e:
            print(f"  ✗ Hotel exception: {e}")
            return []


if __name__ == "__main__":
    collector = TravelDataCollector()
    
    # Define routes with cabin classes
    routes = [
        # EXISTING CITIES - BUSINESS CLASS ONLY (we already have economy)
        {"origin": "CAI", "destination": "DXB", "cabins": ["BUSINESS"]},
        {"origin": "CAI", "destination": "ALG", "cabins": ["BUSINESS"]},
        {"origin": "CAI", "destination": "RUH", "cabins": ["BUSINESS"]},
        {"origin": "CAI", "destination": "AUH", "cabins": ["BUSINESS"]},
        
        # NEW CITIES - BOTH ECONOMY AND BUSINESS
        {"origin": "CAI", "destination": "BCN", "cabins": ["ECONOMY", "BUSINESS"]},  # Barcelona
        {"origin": "CAI", "destination": "MAD", "cabins": ["ECONOMY", "BUSINESS"]},  # Madrid
        {"origin": "CAI", "destination": "DMM", "cabins": ["ECONOMY", "BUSINESS"]},  # Dammam
        {"origin": "CAI", "destination": "JFK", "cabins": ["ECONOMY", "BUSINESS"]},  # New York
        {"origin": "CAI", "destination": "LAX", "cabins": ["ECONOMY", "BUSINESS"]},  # Los Angeles
    ]
    
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║         TRAVEL DATA COLLECTOR - V2 (MULTI-CLASS)         ║
    ╚══════════════════════════════════════════════════════════╝
    
    EXISTING CITIES (Business class only):
      • Cairo (CAI) → Dubai (DXB)
      • Cairo (CAI) → Algiers (ALG)
      • Cairo (CAI) → Riyadh (RUH)
      • Cairo (CAI) → Abu Dhabi (AUH)
    
    NEW CITIES (Economy + Business):
      • Cairo (CAI) → Barcelona (BCN)
      • Cairo (CAI) → Madrid (MAD)
      • Cairo (CAI) → Dammam (DMM)
      • Cairo (CAI) → New York (JFK)
      • Cairo (CAI) → Los Angeles (LAX)
    
    Configuration:
      • Date range: Next 15 days
      • Duration: 3, 5, 7 nights
      • Total routes: 9 (4 existing + 5 new)
      • Total cabin combinations: 14
    
    This will collect:
      ✓ Flight offers for each route/cabin/date/duration
      ✓ Hotel offers for each destination/date
      ✓ All data appended to existing travel_data.db
    
    Estimated time: 40-60 minutes
    """)
    
    confirm = input("Start data collection? (y/n): ").lower()
    
    if confirm == 'y':
        print("\n=== Starting Data Collection ===\n")
        
        # Collect flights AND hotels in one pass
        collector.collect_flights_and_hotels(routes, date_range_days=15)
        
        print("\n=== Data Collection Complete ===")
        print("\nDatabase statistics:")
        
        # Show stats
        conn = sqlite3.connect("travel_data.db")
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM flight_offers")
        total_flights = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM hotel_offers")
        total_hotels = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM city_hotels")
        total_cities = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT origin, destination, cabin_class, COUNT(*) as count
            FROM flight_offers
            GROUP BY origin, destination, cabin_class
            ORDER BY destination, cabin_class
        """)
        routes_summary = cursor.fetchall()
        
        conn.close()
        
        print(f"  • Total flights: {total_flights}")
        print(f"  • Total hotel searches: {total_hotels}")
        print(f"  • Cities with hotels: {total_cities}")
        print(f"\n  Routes breakdown:")
        for origin, dest, cabin, count in routes_summary:
            print(f"    - {origin} → {dest} ({cabin}): {count} flights")
        
        print(f"\n✅ Database ready: travel_data.db")
    else:
        print("\n❌ Data collection cancelled")