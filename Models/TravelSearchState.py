from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union, TypedDict
from datetime import datetime
from Models import FlightSearchState, HotelSearchState

class TravelSearchState(FlightSearchState, HotelSearchState, total=False):
    """Combined state for workflows involving both flights and hotels."""
    pass