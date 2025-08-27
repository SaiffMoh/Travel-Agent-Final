from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class FlightDetail(BaseModel):
    service_type: Optional[str] = Field(default=None, description="Type of service, e.g., Economy, Business")
    airline: Optional[str] = Field(default=None, description="Airline name")
    departure_date: Optional[datetime] = Field(default=None, description="Departure date and time")
    arrival_date: Optional[datetime] = Field(default=None, description="Arrival date and time")
    origin: Optional[str] = Field(default=None, description="Departure airport or city")
    destination: Optional[str] = Field(default=None, description="Arrival airport or city")
    passenger: Optional[str] = Field(default=None, description="Name of the passenger")
    ticket_number: Optional[str] = Field(default=None, description="Flight ticket number")
    amount: Optional[str] = Field(default=None, description="Base fare amount (string to avoid decimal issues)")
    tax: Optional[str] = Field(default=None, description="Tax amount (string)")
    total_amount: Optional[str] = Field(default=None, description="Total fare amount (string)")

class InvoiceData(BaseModel):
    issued_date: Optional[datetime] = Field(default=None, description="Date when the invoice was issued")
    submission_date: Optional[datetime] = Field(default=None, description="Date when the invoice was submitted")
    travel_agency: Optional[str] = Field(default=None, description="Name of the travel agency")
    subsidiary_name: Optional[str] = Field(default=None, description="Name of the company or subsidiary")
    flight_details: List[FlightDetail] = Field(default_factory=list, description="List of flight segments/details")
