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
    # Remove common LLM artifacts
    response = response.strip()
    
    # Remove end-of-message tokens and similar artifacts
    response = re.sub(r'<\|eom_id\|>.*$', '', response, flags=re.DOTALL)
    response = re.sub(r'<\|end\|>.*$', '', response, flags=re.DOTALL)
    response = re.sub(r'```(?:json)?', '', response)
    response = response.strip()
    
    # Extract JSON object using regex - find the outermost braces
    json_pattern = r'\{(?:[^{}]|{[^{}]*})*\}'
    matches = re.findall(json_pattern, response, re.DOTALL)
    
    if matches:
        # Take the largest match (most complete JSON)
        json_str = max(matches, key=len)
        return json_str.strip()
    
    # Fallback: try to find JSON between first { and last }
    start_idx = response.find('{')
    end_idx = response.rfind('}')
    
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        return response[start_idx:end_idx + 1].strip()
    
    return response

def deduplicate_flight_entries(flight_details: List[Dict]) -> List[Dict]:
    """Deduplicate flight entries based on ticket_number, departure_date, origin, destination, and passenger."""
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
            # Sum amounts and total_amounts
            idx = seen[key]
            try:
                # Clean monetary values by removing commas
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
            # Clean monetary values in the entry
            for field in ["amount", "tax", "total_amount"]:
                if entry.get(field):
                    try:
                        value = str(entry[field]).replace(',', '')
                        entry[field] = f"{float(value):.2f}"
                    except (ValueError, TypeError):
                        pass
            deduplicated.append(entry)
    return deduplicated

