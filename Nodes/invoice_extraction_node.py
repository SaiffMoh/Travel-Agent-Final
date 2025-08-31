from typing import Dict, Optional, Any
from Models.TravelSearchState import TravelSearchState
from Models.InvoiceModels import InvoiceData
from pathlib import Path
import pdfplumber
import re
import json
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv
from Utils.invoice_to_html import invoice_to_html
import os

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def generate_system_prompt(schema_json: str) -> str:
    return f"""
You are an expert document parser specialized in flight and travel invoices.

Your job is to extract ALL structured data from a messy OCR invoice text.

CRITICAL INSTRUCTIONS:
1. Extract ONLY information explicitly present in the document.
2. Deduplicate flight entries with identical ticket_number, departure_date, origin, destination, and passenger, summing their amount and total_amount.
3. Include a top-level total_amount as the sum of all flight_details total_amount values.
4. Do NOT infer or add default values (e.g., times, service_type) unless explicitly stated.
5. For missing ticket_number, use invoice_number with an index (e.g., 'CR2500002644-1').

EXTRACTION RULES:
1. For invoice numbers, look for patterns (case insensitive): 'Invoice #', 'INV-', 'No.', 'Number:', 'Ref:', 'Reference:', 'Internal ID'.
2. For vendor types, use only if explicitly mentioned:
   - 'travel_agency' (e.g., 'travel agency', 'Expedia', Tax Activity Code '7911')
   - 'airline' (e.g., 'Egypt Air')
   - 'hotel', 'car_rental', 'supplier'
3. For invoice state, use 'pending', 'valid', or 'canceled' if stated; default to 'pending'.
4. For currency, use 3-letter ISO codes (e.g., USD, EGP) from symbols or text.
5. For flight details, MANDATORY fields:
   - airline: Infer from flight number (e.g., 'MS' → 'Egypt Air') if not explicit.
   - origin, destination: Use city or airport code.
   - departure_date, arrival_date: Use exact dates/times as provided; do NOT add default times.
   - service_type: Extract only if explicitly stated (e.g., 'class: E-'); otherwise, leave null.
   - passenger, ticket_number, amount, tax, total_amount: Extract if available; use 0.00 for missing amounts.
6. If ticket_number is missing, generate as '<invoice_number>-<index>' (e.g., 'CR2500002644-1').

RULES:
1. Do NOT return 'N/A' or defaults for optional fields; use null.
2. For missing dates, use current date for issued_date only if not provided.
3. Deduplicate flight_details by ticket_number, departure_date, origin, destination, passenger, summing amounts.
4. For currency, validate as 3-letter ISO code.
5. Ensure flight segments have consistent data as per the document.

Return ONLY a valid JSON matching this schema:
{schema_json}
""".strip()

SYSTEM_PROMPT = generate_system_prompt(InvoiceData.model_json_schema())

