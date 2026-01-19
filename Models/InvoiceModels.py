from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, List, Union
from datetime import datetime

class FlightDetail(BaseModel):
    """Individual flight segment details within an invoice."""
    model_config = ConfigDict(str_strip_whitespace=True, validate_default=True)
    
    service_type: Optional[str] = Field(default=None, description="Type of service, e.g., Economy, Business")
    airline: Optional[str] = Field(default=None, description="Airline name")
    departure_date: Optional[str] = Field(default=None, description="Departure date (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)")
    arrival_date: Optional[str] = Field(default=None, description="Arrival date (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)")
    origin: Optional[str] = Field(default=None, description="Departure airport or city")
    destination: Optional[str] = Field(default=None, description="Arrival airport or city")
    passenger: Optional[str] = Field(default=None, description="Name of the passenger")
    ticket_number: Optional[str] = Field(default=None, description="Flight ticket number")
    amount: Optional[str] = Field(default=None, description="Base fare amount (string to avoid decimal issues)")
    tax: Optional[str] = Field(default=None, description="Tax amount (string)")
    total_amount: Optional[str] = Field(default=None, description="Total fare amount (string)")
    
    @field_validator('amount', 'tax', 'total_amount', mode='before')
    @classmethod
    def clean_monetary_values(cls, v):
        """Remove commas and ensure proper decimal format."""
        if v is None or v == "":
            return None
        if isinstance(v, (int, float)):
            return f"{float(v):.2f}"
        # Remove commas and convert to float
        try:
            cleaned = str(v).replace(',', '').strip()
            return f"{float(cleaned):.2f}" if cleaned else None
        except (ValueError, TypeError):
            return str(v)
    
    @field_validator('departure_date', 'arrival_date', mode='before')
    @classmethod
    def parse_dates(cls, v):
        """Ensure dates are in string format for flexibility."""
        if v is None or v == "":
            return None
        if isinstance(v, datetime):
            return v.isoformat()
        return str(v)

class InvoiceData(BaseModel):
    """Complete invoice data structure with validation."""
    model_config = ConfigDict(str_strip_whitespace=True, validate_default=True)
    
    # Core invoice information
    invoice_number: Optional[str] = Field(
        default=None,
        description="Unique identifier for the invoice (e.g., 'INV-2023-001' or '12345')"
    )
    issued_date: Optional[str] = Field(
        default=None, 
        description="Date when the invoice was issued (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)"
    )
    submission_date: Optional[str] = Field(
        default=None, 
        description="Date when the invoice was submitted (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)"
    )
    
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
        description="Currency code for all monetary amounts in the invoice (e.g., USD, EUR, EGP)"
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
    
    # Total amount
    total_amount: Optional[str] = Field(
        default=None,
        description="Total invoice amount (string to avoid decimal issues)"
    )
    
    @field_validator('total_amount', mode='before')
    @classmethod
    def clean_total_amount(cls, v):
        """Remove commas and ensure proper decimal format."""
        if v is None or v == "":
            return None
        if isinstance(v, (int, float)):
            return f"{float(v):.2f}"
        try:
            cleaned = str(v).replace(',', '').strip()
            return f"{float(cleaned):.2f}" if cleaned else None
        except (ValueError, TypeError):
            return str(v)
    
    @field_validator('issued_date', 'submission_date', mode='before')
    @classmethod
    def parse_invoice_dates(cls, v):
        """Ensure dates are in string format for flexibility."""
        if v is None or v == "":
            return None
        if isinstance(v, datetime):
            return v.isoformat()
        return str(v)
    
    def model_post_init(self, __context):
        """Post-initialization validation and cleanup."""
        # Deduplicate flight details if needed
        if self.flight_details:
            seen = {}
            deduplicated = []
            for flight in self.flight_details:
                key = (
                    flight.ticket_number,
                    flight.departure_date,
                    flight.origin,
                    flight.destination,
                    flight.passenger
                )
                if key not in seen:
                    seen[key] = True
                    deduplicated.append(flight)
            self.flight_details = deduplicated