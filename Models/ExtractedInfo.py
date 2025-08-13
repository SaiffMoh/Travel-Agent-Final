from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union, TypedDict
from datetime import datetime
class ExtractedInfo(BaseModel):
    departure_date: Optional[str] = Field(None, description="Departure date in YYYY-MM-DD format")
    origin: Optional[str] = Field(None, description="Origin city or airport")
    destination: Optional[str] = Field(None, description="Destination city or airport")
    cabin_class: Optional[str] = Field(None, description="Cabin class (economy, business, first class)")
    trip_type: Optional[str] = Field(None, description="Trip type (one way, round trip)")
    duration: Optional[int] = Field(None, description="Duration in days for round trip")