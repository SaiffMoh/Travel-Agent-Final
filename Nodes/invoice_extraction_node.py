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

def generate_invoice_html(invoice_data: dict) -> str:
    """Generate clean HTML representation of extracted invoice data - ONLY HTML OUTPUT."""
    if not invoice_data:
        return """
        <div class="p-4 bg-red-50 border border-red-200 rounded-lg">
            <p class="text-red-600">No invoice data available.</p>
        </div>
        """

    def format_value(value) -> str:
        """Format value for HTML display."""
        if value is None:
            return "N/A"
        return str(value).replace("<", "&lt;").replace(">", "&gt;")

    # Start with a clean, responsive HTML structure
    html = ['<div class="w-full max-w-6xl mx-auto p-4">']
    
    # Invoice header
    html.append('<div class="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">')
    html.append('<h2 class="text-xl font-bold text-blue-800 mb-3">Invoice Details</h2>')
    html.append('<div class="grid grid-cols-1 md:grid-cols-2 gap-4">')
    
    # Basic invoice information
    basic_fields = [
        ("Invoice Number", "invoice_number"),
        ("Issued Date", "issued_date"),
        ("Submission Date", "submission_date"),
        ("Vendor Name", "vendor_name"),
        ("Travel Agency", "travel_agency"),
        ("Currency", "currency"),
        ("Total Amount", "total_amount")
    ]
    
    for display_name, key in basic_fields:
        value = invoice_data.get(key)
        if value:
            html.append(f'<div class="bg-white p-3 rounded border">')
            html.append(f'<span class="font-semibold text-gray-700">{display_name}:</span>')
            html.append(f'<span class="ml-2 text-gray-900">{format_value(value)}</span>')
            html.append('</div>')
    
    html.append('</div></div>')

    # Flight details section
    if invoice_data.get("flight_details"):
        html.append('<div class="bg-white border border-gray-200 rounded-lg overflow-hidden">')
        html.append('<div class="bg-gray-50 px-4 py-3 border-b border-gray-200">')
        html.append('<h3 class="text-lg font-semibold text-gray-800">Flight Details</h3>')
        html.append('</div>')
        
        # Responsive table
        html.append('<div class="overflow-x-auto">')
        html.append('<table class="w-full">')
        html.append('<thead class="bg-gray-100">')
        html.append('<tr>')
        
        flight_headers = [
            "Airline", "Origin", "Destination", "Departure", "Arrival", 
            "Passenger", "Ticket #", "Service", "Amount", "Tax", "Total"
        ]
        
        for header in flight_headers:
            html.append(f'<th class="px-3 py-2 text-left text-xs font-medium text-gray-700 uppercase tracking-wider border-b border-gray-200">{header}</th>')
        
        html.append('</tr></thead><tbody>')

        for i, flight in enumerate(invoice_data["flight_details"]):
            row_class = "bg-gray-50" if i % 2 else "bg-white"
            html.append(f'<tr class="{row_class}">')
            
            flight_values = [
                flight.get("airline"),
                flight.get("origin"),
                flight.get("destination"),
                flight.get("departure_date"),
                flight.get("arrival_date"),
                flight.get("passenger"),
                flight.get("ticket_number"),
                flight.get("service_type"),
                flight.get("amount"),
                flight.get("tax"),
                flight.get("total_amount")
            ]
            
            for value in flight_values:
                html.append(f'<td class="px-3 py-2 text-sm text-gray-900 border-b border-gray-200">{format_value(value)}</td>')
            
            html.append('</tr>')
        
        html.append('</tbody></table>')
        html.append('</div></div>')

    html.append('</div>')
    return "".join(html)

