from typing import List, Optional, Dict, Any, TypedDict

class TravelSearchState(TypedDict, total=False):
    # Thread / conversation
    thread_id: str
    conversation: List[Dict[str, Any]]
    current_message: str
    user_message: str
    # Control/flow state
    current_node: Optional[str]
    node_trace: List[str]
    needs_followup: bool
    info_complete: bool
    followup_question: Optional[str]
    request_type: Optional[str]  # flights / hotels / packages
    travel_search_completed: bool
    # Invoice processing (isolated)
    invoice_uploaded: bool  # Flag to indicate an invoice was uploaded
    invoice_pdf_path: Optional[str]  # Path to the uploaded PDF
    extracted_invoice_data: Optional[Dict[str, Any]]  # Extracted invoice data
    invoice_html: Optional[str]  # HTML table for invoice data
    # Flight search
    departure_date: Optional[str]
    return_date: Optional[str]
    duration: Optional[int]
    origin: Optional[str]
    destination: Optional[str]
    cabin_class: Optional[str]
    trip_type: str
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
    flight_offers_day_4: Optional[List[Dict[str, Any]]]
    flight_offers_day_5: Optional[List[Dict[str, Any]]]
    flight_offers_day_6: Optional[List[Dict[str, Any]]]
    flight_offers_day_7: Optional[List[Dict[str, Any]]]
    formatted_results: Optional[List[Dict[str, Any]]]
    # Hotel search
    hotel_ids: Optional[List[str]]
    hotel_id: Optional[List[str]]
    city_code: Optional[str]
    checkin_date_day_1: Optional[str]
    checkout_date_day_1: Optional[str]
    checkin_date_day_2: Optional[str]
    checkout_date_day_2: Optional[str]
    checkin_date_day_3: Optional[str]
    checkout_date_day_3: Optional[str]
    checkin_date_day_4: Optional[str]
    checkout_date_day_4: Optional[str]
    checkin_date_day_5: Optional[str]
    checkout_date_day_5: Optional[str]
    checkin_date_day_6: Optional[str]
    checkout_date_day_6: Optional[str]
    checkin_date_day_7: Optional[str]
    checkout_date_day_7: Optional[str]
    currency: Optional[str]
    room_quantity: Optional[int]
    adult: Optional[int]
    # Hotel results
    hotel_offers_duration_1: Optional[List[Dict[str, Any]]]
    hotel_offers_duration_2: Optional[List[Dict[str, Any]]]
    hotel_offers_duration_3: Optional[List[Dict[str, Any]]]
    hotel_offers_duration_4: Optional[List[Dict[str, Any]]]
    hotel_offers_duration_5: Optional[List[Dict[str, Any]]]
    hotel_offers_duration_6: Optional[List[Dict[str, Any]]]
    hotel_offers_duration_7: Optional[List[Dict[str, Any]]]
    hotel_offers: Optional[List[Dict[str, Any]]]
    travel_packages: List[Dict]
    # Company hotels
    company_hotels_path: Optional[str]
    company_hotels: Optional[Dict[str, Any]]
    # Shared API fields
    body: Optional[Dict[str, Any]]
    access_token: Optional[str]
    package_summary: Optional[str]
    travel_packages_html: Optional[List[str]]
    selected_offer: Optional[Dict[str, Any]]
    package_results: Optional[Any]
    # Visa info
    visa_info_html: Optional[str]