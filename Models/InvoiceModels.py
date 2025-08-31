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
    # Core invoice information
    invoice_number: Optional[str] = Field(
        default=None,
        description="Unique identifier for the invoice (e.g., 'INV-2023-001' or '12345')"
    )
    issued_date: Optional[datetime] = Field(default=None, description="Date when the invoice was issued")
    submission_date: Optional[datetime] = Field(default=None, description="Date when the invoice was submitted")
    
    # Vendor and company information
    vendor_type: Optional[str] = Field(
        default=None,
        description="Type of vendor (e.g., 'supplier', 'travel_agency', 'hotel', 'car_rental')",
        examples=["travel_agency", "hotel", "car_rental", "supplier", "airline"]
    )
    vendor_name: Optional[str] = Field(
        default=None,
        description="Name of the vendor/company issuing the invoice"
    )
    subsidiary_name: Optional[str] = Field(
        default=None,
        description="Name of the company or subsidiary that is being billed"
    )
    
    # Invoice status and financials
    invoice_state: Optional[str] = Field(
        default=None,
        description="Current state of the invoice (e.g., 'pending', 'approved', 'paid', 'under_finance_review', 'rejected')",
        examples=["draft", "pending", "under_finance_review", "approved", "paid", "rejected"]
    )
    currency: Optional[str] = Field(
        default=None,
        description="Currency code for all monetary amounts in the invoice (e.g., USD, EUR, EGP)",
        pattern=r"^[A-Z]{3}$"
    )
    
    # Travel details
    travel_agency: Optional[str] = Field(
        default=None,
        description="Name of the travel agency (if different from vendor)"
    )
    flight_details: List[FlightDetail] = Field(
        default_factory=list,
        description="List of flight segments/details"
    )