def invoice_extraction_node(state: TravelSearchState) -> TravelSearchState:
    """Extract structured data from uploaded invoice PDF using Watsonx LLM."""
    pdf_path = state.get("invoice_pdf_path")
    thread_id = state.get("thread_id")
    
    if not pdf_path or not os.path.exists(pdf_path):
        logger.error(f"PDF path not found or invalid: {pdf_path}")
        state["extracted_invoice_data"] = None
        state["invoice_html"] = "<div class='question-response'><div class='question'><p>No PDF file found. Please upload a valid invoice.</p></div></div>"
        state["followup_question"] = "No PDF file found. Please upload a valid invoice."
        state["needs_followup"] = True
        return state

    try:
        # Extract text from PDF
        with pdfplumber.open(pdf_path) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        logger.info(f"Extracted text from {pdf_path}: {text[:500]}...")

        # Build prompt for Watsonx - Updated to be more explicit about JSON format
        prompt = f"""<|SYSTEM|>You are an expert document parser specialized in flight and travel invoices.

Extract structured data from the OCR invoice text and return ONLY a valid JSON object.

CRITICAL REQUIREMENTS:
1. Return ONLY the JSON object - no additional text, tokens, or explanations
2. Use double quotes for all strings in JSON
3. Ensure all monetary values are strings without commas (e.g., "44994.00")
4. Use null for missing fields (not "null" string)
5. Dates in ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS
6. No trailing commas in JSON
7. No extra tokens like <|eom_id|> or <|end|>

JSON SCHEMA:
{{
    "invoice_number": "string or null",
    "issued_date": "YYYY-MM-DDTHH:MM:SS or null",
    "submission_date": "YYYY-MM-DDTHH:MM:SS or null",
    "vendor_type": "travel_agency or null",
    "vendor_name": "string or null",
    "subsidiary_name": "string or null",
    "invoice_state": "string or null",
    "currency": "string or null",
    "travel_agency": "string or null",
    "flight_details": [
        {{
            "airline": "string or null",
            "origin": "string or null",
            "destination": "string or null",
            "departure_date": "YYYY-MM-DD or null",
            "arrival_date": "YYYY-MM-DD or null",
            "passenger": "string or null",
            "ticket_number": "string or null",
            "service_type": "string or null",
            "amount": "string or null",
            "tax": "string or null",
            "total_amount": "string or null"
        }}
    ],
    "total_amount": "string or null"
}}

OCR TEXT:
{text}

<|USER|>Return only the JSON object with no extra text or tokens.<|END|>"""

        logger.info(f"Watsonx prompt: {prompt[:500]}...")

        # Invoke Watsonx LLM
        response = llm.generate(prompt=prompt)
        raw_reply = response["results"][0]["generated_text"].strip()
        logger.info(f"Watsonx LLM raw response: {raw_reply}")

        # Clean the response to extract valid JSON
        cleaned_reply = clean_json_response(raw_reply)
        logger.info(f"Cleaned JSON response: {cleaned_reply}")

        try:
            invoice_data = json.loads(cleaned_reply)
            logger.info(f"Parsed invoice data before deduplication: {invoice_data}")

            # Validate that we have a proper structure
            if not isinstance(invoice_data, dict):
                raise ValueError("Response is not a JSON object")

            # Deduplicate flight entries
            if invoice_data.get("flight_details"):
                invoice_data["flight_details"] = deduplicate_flight_entries(invoice_data["flight_details"])
                # Recalculate total_amount
                try:
                    total = sum(
                        float(str(flight["total_amount"]).replace(',', '')) 
                        for flight in invoice_data["flight_details"] 
                        if flight.get("total_amount")
                    )
                    invoice_data["total_amount"] = f"{total:.2f}"
                except (ValueError, TypeError) as e:
                    logger.warning(f"Failed to recalculate total_amount: {e}")
                    invoice_data["total_amount"] = invoice_data.get("total_amount", "0.00")
            
            logger.info(f"Processed invoice data: {invoice_data}")

            # Save JSON to file
            json_dir = os.path.join("data", "uploads", "json_outputs")
            os.makedirs(json_dir, exist_ok=True)
            json_filename = f"{thread_id}_{os.path.basename(pdf_path).replace('.pdf', '')}.json"
            json_path = os.path.join(json_dir, json_filename)
            with open(json_path, 'w') as f:
                json.dump(invoice_data, f, indent=2)
            logger.info(f"Saved JSON to {json_path}")

            # Generate HTML for invoice data
            invoice_html = generate_invoice_html(invoice_data)
            state["extracted_invoice_data"] = invoice_data
            state["invoice_html"] = invoice_html
            state["followup_question"] = "Invoice processed successfully. Would you like to book another trip or check visa requirements?"
            state["needs_followup"] = True
            state["current_node"] = "invoice_extraction"

        except json.JSONDecodeError as je:
            logger.error(f"Failed to parse JSON: {je}")
            logger.error(f"Cleaned response that failed: {cleaned_reply}")
            
            # Try one more aggressive cleaning approach
            try:
                # Extract everything between the first { and last }
                match = re.search(r'\{.*\}', cleaned_reply, re.DOTALL)
                if match:
                    final_attempt = match.group(0)
                    # Remove any trailing tokens after the closing brace
                    final_attempt = re.sub(r'\}.*$', '}', final_attempt, flags=re.DOTALL)
                    invoice_data = json.loads(final_attempt)
                    logger.info("Successfully parsed JSON on second attempt")
                    
                    # Continue with the same processing as above
                    if invoice_data.get("flight_details"):
                        invoice_data["flight_details"] = deduplicate_flight_entries(invoice_data["flight_details"])
                        try:
                            total = sum(
                                float(str(flight["total_amount"]).replace(',', '')) 
                                for flight in invoice_data["flight_details"] 
                                if flight.get("total_amount")
                            )
                            invoice_data["total_amount"] = f"{total:.2f}"
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Failed to recalculate total_amount: {e}")
                    
                    # Save and generate HTML
                    json_dir = os.path.join("data", "uploads", "json_outputs")
                    os.makedirs(json_dir, exist_ok=True)
                    json_filename = f"{thread_id}_{os.path.basename(pdf_path).replace('.pdf', '')}.json"
                    json_path = os.path.join(json_dir, json_filename)
                    with open(json_path, 'w') as f:
                        json.dump(invoice_data, f, indent=2)
                    
                    invoice_html = generate_invoice_html(invoice_data)
                    state["extracted_invoice_data"] = invoice_data
                    state["invoice_html"] = invoice_html
                    state["followup_question"] = "Invoice processed successfully. Would you like to book another trip or check visa requirements?"
                    state["needs_followup"] = True
                    state["current_node"] = "invoice_extraction"
                    
                else:
                    raise json.JSONDecodeError("Could not extract valid JSON", cleaned_reply, 0)
                    
            except json.JSONDecodeError:
                logger.error(f"Complete JSON parsing failure. Raw: {raw_reply}")
                logger.error(f"Cleaned: {cleaned_reply}")
                state["extracted_invoice_data"] = None
                state["invoice_html"] = "<div class='question-response'><div class='question'><p>Failed to parse invoice data. The PDF may be corrupted or in an unsupported format.</p></div></div>"
                state["followup_question"] = "Failed to parse invoice data. Please upload a valid PDF with recognizable invoice details."
                state["needs_followup"] = True

    except Exception as e:
        logger.error(f"Error processing invoice {pdf_path}: {e}")
        state["extracted_invoice_data"] = None
        state["invoice_html"] = "<div class='question-response'><div class='question'><p>Failed to process invoice. Please try again or upload a different PDF.</p></div></div>"
        state["followup_question"] = "Failed to process invoice. Please try again or upload a different PDF."
        state["needs_followup"] = True

    return state


