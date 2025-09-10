from typing import Dict, Any
from Models.InvoiceModels import InvoiceData

def invoice_to_html(invoice_data: Dict[str, Any]) -> str:
    """Convert InvoiceData JSON to a clean HTML table."""
    def format_value(value: Any) -> str:
        if isinstance(value, list):
            return "<br>".join(format_value(item) for item in value)
        elif isinstance(value, dict):
            return "<br>".join(f"{k}: {format_value(v)}" for k, v in value.items() if v is not None)
        return str(value) if value is not None else ""

    # Start HTML table
    html = """
    <div class="invoice-container">
        <table class="invoice-table">
            <thead class="invoice-header">
                <tr>
                    <th class="field-header">Field</th>
                    <th class="value-header">Value</th>
                </tr>
            </thead>
            <tbody>
    """

    # Define top-level fields in desired order
    fields = [
        ("Invoice Number", "invoice_number"),
        ("Issued Date", "issued_date"),
        ("Submission Date", "submission_date"),
        ("Vendor Type", "vendor_type"),
        ("Vendor Name", "vendor_name"),
        ("Subsidiary Name", "subsidiary_name"),
        ("Invoice State", "invoice_state"),
        ("Currency", "currency"),
        ("Travel Agency", "travel_agency"),
        ("Total Amount", "total_amount")
    ]

    # Add top-level fields
    for display_name, key in fields:
        if key in invoice_data and invoice_data[key] is not None:
            html += f"""
                <tr class="invoice-row">
                    <td class="field-cell">{display_name}</td>
                    <td class="value-cell">{format_value(invoice_data[key])}</td>
                </tr>
            """

    # Handle flight_details as a nested table
    if "flight_details" in invoice_data and invoice_data["flight_details"]:
        html += """
            <tr class="invoice-row">
                <td class="field-cell">Flight Details</td>
                <td class="value-cell">
                    <table class="flight-details-table">
                        <thead class="flight-header">
                            <tr>
                                <th class="flight-column">Airline</th>
                                <th class="flight-column">Origin</th>
                                <th class="flight-column">Destination</th>
                                <th class="flight-column">Departure Date</th>
                                <th class="flight-column">Arrival Date</th>
                                <th class="flight-column">Service Type</th>
                                <th class="flight-column">Passenger</th>
                                <th class="flight-column">Ticket Number</th>
                                <th class="flight-column">Amount</th>
                                <th class="flight-column">Tax</th>
                                <th class="flight-column">Total Amount</th>
                            </tr>
                        </thead>
                        <tbody>
        """
        for flight in invoice_data["flight_details"]:
            html += f"""
                <tr class="flight-row">
                    <td class="flight-cell">{format_value(flight.get('airline'))}</td>
                    <td class="flight-cell">{format_value(flight.get('origin'))}</td>
                    <td class="flight-cell">{format_value(flight.get('destination'))}</td>
                    <td class="flight-cell">{format_value(flight.get('departure_date'))}</td>
                    <td class="flight-cell">{format_value(flight.get('arrival_date'))}</td>
                    <td class="flight-cell">{format_value(flight.get('service_type'))}</td>
                    <td class="flight-cell">{format_value(flight.get('passenger'))}</td>
                    <td class="flight-cell">{format_value(flight.get('ticket_number'))}</td>
                    <td class="flight-cell">{format_value(flight.get('amount'))}</td>
                    <td class="flight-cell">{format_value(flight.get('tax'))}</td>
                    <td class="flight-cell">{format_value(flight.get('total_amount'))}</td>
                </tr>
            """
        html += """
                        </tbody>
                    </table>
                </td>
            </tr>
        """

    html += """
            </tbody>
        </table>
    </div>
    """
    return html