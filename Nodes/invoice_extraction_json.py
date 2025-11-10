import json
import os
import re
from typing import Dict, List
import pdfplumber
from Models.TravelSearchState import TravelSearchState
from Utils.watson_config import llm
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def clean_json_response(response: str) -> str:
    """Clean the LLM response to extract valid JSON."""
    response = response.strip()
    
    # Remove common LLM artifacts
    response = re.sub(r'<\|eom_id\|>.*$', '', response, flags=re.DOTALL)
    response = re.sub(r'<\|end\|>.*$', '', response, flags=re.DOTALL)
    response = re.sub(r'```(?:json)?', '', response)
    response = response.strip()
    
    # Extract JSON object using regex - find the outermost braces
    json_pattern = r'\{(?:[^{}]|{[^{}]*})*\}'
    matches = re.findall(json_pattern, response, re.DOTALL)
    
    if matches:
        json_str = max(matches, key=len)
        return json_str.strip()
    
    # Fallback: try to find JSON between first { and last }
    start_idx = response.find('{')
    end_idx = response.rfind('}')
    
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        return response[start_idx:end_idx + 1].strip()
    
    return response

def deduplicate_flight_entries(flight_details: List[Dict]) -> List[Dict]:
    """Deduplicate flight entries based on key fields."""
    if not flight_details:
        return flight_details

    deduplicated = []
    seen = {}
    
    for entry in flight_details:
        key = (
            entry.get("ticket_number"),
            entry.get("departure_date"),
            entry.get("origin"),
            entry.get("destination"),
            entry.get("passenger")
        )
        
        if key in seen:
            # Sum amounts for duplicates
            idx = seen[key]
            try:
                current_amount = float(str(deduplicated[idx]["amount"]).replace(',', ''))
                new_amount = float(str(entry["amount"]).replace(',', ''))
                current_total = float(str(deduplicated[idx]["total_amount"]).replace(',', ''))
                new_total = float(str(entry["total_amount"]).replace(',', ''))
                current_tax = float(str(deduplicated[idx]["tax"]).replace(',', ''))
                new_tax = float(str(entry["tax"]).replace(',', ''))
                
                deduplicated[idx]["amount"] = f"{current_amount + new_amount:.2f}"
                deduplicated[idx]["total_amount"] = f"{current_total + new_total:.2f}"
                deduplicated[idx]["tax"] = f"{current_tax + new_tax:.2f}"
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to sum amounts for duplicate entry {key}: {e}")
                continue
        else:
            seen[key] = len(deduplicated)
            # Clean monetary values
            for field in ["amount", "tax", "total_amount"]:
                if entry.get(field):
                    try:
                        value = str(entry[field]).replace(',', '')
                        entry[field] = f"{float(value):.2f}"
                    except (ValueError, TypeError):
                        pass
            deduplicated.append(entry)
    
    return deduplicated

def invoice_extraction_json(pdf_path, thread_id):
    """Extract structured data from uploaded invoice PDF using Watsonx LLM."""
    pdf_path = pdf_path
    thread_id = thread_id

  
    # Extract text from PDF
    with pdfplumber.open(pdf_path) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    logger.info(f"Extracted text from {pdf_path}: {text[:500]}...")

    # Enhanced prompt for better extraction
    prompt = f"""<|SYSTEM|>You are an expert document parser specialized in flight and travel invoices.

Extract structured data from the OCR invoice text and return ONLY a valid JSON object.

CRITICAL REQUIREMENTS:
1. Return ONLY the JSON object - no additional text, tokens, or explanations
2. Use double quotes for all strings in JSON
3. Ensure all monetary values are strings without commas (e.g., "44994.00")
4. Use null for missing fields (not "null" string)
5. Dates in ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS
6. No trailing commas in JSON
7. Extract ALL flight segments from the invoice

JSON SCHEMA:
{{
"SRReferenceNumber":
"InvoiceDate": 
"InvoiceNumber": 
"Status":
"IsCash":
"Currency":
"CurrencyRate":
"OriginalInvoice":
"Airlines":
"Cost":
"ChangeFees":
"RefundFees":
"Flight":
"Insurance":
"Transportation":
"Accommodation":
"Others":
"Reviewed":

}}

OCR TEXT:
{text}

<|USER|>Return only the JSON object with no extra text or tokens.<|END|>"""

    # Invoke Watsonx LLM
    response = llm.generate(prompt=prompt)
    raw_reply = response["results"][0]["generated_text"].strip()
    logger.info(f"Watsonx LLM raw response: {raw_reply}")

    # Clean and parse JSON
    cleaned_reply = clean_json_response(raw_reply)
    logger.info(f"Cleaned JSON response: {cleaned_reply}")
      
    invoice_data = json.loads(cleaned_reply)
    
    if not isinstance(invoice_data, dict):
        raise ValueError("Response is not a JSON object")

    # Deduplicate and clean flight details
    if invoice_data.get("flight_details"):
        invoice_data["flight_details"] = deduplicate_flight_entries(invoice_data["flight_details"])
        
        # Recalculate total amount
        try:
            total = sum(
                float(str(flight["total_amount"]).replace(',', '')) 
                for flight in invoice_data["flight_details"] 
                if flight.get("total_amount")
            )
            invoice_data["total_amount"] = f"{total:.2f}"
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to recalculate total_amount: {e}")

    return invoice_data

if __name__ == "__main__":
    pdf_path = "data/test/TIN2500039810.pdf"
    thread_id = "123"
    invoice_data = invoice_extraction_json(pdf_path, thread_id)
    print(json.dumps(invoice_data, indent=2))