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

    # Start HTML table with Tailwind CSS for styling
    html = """
    <div class="overflow-x-auto">
        <table class="min-w-full border-collapse border border-gray-300">
            <thead class="bg-gray-100">
                <tr>
                    <th class="border border-gray-300 px-4 py-2 text-left">Field</th>
                    <th class="border border-gray-300 px-4 py-2 text-left">Value</th>
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
                <tr>
                    <td class="border border-gray-300 px-4 py-2">{display_name}</td>
                    <td class="border border-gray-300 px-4 py-2">{format_value(invoice_data[key])}</td>
                </tr>
            """

    # Handle flight_details as a nested table
    if "flight_details" in invoice_data and invoice_data["flight_details"]:
        html += """
            <tr>
                <td class="border border-gray-300 px-4 py-2">Flight Details</td>
                <td class="border border-gray-300 px-4 py-2">
                    <table class="min-w-full border-collapse border border-gray-200">
                        <thead class="bg-gray-50">
                            <tr>
                                <th class="border border-gray-200 px-2 py-1 text-left">Airline</th>
                                <th class="border border-gray-200 px-2 py-1 text-left">Origin</th>
                                <th class="border border-gray-200 px-2 py-1 text-left">Destination</th>
                                <th class="border border-gray-200 px-2 py-1 text-left">Departure Date</th>
                                <th class="border border-gray-200 px-2 py-1 text-left">Arrival Date</th>
                                <th class="border border-gray-200 px-2 py-1 text-left">Service Type</th>
                                <th class="border border-gray-200 px-2 py-1 text-left">Passenger</th>
                                <th class="border border-gray-200 px-2 py-1 text-left">Ticket Number</th>
                                <th class="border border-gray-200 px-2 py-1 text-left">Amount</th>
                                <th class="border border-gray-200 px-2 py-1 text-left">Tax</th>
                                <th class="border border-gray-200 px-2 py-1 text-left">Total Amount</th>
                            </tr>
                        </thead>
                        <tbody>
        """
        for flight in invoice_data["flight_details"]:
            html += f"""
                <tr>
                    <td class="border border-gray-200 px-2 py-1">{format_value(flight.get('airline'))}</td>
                    <td class="border border-gray-200 px-2 py-1">{format_value(flight.get('origin'))}</td>
                    <td class="border border-gray-200 px-2 py-1">{format_value(flight.get('destination'))}</td>
                    <td class="border border-gray-200 px-2 py-1">{format_value(flight.get('departure_date'))}</td>
                    <td class="border border-gray-200 px-2 py-1">{format_value(flight.get('arrival_date'))}</td>
                    <td class="border border-gray-200 px-2 py-1">{format_value(flight.get('service_type'))}</td>
                    <td class="border border-gray-200 px-2 py-1">{format_value(flight.get('passenger'))}</td>
                    <td class="border border-gray-200 px-2 py-1">{format_value(flight.get('ticket_number'))}</td>
                    <td class="border border-gray-200 px-2 py-1">{format_value(flight.get('amount'))}</td>
                    <td class="border border-gray-200 px-2 py-1">{format_value(flight.get('tax'))}</td>
                    <td class="border border-gray-200 px-2 py-1">{format_value(flight.get('total_amount'))}</td>
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