def generate_invoice_html(invoice_data: dict) -> str:
    """Generate HTML representation of extracted invoice data."""
    if not invoice_data:
        return "<div class='question-response'><div class='question'><p>No invoice data available.</p></div></div>"

    html = ['<div class="overflow-x-auto"><table class="table-auto w-full border-collapse border border-gray-300">']
    html.append('<thead><tr class="bg-gray-100">')
    html.append('<th class="border border-gray-300 px-4 py-2">Field</th>')
    html.append('<th class="border border-gray-300 px-4 py-2">Value</th>')
    html.append('</tr></thead><tbody>')

    fields = [
        ("Invoice Number", invoice_data.get("invoice_number")),
        ("Issued Date", invoice_data.get("issued_date")),
        ("Submission Date", invoice_data.get("submission_date")),
        ("Vendor Type", invoice_data.get("vendor_type")),
        ("Vendor Name", invoice_data.get("vendor_name")),
        ("Subsidiary Name", invoice_data.get("subsidiary_name")),
        ("Invoice State", invoice_data.get("invoice_state")),
        ("Currency", invoice_data.get("currency")),
        ("Total Amount", invoice_data.get("total_amount"))
    ]

    for field, value in fields:
        # Escape special characters in HTML
        value = str(value).replace("<", "&lt;").replace(">", "&gt;") if value else "N/A"
        html.append(f'<tr><td class="border border-gray-300 px-4 py-2">{field}</td>')
        html.append(f'<td class="border border-gray-300 px-4 py-2">{value}</td></tr>')

    if invoice_data.get("flight_details"):
        html.append('<tr><td class="border border-gray-300 px-4 py-2" colspan="2">')
        html.append('<div class="mt-4"><strong>Flight Details</strong></div>')
        html.append('<table class="table-auto w-full border-collapse border border-gray-300 mt-2">')
        html.append('<thead><tr class="bg-gray-100">')
        flight_fields = ["Airline", "Origin", "Destination", "Departure Date", "Arrival Date", "Passenger", "Ticket Number", "Amount", "Tax", "Total Amount"]
        for field in flight_fields:
            html.append(f'<th class="border border-gray-300 px-4 py-2">{field}</th>')
        html.append('</tr></thead><tbody>')

        for flight in invoice_data["flight_details"]:
            html.append('<tr>')
            flight_values = [
                flight.get("airline"),
                flight.get("origin"),
                flight.get("destination"),
                flight.get("departure_date"),
                flight.get("arrival_date"),
                flight.get("passenger"),
                flight.get("ticket_number"),
                flight.get("amount"),
                flight.get("tax"),
                flight.get("total_amount")
            ]
            for value in flight_values:
                # Escape special characters in HTML
                value = str(value).replace("<", "&lt;").replace(">", "&gt;") if value else "N/A"
                html.append(f'<td class="border border-gray-300 px-4 py-2">{value}</td>')
            html.append('</tr>')
        html.append('</tbody></table></td></tr>')

    html.append('</tbody></table></div>')
    return "".join(html)