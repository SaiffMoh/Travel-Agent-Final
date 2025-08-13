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
    return_date: Optional[str]  # if known
    duration: Optional[int]     # if round trip, to calculate return_date
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
    flight_offers: Optional[List[Dict[str, Any]]]

    # -------------------------
    # Hotel search
    # -------------------------
    city_code: Optional[str]  # usually destination_location_code
    hotel_ids: Optional[List[str]]
    checkin_date: Optional[str]   # from departure_date
    checkout_date: Optional[str]  # from departure_date + duration
    currency: Optional[str]
    room_quantity: Optional[int]
    adult: Optional[int]

    # Hotel results
    hotels_by_city: Optional[List[Dict[str, Any]]]  # API 2 output
    hotel_offers: Optional[List[Dict[str, Any]]]    # API 3 output

    # -------------------------
    # Shared API fields
    # -------------------------
    body: Optional[Dict[str, Any]]
    access_token: Optional[str]
    package_summary: Optional[str]

