"""
Database Fallback Service - FIXED VERSION
Only returns exact matches, no "closest date" fallback
"""

import sqlite3
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional


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
        Get flight offers from database - EXACT MATCHES ONLY
        
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
                
                # ONLY try exact match - no closest date fallback
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
                print(f"✗ Database: No flights found for {origin}→{destination} on {departure_date}")
            
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
        """Get hotel offers from database - EXACT MATCHES ONLY"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # ONLY try exact match - no closest date fallback
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
            
            conn.close()
            
            if result:
                hotels = json.loads(result[0])
                # Add metadata
                for hotel in hotels:
                    hotel["_from_database"] = True
                print(f"✓ Database: Found {len(hotels)} cached hotels for {city_code}")
                return hotels
            else:
                print(f"✗ Database: No hotels found for {city_code} on {checkin_date}")
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