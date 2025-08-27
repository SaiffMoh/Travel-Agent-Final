import os
import json
import re
import pdfplumber
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from openai import OpenAI
from dotenv import load_dotenv
from datetime import datetime
from Models.InvoiceModels import InvoiceData

# Load environment variables
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 🧠 System prompt
def generate_system_prompt(schema_json: str) -> str:
    return f"""
You are an expert document parser specialized in flight and travel invoices.

Your job is to extract ALL the structured data from a messy OCR invoice text.

CRITICAL INSTRUCTIONS:
1. You MUST extract ALL possible information from the invoice text.
2. If a field is not explicitly found, make a REASONABLE inference based on the context.
3. For dates and times, if not explicitly stated, infer from context or use logical defaults.
4. For flight details, if any segment is missing, try to derive it from other available information.

EXTRACTION RULES:
1. ONLY extract information that is explicitly present in the document
2. DO NOT infer or guess any values that are not clearly stated
3. For invoice numbers, look for these exact patterns (case insensitive):
   - 'Invoice #', 'INV-', 'No.', 'Number:', 'Ref:', 'Reference:'
4. For vendor types, only use if explicitly mentioned:
   - 'travel_agency' - Only if 'travel agency' or similar is mentioned
   - 'airline' - Only if airline name is present
   - 'hotel' - Only if hotel name is present
   - 'car_rental' - Only if car rental company is mentioned
   - 'supplier' - Only if supplier is mentioned
5. For invoice state, only include if explicitly stated in the document
6. For currency, only include if a currency symbol or code is present

For EACH flight in flight_details, these fields are MANDATORY:
- airline (infer from flight number or carrier code if not explicit)
- origin (city/airport code, required)
- destination (city/airport code, required)
- departure_date (required, infer from context if needed)
- arrival_date (required, must be after departure_date)
- service_type (infer from class if not specified, default to 'Economy')

RULES:
1. NEVER return null for any field - always provide a meaningful value
2. For missing dates, use logical defaults (e.g., current date for issued_date)
3. For missing flight details, try to infer from flight numbers, times, or other context
4. If a numeric field is missing, use 0.00 for amounts
5. If a text field is missing, use 'Unknown' or derive from context
6. For flight segments, ensure all times and dates are consistent
7. For vendor_type, infer from context (e.g., if 'travel agency' is mentioned, use 'travel_agency')
8. For invoice_state, if nothing indicates otherwise, default to 'pending'
9. For currency, look for currency symbols (€, $, £, EGP, etc.) or 3-letter codes in the document

Return ONLY a valid JSON that matches this schema:
{schema_json}
""".strip()

SYSTEM_PROMPT = generate_system_prompt(InvoiceData.model_json_schema())

