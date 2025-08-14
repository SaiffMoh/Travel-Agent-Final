from typing import List, Optional, Dict, Any, TypedDict
class TravelSearchState(TypedDict, total=False):
    # Thread / conversation
    thread_id: str
    conversation: List[Dict[str, Any]]
    current_message: str
    user_message: str

    # -------------------------
    # Flight search
    # -------------------------
    departure_date: Optional[str]
    return_date: Optional[str]  
    duration: Optional[int]     
    origin: Optional[str]
    destination: Optional[str]
    cabin_class: Optional[str]
    trip_type: str  # default round trip

    # Normalized for Amadeus API
    origin_location_code: Optional[str]
    destination_location_code: Optional[str]
    normalized_departure_date: Optional[str]
    normalized_return_date: Optional[str]
    normalized_cabin: Optional[str]
    normalized_trip_type: Optional[str]

    # Flight results
    flight_offers_day_1: Optional[List[Dict[str, Any]]]
    flight_offers_day_2: Optional[List[Dict[str, Any]]]
    flight_offers_day_3: Optional[List[Dict[str, Any]]]

    # -------------------------
    # Hotel search
    # -------------------------
    hotel_ids: Optional[List[str]]
    checkin_date: Optional[List[str]]   # from departure_date
    checkout_date: Optional[List[str]]  # from departure_date + duration
    currency: Optional[str]
    room_quantity: Optional[int]
    adult: Optional[int]

    # Hotel results
    hotel_offers_duration_1: Optional[List[Dict[str, Any]]]
    hotel_offers_duration_2: Optional[List[Dict[str, Any]]]
    hotel_offers_duration_3: Optional[List[Dict[str, Any]]]
    travel_packages: List[Dict]

    # -------------------------
    # Shared API fields
    # -------------------------
    body: Optional[Dict[str, Any]]
    access_token: Optional[str]
    package_summary: Optional[str]
    destination_location_code: Optional[str]

