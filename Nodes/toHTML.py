from typing import List, Optional, Any
from html import escape
from Models.ExtractedInfo import ExtractedInfo
from Utils.get_html_attributes import get_html_attributes
from Models.TravelSearchState import TravelSearchState
from typing import Any, List
from dataclasses import dataclass, field
import html


def toHTML(state: TravelSearchState) -> TravelSearchState:
    def dict_to_table(data: dict) -> str:
        rows = []
        for key, value in data.items():
            if isinstance(value, dict):
                value_html = dict_to_table(value)
            elif isinstance(value, list):
                # Convert list of dicts to nested tables or plain list
                value_html = "<table border='1'>" + "".join(
                    "<tr><td>" + dict_to_table(item) + "</td></tr>" if isinstance(item, dict)
                    else f"<tr><td>{html.escape(str(item))}</td></tr>"
                    for item in value
                ) + "</table>"
            else:
                value_html = html.escape(str(value))
            rows.append(f"<tr><td>{html.escape(str(key))}</td><td>{value_html}</td></tr>")
        return "<table border='1'>" + "".join(rows) + "</table>"

    # Convert each package to a table string
    new_state = TravelSearchState()
    new_state.travel_packages = [
        dict_to_table(pkg) if isinstance(pkg, dict) else html.escape(str(pkg))
        for pkg in state.travel_packages
    ]
    return new_state


# unused function (maybe)
def format_extracted_info_html(extracted_info: ExtractedInfo) -> str:
    """Format extracted information as HTML"""
    html = "<div class='extracted-info'><h4>Current Information:</h4><ul>"
    
    if extracted_info.departure_date:
        html += f"<li><strong>Departure Date:</strong> {extracted_info.departure_date}</li>"
    if extracted_info.origin:
        html += f"<li><strong>From:</strong> {extracted_info.origin}</li>"
    if extracted_info.destination:
        html += f"<li><strong>To:</strong> {extracted_info.destination}</li>"
    if extracted_info.cabin_class:
        html += f"<li><strong>Cabin:</strong> {extracted_info.cabin_class.title()}</li>"
    if extracted_info.duration:
        html += f"<li><strong>Duration:</strong> {extracted_info.duration} days</li>"
    
    html += "</ul></div>"
    return html