class InvoiceExtractor:
    def __init__(self, output_dir: str = "invoice_outputs"):
        """Initialize the invoice extractor with output directory."""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True, parents=True)

    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """Extract text from a PDF file."""
        try:
            text_list = []
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        text_list.append(text)
            return "\n".join(text_list).strip()
        except Exception as e:
            raise Exception(f"Failed to read PDF {pdf_path}: {str(e)}")

    def clean_llm_output(self, parsed: dict) -> dict:
        """Clean the LLM output by only including fields that have actual values."""
        def clean_value(value: Any) -> Any:
            if value is None or value == "" or value == "N/A" or value == "null":
                return None
                
            if isinstance(value, dict):
                # Clean nested dictionaries
                cleaned = {}
                for k, v in value.items():
                    cleaned_v = clean_value(v)
                    if cleaned_v is not None:
                        cleaned[k] = cleaned_v
                return cleaned if cleaned else None
                
            elif isinstance(value, list):
                # Clean lists, removing None values
                cleaned = [clean_value(v) for v in value]
                return [v for v in cleaned if v is not None] or None
                
            elif isinstance(value, str):
                value = value.strip()
                if not value or value.lower() in ['null', 'none', 'n/a']:
                    return None
                # Clean up common issues in text fields
                value = re.sub(r'\s+', ' ', value)  # Normalize whitespace
                value = value.strip('\'"')  # Remove surrounding quotes
                return value if value else None
                
            return value
            
        # Clean the entire parsed dictionary
        cleaned = {}
        for k, v in parsed.items():
            cleaned_v = clean_value(v)
            if cleaned_v is not None:
                cleaned[k] = cleaned_v
                
        # Special handling for flight_details - ensure it's a list if it exists
        if 'flight_details' in cleaned and not isinstance(cleaned['flight_details'], list):
            del cleaned['flight_details']
                
        # Clean and validate invoice number if it exists
        if 'invoice_number' in cleaned and cleaned['invoice_number']:
            # Remove common prefixes/suffixes and clean up the number
            invoice_num = str(cleaned['invoice_number']).strip()
            # Remove common prefixes/suffixes
            for prefix in ['Invoice', 'INV', 'No.', '#', ':']:
                if invoice_num.startswith(prefix):
                    invoice_num = invoice_num[len(prefix):].strip()
            cleaned['invoice_number'] = invoice_num if invoice_num else None
        
        # Ensure flight_details is always a list
        if 'flight_details' not in cleaned:
            cleaned['flight_details'] = []
            
        # Handle date fields
        current_date = datetime.now().isoformat()
        date_fields = ['issued_date', 'due_date']
        for date_field in date_fields:
            if date_field in cleaned and (cleaned[date_field] is None or cleaned[date_field] == ''):
                cleaned[date_field] = current_date
            elif date_field in cleaned and isinstance(cleaned[date_field], datetime):
                cleaned[date_field] = cleaned[date_field].isoformat()
        
        # Ensure currency is uppercase and valid
        if 'currency' in cleaned and isinstance(cleaned['currency'], str):
            cleaned['currency'] = cleaned['currency'].strip().upper()
            if len(cleaned['currency']) != 3 or not cleaned['currency'].isalpha():
                cleaned['currency'] = 'USD'  # Fallback to USD if invalid
        
        return cleaned

    def extract_invoice_data(self, text: str) -> Tuple[Optional[InvoiceData], str]:
        """Extract structured data from invoice text using LLM with improved error handling."""
        try:
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text}
                ],
                temperature=0,
            )
            
            reply = response.choices[0].message.content.strip()
            
            # Clean GPT output from markdown block like ```json ... ```
            cleaned_reply = re.sub(r"^```(?:json)?|```$", "", reply.strip(), flags=re.MULTILINE).strip()
            
            try:
                # Parse and clean the response
                parsed = json.loads(cleaned_reply)
                cleaned = self.clean_llm_output(parsed)
                
                # Ensure flight details is a list
                if "flight_details" not in cleaned or not isinstance(cleaned["flight_details"], list):
                    cleaned["flight_details"] = []
                
                # Clean each flight detail
                cleaned_flights = []
                for flight in cleaned["flight_details"]:
                    if not isinstance(flight, dict):
                        continue
                    
                    # Ensure all required flight fields exist
                    clean_flight = {
                        'airline': flight.get('airline', 'Unknown'),
                        'origin': flight.get('origin', 'Unknown'),
                        'destination': flight.get('destination', 'Unknown'),
                        'departure_date': flight.get('departure_date', datetime.now().isoformat()),
                        'arrival_date': flight.get('arrival_date', datetime.now().isoformat()),
                        'service_type': flight.get('service_type', 'Economy'),
                        'passenger': flight.get('passenger', 'Unknown'),
                        'ticket_number': flight.get('ticket_number', ''),
                        'amount': flight.get('amount', '0.00'),
                        'tax': flight.get('tax', '0.00'),
                        'total_amount': flight.get('total_amount', '0.00')
                    }
                    cleaned_flights.append(clean_flight)
                
                cleaned["flight_details"] = cleaned_flights
                
                # Ensure other required fields
                cleaned.setdefault("subsidiary_name", "Unknown")
                cleaned.setdefault("travel_agency", "Unknown")
                cleaned.setdefault("issued_date", datetime.now().isoformat())
                
                # Convert to Pydantic model with validation
                invoice = InvoiceData(**cleaned)
                
                # Final check for null values
                null_fields = self.find_null_fields(invoice.model_dump())
                if null_fields:
                    print(f"⚠️ Warning: Found null fields after cleaning: {null_fields}")
                    # Apply final cleanup for any remaining nulls
                    for field in null_fields:
                        self._clean_null_field(invoice, field)
                
                return invoice, cleaned_reply
                
            except json.JSONDecodeError as je:
                print("❌ Failed to parse GPT response as JSON:", je)
                print("🔎 GPT raw output:\n", reply)
                return None, f"Invalid JSON response: {str(je)}"
                
        except Exception as e:
            print(f"❌ Error processing invoice: {str(e)}")
            if 'reply' in locals():
                print(f"Raw response: {reply}")
            return None, f"Processing error: {str(e)}"
    
    def _clean_null_field(self, obj: Any, field_path: str) -> None:
        """Clean a specific null field by setting a default value."""
        if not field_path:
            return
            
        parts = field_path.split('.')
        current = obj
        
        try:
            # Navigate to the parent of the field
            for part in parts[:-1]:
                if '[' in part and ']' in part:  # Handle list indices
                    list_part, idx = part.split('[')
                    idx = int(idx[:-1])
                    current = getattr(current, list_part)[idx]
                else:
                    current = getattr(current, part)
            
            # Get the field name (last part)
            field_name = parts[-1]
            
            # Set default value based on field type/name
            if 'date' in field_name.lower():
                default = datetime.now().isoformat()
            elif any(f in field_name.lower() for f in ['amount', 'price', 'total', 'tax']):
                default = '0.00'
            elif field_name == 'service_type':
                default = 'Economy'
            elif field_name in ['airline', 'origin', 'destination', 'passenger']:
                default = 'Unknown'
            else:
                default = ''
            
            # Set the field value
            if hasattr(current, field_name):
                setattr(current, field_name, default)
                
        except (AttributeError, IndexError, ValueError) as e:
            print(f"⚠️ Warning: Could not clean field {field_path}: {str(e)}")
    
    def find_null_fields(self, data: Any, path: str = "") -> List[str]:
        """Recursively find all null/None values in a nested dictionary."""
        null_fields = []

        if isinstance(data, dict):
            for k, v in data.items():
                new_path = f"{path}.{k}" if path else k
                if v is None:
                    null_fields.append(new_path)
                elif isinstance(v, (dict, list)):
                    null_fields.extend(self.find_null_fields(v, new_path))

        elif isinstance(data, list):
            for i, item in enumerate(data):
                if item is None:
                    null_fields.append(f"{path}[{i}]")
                else:
                    null_fields.extend(self.find_null_fields(item, f"{path}[{i}]"))

        return null_fields

    def process_pdf(self, pdf_path: str) -> Tuple[Optional[dict], str]:
        """Process a single PDF file and return extracted data."""
        try:
            # Extract text from PDF
            text = self.extract_text_from_pdf(pdf_path)
            
            # Save raw text for debugging
            pdf_name = Path(pdf_path).stem
            raw_text_path = self.output_dir / f"{pdf_name}_raw.txt"
            with open(raw_text_path, "w", encoding="utf-8") as f:
                f.write(text)
            
            # Extract structured data
            invoice_data, raw_output = self.extract_invoice_data(text)
            
            if invoice_data:
                # Save the extracted data
                json_path = self.output_dir / f"{pdf_name}.json"
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(invoice_data.model_dump(), f, indent=2, default=str)
                
                return invoice_data.model_dump(), str(json_path)
            
            return None, "Failed to extract data from PDF"
            
        except Exception as e:
            print(f"❌ Error processing {pdf_path}: {str(e)}")
            return None, str(e)

    def process_directory(self, directory: str) -> Dict[str, dict]:
        """Process all PDFs in a directory and return results."""
        results = {}
        pdf_files = list(Path(directory).glob("*.pdf"))
        
        for pdf_file in pdf_files:
            print(f"\nProcessing {pdf_file.name}...")
            result, message = self.process_pdf(str(pdf_file))
            if result:
                results[pdf_file.name] = result
                print(f"✅ Successfully processed {pdf_file.name}")
            else:
                print(f"❌ Failed to process {pdf_file.name}: {message}")
        
        # Save combined results
        if results:
            combined_path = self.output_dir / "combined.json"
            with open(combined_path, "w", encoding="utf-8") as f:
                json.dump(list(results.values()), f, indent=2, default=str)
            print(f"\n📦 Combined results saved to: {combined_path}")
        
        return results

def process_invoice_pdfs(directory: str) -> Dict[str, dict]:
    """Main function to process invoice PDFs in a directory."""
    extractor = InvoiceExtractor()
    return extractor.process_directory(directory)