def invoice_extraction_node(state: TravelSearchState) -> TravelSearchState:
    """Node to process an uploaded invoice PDF and generate an HTML table."""
    try:
        pdf_path = state.get("invoice_pdf_path")
        if not pdf_path or not Path(pdf_path).exists():
            print("ERROR: No valid PDF path in state")
            state["needs_followup"] = True
            state["followup_question"] = "No invoice found to process. Please upload a valid PDF."
            state["extracted_invoice_data"] = None
            state["invoice_html"] = None
            json_path = Path("data/uploads/json_outputs") / f"{state['thread_id']}_{Path(pdf_path).stem}.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump({"error": "No valid PDF path in state"}, f, indent=2)
            return state

        # Extract text from PDF
        text_list = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_list.append(text)
        text = "\n".join(text_list).strip()
        if not text:
            print("ERROR: No text extracted from PDF")
            state["needs_followup"] = True
            state["followup_question"] = "The uploaded PDF is empty or unreadable. Please upload a valid invoice PDF."
            state["extracted_invoice_data"] = None
            state["invoice_html"] = None
            json_path = Path("data/uploads/json_outputs") / f"{state['thread_id']}_{Path(pdf_path).stem}.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump({"error": "No text extracted from PDF"}, f, indent=2)
            return state

        # Extract structured data using LLM
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text}
            ],
            temperature=0,
        )
        reply = response.choices[0].message.content.strip()
        print(f"LLM raw response: {reply}")
        cleaned_reply = re.sub(r"^```(?:json)?|```$", "", reply.strip(), flags=re.MULTILINE).strip()

        # Parse and clean the response
        try:
            parsed = json.loads(cleaned_reply)

            # Deduplicate flight_details
            def deduplicate_flights(flights: list, invoice_number: str) -> list:
                if not flights:
                    return []
                deduped = {}
                for idx, flight in enumerate(flights):
                    if not isinstance(flight, dict):
                        continue
                    # Handle missing ticket_number
                    ticket_number = flight.get("ticket_number")
                    if not ticket_number or ticket_number in ["", "null", "N/A", "Unknown"]:
                        ticket_number = f"{invoice_number}-{idx + 1}"
                        flight["ticket_number"] = ticket_number
                    key = (
                        ticket_number,
                        flight.get("departure_date"),
                        flight.get("origin"),
                        flight.get("destination"),
                        flight.get("passenger")
                    )
                    if key in deduped:
                        deduped[key]["amount"] = str(float(deduped[key].get("amount", 0)) + float(flight.get("amount", 0)))
                        deduped[key]["total_amount"] = str(float(deduped[key].get("total_amount", 0)) + float(flight.get("total_amount", 0)))
                    else:
                        deduped[key] = flight.copy()
                return list(deduped.values())

            # Clean LLM output
            def clean_value(value: Any) -> Any:
                if value is None or value == "" or value == "N/A" or value == "null" or value == "Unknown":
                    return None
                if isinstance(value, dict):
                    cleaned = {k: clean_value(v) for k, v in value.items()}
                    return cleaned if cleaned else None
                elif isinstance(value, list):
                    cleaned = [clean_value(v) for v in value]
                    return [v for v in cleaned if v is not None] or None
                elif isinstance(value, str):
                    value = value.strip()
                    if not value or value.lower() in ['null', 'none', 'n/a', 'unknown']:
                        return None
                    value = re.sub(r'\s+', ' ', value).strip('\'"')
                    return value if value else None
                return value

            cleaned = {}
            invoice_number = parsed.get("invoice_number", "Unknown")
            for k, v in parsed.items():
                if k == 'flight_details' and isinstance(v, list):
                    cleaned_flights = deduplicate_flights(v, invoice_number)
                    if cleaned_flights:
                        cleaned['flight_details'] = cleaned_flights
                else:
                    cleaned_v = clean_value(v)
                    if cleaned_v is not None:
                        cleaned[k] = cleaned_v

            # Calculate total_amount
            if 'flight_details' in cleaned and cleaned['flight_details']:
                total_amount = sum(float(flight.get("total_amount", 0)) for flight in cleaned['flight_details'])
                cleaned['total_amount'] = str(total_amount)

            if 'invoice_number' in cleaned and isinstance(cleaned['invoice_number'], str):
                invoice_num = cleaned['invoice_number'].strip()
                for prefix in ['Invoice', 'INV', 'No.', '#', ':', 'Internal ID']:
                    if invoice_num.startswith(prefix):
                        invoice_num = invoice_num[len(prefix):].strip()
                cleaned['invoice_number'] = invoice_num if invoice_num and invoice_num != 'Unknown' else None

            if 'flight_details' in cleaned and not cleaned['flight_details']:
                del cleaned['flight_details']

            if 'currency' in cleaned and isinstance(cleaned['currency'], str):
                cleaned['currency'] = cleaned['currency'].strip().upper()
                if len(cleaned['currency']) != 3 or not cleaned['currency'].isalpha():
                    del cleaned['currency']

            cleaned.setdefault("subsidiary_name", None)
            cleaned.setdefault("travel_agency", None)
            cleaned.setdefault("issued_date", datetime.now().isoformat())
            invoice = InvoiceData(**cleaned)

            # Save JSON with thread_id
            thread_id = state["thread_id"]
            json_path = Path("data/uploads/json_outputs") / f"{thread_id}_{Path(pdf_path).stem}.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(invoice.dict(), f, indent=2, default=str)

            # Generate HTML table
            html_table = invoice_to_html(invoice.dict())

            # Update state
            state["extracted_invoice_data"] = invoice.dict()
            state["invoice_html"] = html_table
            state["needs_followup"] = True
            state["followup_question"] = "Invoice processed successfully. Would you like to proceed with a travel search or something else?"
            state["invoice_uploaded"] = False
            state["invoice_pdf_path"] = None

            return state

        except json.JSONDecodeError as je:
            print(f"ERROR: Failed to parse GPT response: {je}, raw response: {reply}")
            state["needs_followup"] = True
            state["followup_question"] = "Failed to parse invoice data. Please upload a valid PDF with recognizable invoice details."
            state["extracted_invoice_data"] = None
            state["invoice_html"] = None
            json_path = Path("data/uploads/json_outputs") / f"{state['thread_id']}_{Path(pdf_path).stem}.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump({"error": f"Failed to parse GPT response: {str(je)}"}, f, indent=2)
            return state
    except Exception as e:
        print(f"ERROR: Invoice processing failed: {e}")
        state["needs_followup"] = True
        state["followup_question"] = f"Error processing invoice: {str(e)}. Please try uploading a valid PDF."
        state["extracted_invoice_data"] = None
        state["invoice_html"] = None
        json_path = Path("data/uploads/json_outputs") / f"{state['thread_id']}_{Path(pdf_path).stem}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({"error": f"Invoice processing failed: {str(e)}"}, f, indent=2)
        return state