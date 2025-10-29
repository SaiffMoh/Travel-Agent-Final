"""
Database Fallback Service - SMART PRICE CALCULATION v2 (full file)

Provides:
- get_flight_offers: returns flights by day (exact match or same-route any-date adjusted)
- get_hotel_ids: returns hotel ids for a city (case-insensitive)
- get_hotel_offers: exact-date lookup OR ANY-dates smart price-per-night scaling (case-insensitive)
- helpers: route_exists, city_exists, get_available_routes, get_available_cities, get_database_stats

Drop this file into your project (replace existing database_fallback.py) and restart your service.
"""

import sqlite3
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import copy


class DatabaseFallbackService:
    def __init__(self, db_path: str = "travel_data.db"):
        self.db_path = db_path

    def _get_connection(self):
        """Get database connection"""
        return sqlite3.connect(self.db_path)

    # -------------------------
    # Flight methods
    # -------------------------
    def get_flight_offers(self,
                         origin: str,
                         destination: str,
                         departure_date: str,
                         cabin_class: str = "ECONOMY",
                         duration: Optional[int] = None) -> Dict[int, List[Dict[str, Any]]]:
        """
        Get flight offers from database - RETURNS DATA BY DAY

        Priority:
        1. Exact match (route + date + cabin [+duration])
        2. Same route/cabin/optional-duration, ANY date -> adjust dates but keep prices
        3. Return empty dict if nothing found (let LLM handle)

        Returns dict: {1: [flights_day1], 2: [flights_day2], 3: [flights_day3]}
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            dep_date = datetime.strptime(departure_date, "%Y-%m-%d").date()

            flights_by_day: Dict[int, List[Dict[str, Any]]] = {}

            # For three consecutive days
            for day_offset in range(3):
                day_num = day_offset + 1
                search_date = (dep_date + timedelta(days=day_offset)).strftime("%Y-%m-%d")

                day_flights: List[Dict[str, Any]] = []

                # Try 1: Exact match (route + date + cabin + optional duration)
                cursor.execute("""
                    SELECT offer_data, duration, search_date, departure_date
                    FROM flight_offers
                    WHERE origin = ?
                    AND destination = ?
                    AND departure_date = ?
                    AND cabin_class = ?
                    AND (? IS NULL OR duration = ?)
                    ORDER BY created_at DESC
                    LIMIT 3
                """, (origin, destination, search_date, cabin_class, duration, duration))

                results = cursor.fetchall()
                for row in results:
                    try:
                        offer_data = json.loads(row[0])
                    except Exception:
                        continue
                    offer_data["_search_date"] = search_date
                    offer_data["_day_number"] = day_num
                    offer_data["_from_database"] = True
                    offer_data["_exact_match"] = True
                    day_flights.append(offer_data)

                # Try 2: Same route/cabin/optional-duration, ANY date (adjust dates)
                if not day_flights:
                    cursor.execute("""
                        SELECT offer_data, duration, search_date, departure_date
                        FROM flight_offers
                        WHERE origin = ?
                        AND destination = ?
                        AND cabin_class = ?
                        AND (? IS NULL OR duration = ?)
                        ORDER BY created_at DESC
                        LIMIT 3
                    """, (origin, destination, cabin_class, duration, duration))

                    results = cursor.fetchall()
                    if results:
                        for row in results:
                            try:
                                offer_data = json.loads(row[0])
                                old_dep_date = row[3]  # stored departure_date in DB row
                            except Exception:
                                continue

                            # Calculate shift in days from old_dep_date to search_date
                            try:
                                target_dt = datetime.strptime(search_date, "%Y-%m-%d")
                                old_dt = datetime.strptime(old_dep_date, "%Y-%m-%d")
                                day_offset_calc = (target_dt - old_dt).days
                            except Exception:
                                day_offset_calc = 0

                            adjusted = self._adjust_flight_dates(offer_data, day_offset_calc)

                            adjusted["_search_date"] = search_date
                            adjusted["_day_number"] = day_num
                            adjusted["_from_database"] = True
                            adjusted["_dates_adjusted"] = True
                            day_flights.append(adjusted)

                flights_by_day[day_num] = day_flights

            conn.close()

            total_flights = sum(len(f) for f in flights_by_day.values())
            if total_flights > 0:
                print(f"✓ Database: Found {total_flights} cached flights for {origin}→{destination}")
                return flights_by_day
            else:
                print(f"✗ Database: No flights found for {origin}→{destination}")
                return {}

        except Exception as e:
            print(f"✗ Database error getting flights: {e}")
            conn.close()
            return {}

    def _adjust_flight_dates(self, flight: Dict[str, Any], day_offset: int) -> Dict[str, Any]:
        """Adjust flight dates by offset days, keeping times and prices the same"""
        adjusted = copy.deepcopy(flight)

        for itinerary in adjusted.get("itineraries", []):
            for segment in itinerary.get("segments", []):
                for key in ["departure", "arrival"]:
                    if key in segment and isinstance(segment[key], dict) and "at" in segment[key]:
                        old_time_str = segment[key]["at"]
                        try:
                            # Accept strings like "2025-11-01T10:00:00" or with Z
                            old_dt = datetime.fromisoformat(old_time_str.replace("Z", "+00:00"))
                            new_dt = old_dt + timedelta(days=day_offset)
                            # Normalize to ISO with Z (UTC)
                            segment[key]["at"] = new_dt.isoformat(timespec='seconds').replace("+00:00", "Z")
                        except Exception as e:
                            print(f"Warning: Could not adjust flight date {old_time_str}: {e}")

        return adjusted

    # -------------------------
    # Hotel methods
    # -------------------------
    def get_hotel_ids(self, city_code: str) -> List[str]:
        """Get hotel IDs for a city from database (case-insensitive)"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT hotel_ids
                FROM city_hotels
                WHERE upper(city_code) = upper(?)
            """, (city_code,))
            result = cursor.fetchone()
            conn.close()

            if result:
                try:
                    hotel_ids = json.loads(result[0])
                except Exception:
                    hotel_ids = result[0]
                print(f"✓ Database: Found {len(hotel_ids) if isinstance(hotel_ids, list) else '1'} hotels for {city_code}")
                return hotel_ids if isinstance(hotel_ids, list) else [hotel_ids]
            else:
                print(f"✗ Database: No hotels found for {city_code}")
                return []

        except Exception as e:
            print(f"✗ Database error getting hotel IDs: {e}")
            conn.close()
            return []

    def get_hotel_offers(self,
                        city_code: str,
                        checkin_date: Optional[str],
                        checkout_date: Optional[str]) -> List[Dict[str, Any]]:
        """
        Get hotel offers from database with SMART PRICE CALCULATION

        Priority:
        1. Exact match (city + exact dates) → Use as-is
        2. Same city + ANY dates (case-insensitive) → Calculate price-per-night and scale to requested duration
        3. Return empty (let LLM handle if city not found)
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            requested_nights = None
            if checkin_date and checkout_date:
                try:
                    checkin_dt = datetime.strptime(checkin_date, "%Y-%m-%d")
                    checkout_dt = datetime.strptime(checkout_date, "%Y-%m-%d")
                    requested_nights = (checkout_dt - checkin_dt).days
                except Exception:
                    requested_nights = None

            # Try 1: Exact match (city + exact dates)
            if checkin_date and checkout_date:
                cursor.execute("""
                    SELECT hotel_data, checkin_date, checkout_date
                    FROM hotel_offers
                    WHERE upper(city_code) = upper(?)
                    AND checkin_date = ?
                    AND checkout_date = ?
                    ORDER BY created_at DESC
                    LIMIT 5
                """, (city_code, checkin_date, checkout_date))

                rows = cursor.fetchall()
                if rows:
                    hotels: List[Dict[str, Any]] = []
                    for row in rows:
                        try:
                            hs = json.loads(row[0])
                        except Exception:
                            continue
                        for h in hs:
                            h["_from_database"] = True
                            h["_exact_match"] = True
                        hotels.extend(hs)
                    conn.close()
                    print(f"✓ Database: Found {len(hotels)} hotels for {city_code} (exact dates)")
                    return hotels

            # Try 2: Same city, ANY dates → case-insensitive match, get multiple recent rows
            print(f"  → No exact match (or not requested), searching for {city_code} with ANY dates (case-insensitive)...")
            cursor.execute("""
                SELECT hotel_data, checkin_date, checkout_date
                FROM hotel_offers
                WHERE upper(city_code) = upper(?)
                ORDER BY created_at DESC
                LIMIT 5
            """, (city_code,))

            rows = cursor.fetchall()
            if rows:
                adjusted_hotels: List[Dict[str, Any]] = []
                for row in rows:
                    try:
                        db_hotels = json.loads(row[0])
                    except Exception:
                        print("  ⚠️  Skipping malformed hotel_data JSON")
                        continue

                    db_checkin = row[1]
                    db_checkout = row[2]

                    # Validate DB dates
                    try:
                        db_checkin_dt = datetime.strptime(db_checkin, "%Y-%m-%d")
                        db_checkout_dt = datetime.strptime(db_checkout, "%Y-%m-%d")
                        db_nights = (db_checkout_dt - db_checkin_dt).days
                    except Exception:
                        print(f"  ⚠️ Skipping DB record with invalid dates: {db_checkin} - {db_checkout}")
                        continue

                    if db_nights <= 0:
                        print(f"  ⚠️ Skipping DB record with non-positive nights: {db_nights}")
                        continue

                    for hotel in db_hotels:
                        adjusted = copy.deepcopy(hotel)
                        # If requested nights provided, scale DB totals to requested nights
                        if requested_nights and requested_nights > 0:
                            self._scale_offers_to_requested_nights(adjusted, db_nights, requested_nights, checkin_date, checkout_date)
                            adjusted["_price_calculated"] = True
                            adjusted["_original_dates"] = f"{db_checkin} to {db_checkout}"
                            adjusted["_original_nights"] = db_nights
                            adjusted["_requested_nights"] = requested_nights
                        else:
                            # Add price-per-night metadata for visibility
                            self._ensure_price_per_night_metadata(adjusted, db_nights)
                            adjusted["_original_dates"] = f"{db_checkin} to {db_checkout}"
                            adjusted["_original_nights"] = db_nights

                        adjusted["_from_database"] = True
                        adjusted["_dates_adjusted"] = True if requested_nights else False
                        adjusted_hotels.append(adjusted)

                conn.close()
                if adjusted_hotels:
                    print(f"✓ Database: Found {len(adjusted_hotels)} hotels for {city_code} (ANY-dates). Adjusted to requested dates if provided.")
                    return adjusted_hotels

            conn.close()
            print(f"✗ Database: No hotels found for {city_code}")
            return []

        except Exception as e:
            print(f"✗ Database error getting hotels: {e}")
            conn.close()
            return []

    def _scale_offers_to_requested_nights(self, hotel: Dict[str, Any], db_nights: int, requested_nights: int, new_checkin: str, new_checkout: str):
        """
        Calculate price-per-night from DB offers and scale to requested duration,
        then update offers' checkInDate/checkOutDate and price fields.
        """
        if "offers" in hotel:
            for offer in hotel["offers"]:
                offer["checkInDate"] = new_checkin
                offer["checkOutDate"] = new_checkout
                if "price" in offer and "total" in offer["price"]:
                    try:
                        db_total = float(offer["price"]["total"])
                        price_per_night = db_total / db_nights
                        new_total = price_per_night * requested_nights
                        # maintain base/total ratio if base exists
                        if "base" in offer["price"]:
                            db_base = float(offer["price"]["base"])
                            base_ratio = db_base / db_total if db_total else 0.9
                            new_base = new_total * base_ratio
                            offer["price"]["base"] = f"{new_base:.2f}"
                        offer["price"]["total"] = f"{new_total:.2f}"
                        offer["price"]["_price_per_night"] = f"{price_per_night:.2f}"
                    except Exception as e:
                        print(f"  ⚠️ Price calculation error when scaling offers: {e}")

        # handle processed-style best_offers if present
        if "best_offers" in hotel:
            for bo in hotel["best_offers"]:
                offer = bo.get("offer", {})
                if offer:
                    offer["checkInDate"] = new_checkin
                    offer["checkOutDate"] = new_checkout
                    if "price" in offer and "total" in offer["price"]:
                        try:
                            db_total = float(offer["price"]["total"])
                            price_per_night = db_total / db_nights
                            new_total = price_per_night * requested_nights
                            if "base" in offer["price"]:
                                db_base = float(offer["price"]["base"])
                                base_ratio = db_base / db_total if db_total else 0.9
                                new_base = new_total * base_ratio
                                offer["price"]["base"] = f"{new_base:.2f}"
                            offer["price"]["total"] = f"{new_total:.2f}"
                            offer["price"]["_price_per_night"] = f"{price_per_night:.2f}"
                        except Exception as e:
                            print(f"  ⚠️ Price calculation error on best_offers: {e}")

    def _ensure_price_per_night_metadata(self, hotel: Dict[str, Any], db_nights: int):
        """
        Ensure offers contain _price_per_night metadata when DB nights are known.
        """
        if "offers" in hotel:
            for offer in hotel["offers"]:
                if "price" in offer and "total" in offer["price"]:
                    try:
                        db_total = float(offer["price"]["total"])
                        price_per_night = db_total / db_nights
                        offer["price"]["_price_per_night"] = f"{price_per_night:.2f}"
                    except Exception:
                        pass

        if "best_offers" in hotel:
            for bo in hotel["best_offers"]:
                offer = bo.get("offer", {})
                if "price" in offer and "total" in offer["price"]:
                    try:
                        db_total = float(offer["price"]["total"])
                        price_per_night = db_total / db_nights
                        offer["price"]["_price_per_night"] = f"{price_per_night:.2f}"
                    except Exception:
                        pass

    # -------------------------
    # Helpers & Stats
    # -------------------------
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

    def city_exists(self, city_code: str) -> bool:
        """Quick check if city exists in database (case-insensitive)"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT COUNT(*) 
                FROM city_hotels 
                WHERE upper(city_code) = upper(?)
            """, (city_code,))
            count = cursor.fetchone()[0]
            conn.close()
            return count > 0

        except Exception as e:
            print(f"✗ Database error checking city: {e}")
            conn.close()
            return False

    def route_exists(self, origin: str, destination: str) -> bool:
        """Quick check if route exists in database"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT COUNT(*) 
                FROM flight_offers 
                WHERE origin = ? AND destination = ?
            """, (origin, destination))
            count = cursor.fetchone()[0]
            conn.close()
            return count > 0

        except Exception as e:
            print(f"✗ Database error checking route: {e}")
            conn.close()
            return False

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