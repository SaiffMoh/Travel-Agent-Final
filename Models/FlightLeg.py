from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union, TypedDict
from datetime import datetime

class FlightLeg(BaseModel):
    airline: str = Field(..., description="Airline code")
    flight_number: str = Field(..., description="Flight number")
    departure_airport: str = Field(..., description="Departure airport code")
    arrival_airport: str = Field(..., description="Arrival airport code")
    departure_time: str = Field(..., description="Departure time")
    arrival_time: str = Field(..., description="Arrival time")
    duration: str = Field(..., description="Flight duration")
    stops: Optional[int] = Field(None, description="Number of stops")
    layovers: List[str] = Field(default=[], description="Layover information")