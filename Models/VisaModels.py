"""
Models/VisaModels.py
Pydantic models for visa document extraction and validation.
"""
from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, Dict, Any, List
from datetime import datetime
import re


class VisaData(BaseModel):
    """Complete visa data structure with validation."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_default=True,
        populate_by_name=True
    )
    
    # Core visa information
    visa_type: Optional[str] = Field(
        default=None,
        description="Type of visa (e.g., 'Tourist', 'Business', 'Transit', 'Entry Permit')",
        examples=["Tourist Visa", "Business Visa", "Transit Visa", "Entry Permit", "Work Visa"]
    )
    visa_number: Optional[str] = Field(
        default=None,
        alias="entry_permit_number",
        description="Visa/Entry Permit number (e.g., '206/2025/87553014')"
    )
    country: Optional[str] = Field(
        default=None,
        description="Issuing country (e.g., 'United Arab Emirates', 'UAE')"
    )
    
    # Personal information
    full_name: Optional[str] = Field(
        default=None,
        description="Full name as it appears on visa (preferably 'SURNAME, GIVEN_NAMES' format)"
    )
    surname: Optional[str] = Field(
        default=None,
        description="Surname/Last name"
    )
    given_names: Optional[str] = Field(
        default=None,
        description="Given names/First name(s)"
    )
    nationality: Optional[str] = Field(
        default=None,
        description="Nationality of the visa holder"
    )
    gender: Optional[str] = Field(
        default=None,
        description="Gender (M/F/Male/Female)"
    )
    
    # Passport information
    passport_number: Optional[str] = Field(
        default=None,
        description="Passport number"
    )
    passport_type: Optional[str] = Field(
        default=None,
        description="Type of passport (e.g., 'Normal', 'Diplomatic', 'Service')"
    )
    
    # Dates
    date_of_birth: Optional[str] = Field(
        default=None,
        description="Date of birth in YYYY-MM-DD format"
    )
    date_of_issue: Optional[str] = Field(
        default=None,
        description="Visa issue date in YYYY-MM-DD format"
    )
    date_of_expiry: Optional[str] = Field(
        default=None,
        alias="valid_until",
        description="Visa expiry date in YYYY-MM-DD format"
    )
    
    # Places
    place_of_birth: Optional[str] = Field(
        default=None,
        description="Place of birth"
    )
    place_of_issue: Optional[str] = Field(
        default=None,
        description="Place where visa was issued"
    )
    
    # Occupation and purpose
    profession: Optional[str] = Field(
        default=None,
        alias="occupation",
        description="Profession/occupation of visa holder"
    )
    purpose_of_visit: Optional[str] = Field(
        default=None,
        description="Purpose of visit (e.g., 'Tourism', 'Business', 'Visit')"
    )
    
    # UAE-specific fields
    uid_number: Optional[str] = Field(
        default=None,
        alias="uid_no",
        description="U.I.D. (Unified Identification) number for UAE visas"
    )
    file_number: Optional[str] = Field(
        default=None,
        description="File number or reference number"
    )
    
    # Sponsor/Host information
    host_name: Optional[str] = Field(
        default=None,
        alias="sponsor_name",
        description="Name of sponsor/host in destination country"
    )
    host_address: Optional[str] = Field(
        default=None,
        alias="sponsor_address",
        description="Address of sponsor/host"
    )
    host_phone: Optional[str] = Field(
        default=None,
        description="Phone number of sponsor/host"
    )
    
    # Visa validity and restrictions
    duration_of_stay: Optional[str] = Field(
        default=None,
        description="Duration of stay permitted (e.g., '30 days', '60 days')"
    )
    number_of_entries: Optional[str] = Field(
        default=None,
        description="Number of entries allowed (e.g., 'Single', 'Multiple')"
    )
    
    # Additional information
    remarks: Optional[str] = Field(
        default=None,
        alias="additional_info",
        description="Any additional remarks or information"
    )
    
    # Metadata from extraction process
    extraction_method: Optional[str] = Field(
        default=None,
        description="Method used for extraction (e.g., 'direct_text', 'ocr', 'barcode')"
    )
    extraction_confidence: Optional[str] = Field(
        default=None,
        description="Confidence level of extraction (e.g., '5/5 critical fields')"
    )
    validation_warnings: Optional[List[str]] = Field(
        default_factory=list,
        description="List of validation warnings"
    )
    
    # Source data for debugging
    mrz_data: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="MRZ (Machine Readable Zone) data if available"
    )
    barcode_data: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Barcode data if available"
    )
    structured_data: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Structured data extracted directly from PDF"
    )
    data_sources_used: Optional[List[str]] = Field(
        default_factory=list,
        description="List of data sources used for extraction"
    )
    
    # Raw text for reference
    raw_english_text: Optional[str] = Field(
        default=None,
        exclude=True,  # Don't include in JSON output by default
        description="Raw English text extracted from document"
    )
    raw_arabic_text: Optional[str] = Field(
        default=None,
        exclude=True,  # Don't include in JSON output by default
        description="Raw Arabic text extracted from document"
    )
    mrz_line1: Optional[str] = Field(
        default=None,
        description="First line of MRZ if present"
    )
    mrz_line2: Optional[str] = Field(
        default=None,
        description="Second line of MRZ if present"
    )
    
    @field_validator('date_of_birth', 'date_of_issue', 'date_of_expiry', mode='before')
    @classmethod
    def parse_and_validate_dates(cls, v):
        """Parse and validate dates, converting various formats to YYYY-MM-DD."""
        if v is None or v == "":
            return None
        
        # If already in correct format
        if isinstance(v, str) and re.match(r'^\d{4}-\d{2}-\d{2}$', v):
            return v
        
        # Try to parse different date formats
        date_str = str(v).strip()
        
        # Format: DD-MM-YYYY or DD/MM/YYYY
        for sep in ['-', '/', '.']:
            if sep in date_str:
                parts = date_str.split(sep)
                if len(parts) == 3:
                    try:
                        # Check if it's DD-MM-YYYY or YYYY-MM-DD
                        if len(parts[0]) == 4:  # YYYY-MM-DD
                            year, month, day = parts
                        else:  # DD-MM-YYYY
                            day, month, year = parts
                        
                        # Validate and format
                        year = int(year)
                        month = int(month)
                        day = int(day)
                        
                        # Handle 2-digit years
                        if year < 100:
                            year = 2000 + year if year <= 50 else 1900 + year
                        
                        return f"{year:04d}-{month:02d}-{day:02d}"
                    except (ValueError, TypeError):
                        pass
        
        # Format: DDMMMYYYY (e.g., 01JAN1980)
        if re.match(r'^\d{2}[A-Z]{3}\d{4}$', date_str.upper()):
            try:
                date_obj = datetime.strptime(date_str.upper(), '%d%b%Y')
                return date_obj.strftime('%Y-%m-%d')
            except ValueError:
                pass
        
        # If we can't parse it, return as is and let validation catch it
        return date_str
    
    @field_validator('gender', mode='before')
    @classmethod
    def normalize_gender(cls, v):
        """Normalize gender values."""
        if v is None or v == "":
            return None
        
        v_upper = str(v).strip().upper()
        if v_upper in ['M', 'MALE']:
            return 'Male'
        elif v_upper in ['F', 'FEMALE']:
            return 'Female'
        return v
    
    @field_validator('passport_number', 'visa_number', 'uid_number', mode='before')
    @classmethod
    def clean_id_numbers(cls, v):
        """Clean ID numbers by removing extra spaces and formatting."""
        if v is None or v == "":
            return None
        return str(v).strip().replace(' ', '')
    
    @field_validator('full_name', mode='after')
    @classmethod
    def split_name_if_needed(cls, v, info):
        """If full_name is provided but surname/given_names aren't, try to split."""
        if v and not info.data.get('surname') and not info.data.get('given_names'):
            # Try to split on comma (SURNAME, GIVEN_NAMES format)
            if ',' in v:
                parts = v.split(',', 1)
                info.data['surname'] = parts[0].strip()
                info.data['given_names'] = parts[1].strip() if len(parts) > 1 else None
            # Try to split on space (GIVEN_NAMES SURNAME format)
            elif ' ' in v:
                parts = v.rsplit(' ', 1)
                info.data['given_names'] = parts[0].strip()
                info.data['surname'] = parts[1].strip() if len(parts) > 1 else None
        return v
    
    def model_post_init(self, __context):
        """Post-initialization validation and data quality checks."""
        warnings = []
        
        # Check date consistency
        if self.date_of_issue and self.date_of_expiry:
            try:
                issue_date = datetime.strptime(self.date_of_issue, '%Y-%m-%d')
                expiry_date = datetime.strptime(self.date_of_expiry, '%Y-%m-%d')
                
                if issue_date >= expiry_date:
                    warnings.append("Issue date is after or equal to expiry date")
            except ValueError:
                warnings.append("Date format validation failed")
        
        # Check if visa is expired
        if self.date_of_expiry:
            try:
                expiry_date = datetime.strptime(self.date_of_expiry, '%Y-%m-%d')
                if expiry_date.date() < datetime.now().date():
                    warnings.append(f"Visa expired on {self.date_of_expiry}")
            except ValueError:
                pass
        
        # Check for missing critical fields
        critical_fields = {
            'visa_type': self.visa_type,
            'visa_number': self.visa_number,
            'country': self.country,
            'full_name': self.full_name,
            'passport_number': self.passport_number,
            'date_of_expiry': self.date_of_expiry
        }
        
        missing = [k for k, v in critical_fields.items() if not v]
        if missing:
            warnings.append(f"Missing critical fields: {', '.join(missing)}")
        
        # Add warnings to the model
        if warnings:
            if self.validation_warnings is None:
                self.validation_warnings = []
            self.validation_warnings.extend(warnings)
        
        # Calculate extraction confidence
        fields_filled = sum([1 for v in critical_fields.values() if v])
        self.extraction_confidence = f"{fields_filled}/{len(critical_fields)} critical fields"