def invoice_extraction_node(state: TravelSearchState) -> TravelSearchState:
    """Extract structured data from uploaded invoice PDF using Watsonx LLM."""
    pdf_path = state.get("invoice_pdf_path")
    thread_id = state.get("thread_id")
    
    if not pdf_path or not os.path.exists(pdf_path):
        logger.error(f"PDF path not found or invalid: {pdf_path}")
        state["extracted_invoice_data"] = None
        state["invoice_html"] = """
        <div class="p-4 bg-red-50 border border-red-200 rounded-lg">
            <p class="text-red-600">No PDF file found. Please upload a valid invoice.</p>
        </div>
        """
        state["followup_question"] = "No PDF file found. Please upload a valid invoice."
        state["needs_followup"] = True
        return state

    try:
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

        # Invoke Watsonx LLM
        response = llm.generate(prompt=prompt)
        raw_reply = response["results"][0]["generated_text"].strip()
        logger.info(f"Watsonx LLM raw response: {raw_reply}")

        # Clean and parse JSON
        cleaned_reply = clean_json_response(raw_reply)
        logger.info(f"Cleaned JSON response: {cleaned_reply}")

        try:
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

            # Save JSON to file for record keeping
            json_dir = os.path.join("data", "uploads", "json_outputs")
            os.makedirs(json_dir, exist_ok=True)
            json_filename = f"{thread_id}_{os.path.basename(pdf_path).replace('.pdf', '')}.json"
            json_path = os.path.join(json_dir, json_filename)
            with open(json_path, 'w') as f:
                json.dump(invoice_data, f, indent=2)

            # Generate HTML - THIS IS THE ONLY OUTPUT WE NEED
            invoice_html = generate_invoice_html(invoice_data)
            
            # Store in state but only return HTML
            state["extracted_invoice_data"] = invoice_data  # For internal use only
            state["invoice_html"] = invoice_html  # This is what gets returned
            state["followup_question"] = "Invoice processed successfully. Would you like to book another trip or check visa requirements?"
            state["needs_followup"] = True
            state["current_node"] = "invoice_extraction"

        except json.JSONDecodeError as je:
            logger.error(f"Failed to parse JSON: {je}")
            
            # Try aggressive cleaning
            try:
                match = re.search(r'\{.*\}', cleaned_reply, re.DOTALL)
                if match:
                    final_attempt = match.group(0)
                    final_attempt = re.sub(r'\}.*$', '}', final_attempt, flags=re.DOTALL)
                    invoice_data = json.loads(final_attempt)
                    
                    # Process successfully parsed data
                    if invoice_data.get("flight_details"):
                        invoice_data["flight_details"] = deduplicate_flight_entries(invoice_data["flight_details"])
                        try:
                            total = sum(
                                float(str(flight["total_amount"]).replace(',', '')) 
                                for flight in invoice_data["flight_details"] 
                                if flight.get("total_amount")
                            )
                            invoice_data["total_amount"] = f"{total:.2f}"
                        except (ValueError, TypeError):
                            pass
                    
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
                    state["followup_question"] = "Invoice processed successfully."
                    state["needs_followup"] = True
                    state["current_node"] = "invoice_extraction"
                else:
                    raise json.JSONDecodeError("Could not extract valid JSON", cleaned_reply, 0)
                    
            except json.JSONDecodeError:
                logger.error(f"Complete JSON parsing failure")
                state["extracted_invoice_data"] = None
                state["invoice_html"] = """
                <div class="p-4 bg-red-50 border border-red-200 rounded-lg">
                    <p class="text-red-600">Failed to parse invoice data. The PDF may be corrupted or in an unsupported format.</p>
                </div>
                """
                state["followup_question"] = "Failed to parse invoice data. Please upload a valid PDF."
                state["needs_followup"] = True

    except Exception as e:
        logger.error(f"Error processing invoice {pdf_path}: {e}")
        state["extracted_invoice_data"] = None
        state["invoice_html"] = """
        <div class="p-4 bg-red-50 border border-red-200 rounded-lg">
            <p class="text-red-600">Failed to process invoice. Please try again or upload a different PDF.</p>
        </div>
        """
        state["followup_question"] = "Failed to process invoice. Please try again."
        state["needs_followup"] = True

    return state

# === NODES.PY ===
# This goes in your nodes.py file

import json
import os
import re
from typing import Dict, List
import pdfplumber
from Models.TravelSearchState import TravelSearchState
from Utils.watson_config import llm
import logging

