from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union, TypedDict
from datetime import datetime

class FlightSearchState(TypedDict, total=False):
    # Thread management
    thread_id: str
    
    # Conversation tracking
    conversation: List[Dict[str, Any]]
    current_message: str
    
    # Extracted information
    departure_date: Optional[str]
    origin: Optional[str]
    destination: Optional[str]
    cabin_class: Optional[str]
    trip_type: str  # Default to round trip
    duration: Optional[int]
    
    # Normalized information for API calls
    origin_location_code: Optional[str]
    destination_location_code: Optional[str]
    normalized_departure_date: Optional[str]
    normalized_cabin: Optional[str]
    normalized_trip_type: Optional[str]
    
    # API request data
    body: Optional[Dict[str, Any]]
    access_token: Optional[str]
    
    # Results
    result: Optional[Dict[str, Any]]
    formatted_results: Optional[List[Dict[str, Any]]]
    summary: Optional[str]
    
    # Flow control
    needs_followup: bool
    info_complete: bool
    followup_question: Optional[str]
    current_node: Optional[str]
    followup_count: int
    
    # Debug information
    node_trace: List[str]