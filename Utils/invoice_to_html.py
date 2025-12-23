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

    # Inline styles (safe from Tailwind purge) for immediate correct rendering
    container_style = (
        "font-family: Inter, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial;"
        " color: #111827; padding: 0.5rem;"
    )
    table_style = "width:100%; border-collapse:collapse;"
    th_style = "text-align:left; padding:0.5rem 0.75rem; font-weight:600; color:#111827;"
    td_style = "padding:0.5rem 0.75rem; vertical-align:top; color:#374151;"
    small_muted = "color:#6b7280; font-size:0.9rem;"

    # Start HTML table with inline styles added
    html = f"""
    <div class="invoice-container" style="{container_style}">
        <table class="invoice-table" style="{table_style}">
            <thead class="invoice-header">
                <tr>
                    <th class="field-header" style="{th_style} width:30%;">Field</th>
                    <th class="value-header" style="{th_style} width:70%;">Value</th>
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
                    <td class="field-cell" style="{td_style}; font-weight:600;">{display_name}</td>
                    <td class="value-cell" style="{td_style};">{format_value(invoice_data[key])}</td>
                </tr>
            """

    # Handle flight_details as a nested table
    if "flight_details" in invoice_data and invoice_data["flight_details"]:
        html += f"""
            <tr class="invoice-row">
                <td class="field-cell" style="{td_style}; font-weight:600;">Flight Details</td>
                <td class="value-cell" style="{td_style};">
                    <table class="flight-details-table" style="width:100%; border-collapse:collapse;">
                        <thead class="flight-header">
                            <tr>
                                <th class="flight-column" style="{th_style}">Airline</th>
                                <th class="flight-column" style="{th_style}">Origin</th>
                                <th class="flight-column" style="{th_style}">Destination</th>
                                <th class="flight-column" style="{th_style}">Departure Date</th>
                                <th class="flight-column" style="{th_style}">Arrival Date</th>
                                <th class="flight-column" style="{th_style}">Service Type</th>
                                <th class="flight-column" style="{th_style}">Passenger</th>
                                <th class="flight-column" style="{th_style}">Ticket Number</th>
                                <th class="flight-column" style="{th_style}">Amount</th>
                                <th class="flight-column" style="{th_style}">Tax</th>
                                <th class="flight-column" style="{th_style}">Total Amount</th>
                            </tr>
                        </thead>
                        <tbody>
        """
        for flight in invoice_data["flight_details"]:
            html += f"""
                <tr class="flight-row">
                    <td class="flight-cell" style="{td_style};">{format_value(flight.get('airline'))}</td>
                    <td class="flight-cell" style="{td_style};">{format_value(flight.get('origin'))}</td>
                    <td class="flight-cell" style="{td_style};">{format_value(flight.get('destination'))}</td>
                    <td class="flight-cell" style="{td_style};">{format_value(flight.get('departure_date'))}</td>
                    <td class="flight-cell" style="{td_style};">{format_value(flight.get('arrival_date'))}</td>
                    <td class="flight-cell" style="{td_style};">{format_value(flight.get('service_type'))}</td>
                    <td class="flight-cell" style="{td_style};">{format_value(flight.get('passenger'))}</td>
                    <td class="flight-cell" style="{td_style};">{format_value(flight.get('ticket_number'))}</td>
                    <td class="flight-cell" style="{td_style};">{format_value(flight.get('amount'))}</td>
                    <td class="flight-cell" style="{td_style};">{format_value(flight.get('tax'))}</td>
                    <td class="flight-cell" style="{td_style};">{format_value(flight.get('total_amount'))}</td>
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