def clean_json_response(response: str) -> str:
    """Clean the LLM response to extract valid JSON."""
    response = response.strip()
    
    # Remove common LLM artifacts
    response = re.sub(r'<\|eom_id\|>.*', '' , response, flags=re.DOTALL)
    response = re.sub(r'<\|end\|>.*', '' , response, flags=re.DOTALL)
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
                logging.warning(f"Failed to sum amounts for duplicate entry {key}: {e}")
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

def generate_invoice_html(invoice_data: dict) -> str:
    """Generate clean HTML representation of extracted invoice data - ONLY HTML OUTPUT."""
    if not invoice_data:
        return """
        <div class="p-4 bg-red-50 border border-red-200 rounded-lg">
            <p class="text-red-600">No invoice data available.</p>
        </div>
        """

    def format_value(value) -> str:
        """Format value for HTML display."""
        if value is None:
            return "N/A"
        return str(value).replace("<", "&lt;").replace(">", "&gt;")

    # Start with a clean, responsive HTML structure
    html = ['<div class="w-full max-w-6xl mx-auto p-4">']
    
    # Invoice header
    html.append('<div class="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">')
    html.append('<h2 class="text-xl font-bold text-blue-800 mb-3">Invoice Details</h2>')
    html.append('<div class="grid grid-cols-1 md:grid-cols-2 gap-4">')
    
    # Basic invoice information
    basic_fields = [
        ("Invoice Number", "invoice_number"),
        ("Issued Date", "issued_date"),
        ("Submission Date", "submission_date"),
        ("Vendor Name", "vendor_name"),
        ("Travel Agency", "travel_agency"),
        ("Currency", "currency"),
        ("Total Amount", "total_amount")
    ]
    
    for display_name, key in basic_fields:
        value = invoice_data.get(key)
        if value:
            html.append(f'<div class="bg-white p-3 rounded border">')
            html.append(f'<span class="font-semibold text-gray-700">{display_name}:</span>')
            html.append(f'<span class="ml-2 text-gray-900">{format_value(value)}</span>')
            html.append('</div>')
    
    html.append('</div></div>')

    # Flight details section
    if invoice_data.get("flight_details"):
        html.append('<div class="bg-white border border-gray-200 rounded-lg overflow-hidden">')
        html.append('<div class="bg-gray-50 px-4 py-3 border-b border-gray-200">')
        html.append('<h3 class="text-lg font-semibold text-gray-800">Flight Details</h3>')
        html.append('</div>')
        
        # Responsive table
        html.append('<div class="overflow-x-auto">')
        html.append('<table class="w-full">')
        html.append('<thead class="bg-gray-100">')
        html.append('<tr>')
        
        flight_headers = [
            "Airline", "Origin", "Destination", "Departure", "Arrival", 
            "Passenger", "Ticket #", "Service", "Amount", "Tax", "Total"
        ]
        
        for header in flight_headers:
            html.append(f'<th class="px-3 py-2 text-left text-xs font-medium text-gray-700 uppercase tracking-wider border-b border-gray-200">{header}</th>')
        
        html.append('</tr></thead><tbody>')

        for i, flight in enumerate(invoice_data["flight_details"]):
            row_class = "bg-gray-50" if i % 2 else "bg-white"
            html.append(f'<tr class="{row_class}">')
            
            flight_values = [
                flight.get("airline"),
                flight.get("origin"),
                flight.get("destination"),
                flight.get("departure_date"),
                flight.get("arrival_date"),
                flight.get("passenger"),
                flight.get("ticket_number"),
                flight.get("service_type"),
                flight.get("amount"),
                flight.get("tax"),
                flight.get("total_amount")
            ]
            
            for value in flight_values:
                html.append(f'<td class="px-3 py-2 text-sm text-gray-900 border-b border-gray-200">{format_value(value)}</td>')
            
            html.append('</tr>')
        
        html.append('</tbody></table>')
        html.append('</div></div>')

    html.append('</div>')
    return "".join(html)

