from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union, TypedDict
from datetime import datetime

class HotelSearchState(TypedDict, total=False):
    thread_id: str
    user_message: str
    selected_flight: int
    city_code: str
    hotel_id: list[str]
    checkin_date: str
    checkout_date: str
    currency: str
    roomQuantty: int
    adult: int
    summary: str
    body: Optional[Dict[str, Any]]
    access_token: Optional[str]
    hotels_offers: Optional[List[Dict[str, Any]]]