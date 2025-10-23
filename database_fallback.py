"""
Database Fallback Service
Retrieves flight and hotel data from local SQLite database when Amadeus API fails
"""

import sqlite3
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import random


class DatabaseFallbackService:
    def __init__(self, db_path: str = "travel_data.db"):
        self.db_path = db_path
    
    def _get_connection(self):
        """Get database connection"""
        return sqlite3.connect(self.db_path)
    
    def get_flight_offers(self, 
                         origin: str,
                         destination: str,
                         departure_date: str,
                         cabin_class: str = "ECONOMY",
                         duration: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get flight offers from database
        
        Returns list of flight offers for 7 consecutive days starting from departure_date
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Parse departure date
            dep_date = datetime.strptime(departure_date, "%Y-%m-%d").date()
            
            all_flights = []
            
            # Get flights for 7 consecutive days
            for day_offset in range(7):
                search_date = (dep_date + timedelta(days=day_offset)).strftime("%Y-%m-%d")
                
                # Try exact match first
                cursor.execute("""
                    SELECT offer_data, duration, search_date
                    FROM flight_offers
                    WHERE origin = ? 
                    AND destination = ?
                    AND departure_date = ?
                    AND cabin_class = ?
                    AND (? IS NULL OR duration = ?)
                    ORDER BY created_at DESC
                    LIMIT 5
                """, (origin, destination, search_date, cabin_class, duration, duration))
                
                results = cursor.fetchall()
                
                # If no exact date match, find closest date
                if not results:
                    cursor.execute("""
                        SELECT offer_data, duration, search_date,
                               ABS(julianday(departure_date) - julianday(?)) as date_diff
                        FROM flight_offers
                        WHERE origin = ?
                        AND destination = ?
                        AND cabin_class = ?
                        AND (? IS NULL OR duration = ?)
                        ORDER BY date_diff ASC, created_at DESC
                        LIMIT 5
                    """, (search_date, origin, destination, cabin_class, duration, duration))
                    
                    results = cursor.fetchall()
                
                # Process results for this day
                day_flights = []
                for row in results:
                    offer_data = json.loads(row[0])
                    # Add metadata
                    offer_data["_search_date"] = search_date
                    offer_data["_day_number"] = day_offset + 1
                    offer_data["_from_database"] = True
                    day_flights.append(offer_data)
                
                all_flights.extend(day_flights)
            
            conn.close()
            
            if all_flights:
                print(f"✓ Database: Found {len(all_flights)} cached flights for {origin}→{destination}")
            else:
                print(f"✗ Database: No flights found for {origin}→{destination}")
            
            return all_flights
            
        except Exception as e:
            print(f"✗ Database error getting flights: {e}")
            conn.close()
            return []
    
    def get_hotel_ids(self, city_code: str) -> List[str]:
        """Get hotel IDs for a city from database"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT hotel_ids
                FROM city_hotels
                WHERE city_code = ?
            """, (city_code,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                hotel_ids = json.loads(result[0])
                print(f"✓ Database: Found {len(hotel_ids)} hotels for {city_code}")
                return hotel_ids
            else:
                print(f"✗ Database: No hotels found for {city_code}")
                return []
                
        except Exception as e:
            print(f"✗ Database error getting hotel IDs: {e}")
            conn.close()
            return []
    
    def get_hotel_offers(self,
                        city_code: str,
                        checkin_date: str,
                        checkout_date: str) -> List[Dict[str, Any]]:
        """Get hotel offers from database"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Try exact match first
            cursor.execute("""
                SELECT hotel_data
                FROM hotel_offers
                WHERE city_code = ?
                AND checkin_date = ?
                AND checkout_date = ?
                ORDER BY created_at DESC
                LIMIT 1
            """, (city_code, checkin_date, checkout_date))
            
            result = cursor.fetchone()
            
            # If no exact match, find closest dates
            if not result:
                cursor.execute("""
                    SELECT hotel_data,
                           ABS(julianday(checkin_date) - julianday(?)) as checkin_diff,
                           ABS(julianday(checkout_date) - julianday(?)) as checkout_diff
                    FROM hotel_offers
                    WHERE city_code = ?
                    ORDER BY (checkin_diff + checkout_diff) ASC, created_at DESC
                    LIMIT 1
                """, (checkin_date, checkout_date, city_code))
                
                result = cursor.fetchone()
            
            conn.close()
            
            if result:
                hotels = json.loads(result[0])
                # Add metadata
                for hotel in hotels:
                    hotel["_from_database"] = True
                print(f"✓ Database: Found {len(hotels)} cached hotels for {city_code}")
                return hotels
            else:
                print(f"✗ Database: No hotels found for {city_code}")
                return []
                
        except Exception as e:
            print(f"✗ Database error getting hotels: {e}")
            conn.close()
            return []
    
    def get_available_routes(self) -> List[Dict[str, str]]:
        """Get all available routes in database"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT DISTINCT origin, destination
                FROM flight_offers
                ORDER BY origin, destination
            """)
            
            results = cursor.fetchall()
            conn.close()
            
            routes = [{"origin": row[0], "destination": row[1]} for row in results]
            return routes
            
        except Exception as e:
            print(f"✗ Database error getting routes: {e}")
            conn.close()
            return []
    
    def get_available_cities(self) -> List[str]:
        """Get all available cities in database"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT DISTINCT city_code
                FROM city_hotels
                ORDER BY city_code
            """)
            
            results = cursor.fetchall()
            conn.close()
            
            cities = [row[0] for row in results]
            return cities
            
        except Exception as e:
            print(f"✗ Database error getting cities: {e}")
            conn.close()
            return []
    
    def get_database_stats(self) -> Dict[str, Any]:
        """Get statistics about database contents"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Flight stats
            cursor.execute("SELECT COUNT(*) FROM flight_offers")
            total_flights = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(DISTINCT origin || '-' || destination) FROM flight_offers")
            unique_routes = cursor.fetchone()[0]
            
            # Hotel stats
            cursor.execute("SELECT COUNT(*) FROM hotel_offers")
            total_hotel_searches = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM city_hotels")
            cities_with_hotels = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                "total_flights": total_flights,
                "unique_routes": unique_routes,
                "total_hotel_searches": total_hotel_searches,
                "cities_with_hotels": cities_with_hotels
            }
            
        except Exception as e:
            print(f"✗ Database error getting stats: {e}")
            conn.close()
            return {}


# Fallback data generator for completely missing data
class FallbackDataGenerator:
    """Generate realistic dummy data when database has no matches"""
    
    @staticmethod
    def generate_flight_offer(origin: str, destination: str, departure_date: str, 
                             cabin: str = "ECONOMY", duration: int = 5) -> Dict[str, Any]:
        """Generate a realistic flight offer"""
        
        dep_datetime = datetime.strptime(departure_date, "%Y-%m-%d")
        ret_datetime = dep_datetime + timedelta(days=duration)
        
        # Random flight times
        dep_time = f"{random.randint(6, 22):02d}:{random.choice(['00', '15', '30', '45'])}:00"
        arr_time = f"{random.randint(6, 22):02d}:{random.choice(['00', '15', '30', '45'])}:00"
        
        # Price ranges based on cabin
        price_ranges = {
            "ECONOMY": (8000, 15000),
            "PREMIUM_ECONOMY": (15000, 25000),
            "BUSINESS": (25000, 45000),
            "FIRST": (45000, 80000)
        }
        
        base_price = random.randint(*price_ranges.get(cabin, (8000, 15000)))
        
        return {
            "type": "flight-offer",
            "id": f"FALLBACK_{random.randint(1000, 9999)}",
            "source": "GDS",
            "instantTicketingRequired": False,
            "nonHomogeneous": False,
            "oneWay": False,
            "lastTicketingDate": (dep_datetime - timedelta(days=3)).strftime("%Y-%m-%d"),
            "numberOfBookableSeats": random.randint(1, 9),
            "itineraries": [
                {
                    "duration": f"PT{random.randint(3, 8)}H{random.randint(0, 59)}M",
                    "segments": [
                        {
                            "departure": {
                                "iataCode": origin,
                                "at": f"{departure_date}T{dep_time}"
                            },
                            "arrival": {
                                "iataCode": destination,
                                "at": f"{departure_date}T{arr_time}"
                            },
                            "carrierCode": random.choice(["MS", "LH", "AF", "BA"]),
                            "number": str(random.randint(100, 999)),
                            "aircraft": {"code": random.choice(["320", "321", "738", "789"])},
                            "operating": {"carrierCode": random.choice(["MS", "LH", "AF", "BA"])},
                            "duration": f"PT{random.randint(3, 8)}H{random.randint(0, 59)}M",
                            "id": "1",
                            "numberOfStops": 0
                        }
                    ]
                },
                {
                    "duration": f"PT{random.randint(3, 8)}H{random.randint(0, 59)}M",
                    "segments": [
                        {
                            "departure": {
                                "iataCode": destination,
                                "at": f"{ret_datetime.strftime('%Y-%m-%d')}T{dep_time}"
                            },
                            "arrival": {
                                "iataCode": origin,
                                "at": f"{ret_datetime.strftime('%Y-%m-%d')}T{arr_time}"
                            },
                            "carrierCode": random.choice(["MS", "LH", "AF", "BA"]),
                            "number": str(random.randint(100, 999)),
                            "aircraft": {"code": random.choice(["320", "321", "738", "789"])},
                            "operating": {"carrierCode": random.choice(["MS", "LH", "AF", "BA"])},
                            "duration": f"PT{random.randint(3, 8)}H{random.randint(0, 59)}M",
                            "id": "2",
                            "numberOfStops": 0
                        }
                    ]
                }
            ],
            "price": {
                "currency": "EGP",
                "total": str(base_price),
                "base": str(base_price * 0.85),
                "fees": [{"amount": str(base_price * 0.15), "type": "SUPPLIER"}],
                "grandTotal": str(base_price)
            },
            "pricingOptions": {
                "fareType": ["PUBLISHED"],
                "includedCheckedBagsOnly": True
            },
            "validatingAirlineCodes": [random.choice(["MS", "LH", "AF", "BA"])],
            "travelerPricings": [
                {
                    "travelerId": "1",
                    "fareOption": "STANDARD",
                    "travelerType": "ADULT",
                    "price": {
                        "currency": "EGP",
                        "total": str(base_price),
                        "base": str(base_price * 0.85)
                    }
                }
            ],
            "_from_database": True,
            "_is_generated": True
        }
    
    @staticmethod
    def generate_hotel_offer(hotel_name: str, checkin: str, checkout: str) -> Dict[str, Any]:
        """Generate a realistic hotel offer"""
        
        checkin_dt = datetime.strptime(checkin, "%Y-%m-%d")
        checkout_dt = datetime.strptime(checkout, "%Y-%m-%d")
        nights = (checkout_dt - checkin_dt).days
        
        rate_per_night = random.randint(800, 3000)
        total_price = rate_per_night * nights
        
        return {
            "type": "hotel-offers",
            "hotel": {
                "name": hotel_name,
                "hotelId": f"FALLBACK{random.randint(10000, 99999)}",
                "chainCode": random.choice(["HI", "RT", "MC", "AC"]),
                "rating": str(random.randint(3, 5))
            },
            "available": True,
            "offers": [
                {
                    "id": f"OFFER_{random.randint(1000, 9999)}",
                    "checkInDate": checkin,
                    "checkOutDate": checkout,
                    "rateCode": "RAC",
                    "room": {
                        "type": random.choice(["STANDARD", "SUPERIOR", "DELUXE"]),
                        "typeEstimated": {
                            "category": "STANDARD_ROOM",
                            "beds": random.randint(1, 2),
                            "bedType": "DOUBLE"
                        }
                    },
                    "guests": {"adults": 1},
                    "price": {
                        "currency": "EGP",
                        "base": str(total_price * 0.9),
                        "total": str(total_price),
                        "variations": {
                            "average": {"base": str(rate_per_night)}
                        }
                    },
                    "policies": {
                        "cancellation": {
                            "type": "FULL_REFUND"
                        }
                    }
                }
            ],
            "_from_database": True,
            "_is_generated": True
        }