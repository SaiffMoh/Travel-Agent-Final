from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union, TypedDict
from datetime import datetime
from Models.FlightLeg import FlightLeg
class FlightResult(BaseModel):
    price: str = Field(..., description="Flight price")
    currency: str = Field(..., description="Price currency")
    search_date: Optional[str] = Field(None, description="Date this flight was searched for")
    outbound: FlightLeg = Field(..., description="Outbound flight details")
    return_leg: Optional[FlightLeg] = Field(None, description="Return flight details (for round trips)")