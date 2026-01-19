"""
Models/PassportModels.py
Pydantic models for passport document extraction and validation.
"""
from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional
from datetime import datetime
import re


class PassportData(BaseModel):
    """Complete passport data structure with validation."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_default=True,
        populate_by_name=True
    )
    
    # Core passport information
    passport_type: Optional[str] = Field(
        default=None,
        description="Type of passport (e.g., 'P' for regular passport, 'D' for diplomatic)"
    )
    country_code: Optional[str] = Field(
        default=None,
        description="3-letter country code (e.g., 'EGY', 'USA', 'GBR')"
    )
    passport_number: Optional[str] = Field(
        default=None,
        alias="PassportNum",
        description="Passport number"
    )
    
    # Personal information
    full_name: Optional[str] = Field(
        default=None,
        alias="NameInPassport",
        description="Full name as it appears in passport"
    )
    surname: Optional[str] = Field(
        default=None,
        description="Surname/Family name/Last name"
    )
    given_names: Optional[str] = Field(
        default=None,
        description="Given names/First name(s)"
    )
    
    # Additional details
    nationality: Optional[str] = Field(
        default=None,
        description="Nationality (3-letter code)"
    )
    gender: Optional[str] = Field(
        default=None,
        description="Gender (M/F/Male/Female/X)"
    )
    
    # Dates
    birth_date: Optional[str] = Field(
        default=None,
        description="Date of birth in YYYY-MM-DD format"
    )
    issued_date: Optional[str] = Field(
        default=None,
        description="Passport issue date in YYYY-MM-DD format"
    )
    expiry_date: Optional[str] = Field(
        default=None,
        alias="ExpiryDate",
        description="Passport expiry date in YYYY-MM-DD format"
    )
    
    # Extraction metadata
    extraction_method: Optional[str] = Field(
        default=None,
        description="Method used for extraction (e.g., 'MRZ_barcode', 'OCR', 'hybrid')"
    )
    
    @field_validator('birth_date', 'issued_date', 'expiry_date', mode='before')
    @classmethod
    def validate_dates(cls, v):
        """Validate and standardize date format."""
        if v is None or v == "":
            return None
        
        # If already in correct format
        if isinstance(v, str) and re.match(r'^\d{4}-\d{2}-\d{2}$', v):
            return v
        
        # Try to parse the date
        date_str = str(v).strip()
        
        # Format: DD-MM-YYYY or DD/MM/YYYY
        for sep in ['-', '/', '.']:
            if sep in date_str:
                parts = date_str.split(sep)
                if len(parts) == 3:
                    try:
                        if len(parts[0]) == 4:  # YYYY-MM-DD
                            year, month, day = parts
                        else:  # DD-MM-YYYY
                            day, month, year = parts
                        
                        year = int(year)
                        month = int(month)
                        day = int(day)
                        
                        # Handle 2-digit years
                        if year < 100:
                            year = 2000 + year if year <= 50 else 1900 + year
                        
                        return f"{year:04d}-{month:02d}-{day:02d}"
                    except (ValueError, TypeError):
                        pass
        
        return date_str
    
    @field_validator('gender', mode='before')
    @classmethod
    def normalize_gender(cls, v):
        """Normalize gender values."""
        if v is None or v == "":
            return None
        
        v_upper = str(v).strip().upper()
        if v_upper in ['M', 'MALE']:
            return 'M'
        elif v_upper in ['F', 'FEMALE']:
            return 'F'
        elif v_upper == 'X':
            return 'X'
        return v
    
    @field_validator('passport_number', mode='before')
    @classmethod
    def clean_passport_number(cls, v):
        """Clean passport number by removing extra spaces."""
        if v is None or v == "":
            return None
        return str(v).strip().replace(' ', '')
    
    @field_validator('country_code', 'nationality', mode='before')
    @classmethod
    def uppercase_codes(cls, v):
        """Convert country codes to uppercase."""
        if v is None or v == "":
            return None
        return str(v).strip().upper()
    
    @field_validator('full_name', mode='after')
    @classmethod
    def construct_full_name(cls, v, info):
        """If full_name is missing but we have surname and given_names, construct it."""
        if not v and info.data.get('surname') and info.data.get('given_names'):
            surname = info.data['surname']
            given = info.data['given_names']
            return f"{given} {surname}".strip()
        return v
    
    def model_post_init(self, __context):
        """Post-initialization validation."""
        # Check if passport is expired
        if self.expiry_date:
            try:
                expiry = datetime.strptime(self.expiry_date, '%Y-%m-%d')
                if expiry.date() < datetime.now().date():
                    # Could add a warning field if needed
                    pass
            except ValueError:
                pass
        
        # Ensure nationality matches country_code if not set
        if not self.nationality and self.country_code:
            self.nationality = self.country_code
