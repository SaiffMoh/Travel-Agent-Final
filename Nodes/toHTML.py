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
                value_html = "<table border='1'>" + "".join(
                    "<tr><td>" + dict_to_table(item) + "</td></tr>" if isinstance(item, dict)
                    else f"<tr><td>{html.escape(str(item))}</td></tr>"
                    for item in value
                ) + "</table>"
            else:
                value_html = html.escape(str(value))
            rows.append(f"<tr><td>{html.escape(str(key))}</td><td>{value_html}</td></tr>")
        return "<table border='1'>" + "".join(rows) + "</table>"

    # Render packages to HTML string list
    travel_packages = state.get("travel_packages", [])
    try:
        print(f"toHTML: received {len(travel_packages)} packages")
    except Exception as _:
        print("toHTML: unable to determine package count")
    html_packages = [
        dict_to_table(pkg) if isinstance(pkg, dict) else html.escape(str(pkg))
        for pkg in travel_packages
    ]
    print(f"toHTML: built {len(html_packages)} html snippets")

    # Attach HTML to state and continue
    state["travel_packages_html"] = html_packages
    state["current_node"] = "to_html"
    return state


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