def invoice_extraction_node(state: TravelSearchState) -> TravelSearchState:
    """Extract structured data from uploaded invoice PDF using Watsonx LLM."""
    pdf_path = state.get("invoice_pdf_path")
    thread_id = state.get("thread_id")
    
    if not pdf_path or not os.path.exists(pdf_path):
        logging.error(f"PDF path not found or invalid: {pdf_path}")
        state["extracted_invoice_data"] = None
        state["invoice_html"] = """
        <div class="p-4 bg-red-50 border border-red-200 rounded-lg">
            <p class="text-red-600">No PDF file found. Please upload a valid invoice.</p>
        </div>
        """
        state["followup_question"] = "No PDF file found. Please upload a valid invoice."
        state["needs_followup"] = True
        return state

    try:
        # Extract text from PDF
        with pdfplumber.open(pdf_path) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        logging.info(f"Extracted text from {pdf_path}: {text[:500]}...")

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

        # Invoke Watsonx LLM
        response = llm.generate(prompt=prompt)
        raw_reply = response["results"][0]["generated_text"].strip()
        logging.info(f"Watsonx LLM raw response: {raw_reply}")

        # Clean and parse JSON
        cleaned_reply = clean_json_response(raw_reply)
        logging.info(f"Cleaned JSON response: {cleaned_reply}")

        try:
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
                    logging.warning(f"Failed to recalculate total_amount: {e}")

            # Save JSON to file for record keeping
            json_dir = os.path.join("data", "uploads", "json_outputs")
            os.makedirs(json_dir, exist_ok=True)
            json_filename = f"{thread_id}_{os.path.basename(pdf_path).replace('.pdf', '')}.json"
            json_path = os.path.join(json_dir, json_filename)
            with open(json_path, 'w') as f:
                json.dump(invoice_data, f, indent=2)

            # Generate HTML - THIS IS THE ONLY OUTPUT WE NEED
            invoice_html = generate_invoice_html(invoice_data)
            
            # Store in state but only return HTML
            state["extracted_invoice_data"] = invoice_data  # For internal use only
            state["invoice_html"] = invoice_html  # This is what gets returned
            state["followup_question"] = "Invoice processed successfully. Would you like to book another trip or check visa requirements?"
            state["needs_followup"] = True
            state["current_node"] = "invoice_extraction"

        except json.JSONDecodeError as je:
            logging.error(f"Failed to parse JSON: {je}")
            
            # Try aggressive cleaning
            try:
                match = re.search(r'\{.*\}', cleaned_reply, re.DOTALL)
                if match:
                    final_attempt = match.group(0)
                    final_attempt = re.sub(r'\}.*', '}', final_attempt, flags=re.DOTALL)
                    invoice_data = json.loads(final_attempt)
                    
                    # Process successfully parsed data
                    if invoice_data.get("flight_details"):
                        invoice_data["flight_details"] = deduplicate_flight_entries(invoice_data["flight_details"])
                        try:
                            total = sum(
                                float(str(flight["total_amount"]).replace(',', '')) 
                                for flight in invoice_data["flight_details"] 
                                if flight.get("total_amount")
                            )
                            invoice_data["total_amount"] = f"{total:.2f}"
                        except (ValueError, TypeError):
                            pass
                    
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
                    state["followup_question"] = "Invoice processed successfully."
                    state["needs_followup"] = True
                    state["current_node"] = "invoice_extraction"
                else:
                    raise json.JSONDecodeError("Could not extract valid JSON", cleaned_reply, 0)
                    
            except json.JSONDecodeError:
                logging.error(f"Complete JSON parsing failure")
                state["extracted_invoice_data"] = None
                state["invoice_html"] = """
                <div class="p-4 bg-red-50 border border-red-200 rounded-lg">
                    <p class="text-red-600">Failed to parse invoice data. The PDF may be corrupted or in an unsupported format.</p>
                </div>
                """
                state["followup_question"] = "Failed to parse invoice data. Please upload a valid PDF."
                state["needs_followup"] = True

    except Exception as e:
        logging.error(f"Error processing invoice {pdf_path}: {e}")
        state["extracted_invoice_data"] = None
        state["invoice_html"] = """
        <div class="p-4 bg-red-50 border border-red-200 rounded-lg">
            <p class="text-red-600">Failed to process invoice. Please try again or upload a different PDF.</p>
        </div>
        """
        state["followup_question"] = "Failed to process invoice. Please try again."
        state["needs_followup"] = True

    return state