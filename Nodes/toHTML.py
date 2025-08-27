from typing import List, Optional, Any
from html import escape
from Models.TravelSearchState import TravelSearchState
from datetime import datetime

def toHTML(state: TravelSearchState) -> TravelSearchState:
    """Convert travel packages to clean HTML format with LLM summary."""

    travel_packages = state.get("travel_packages", [])
    package_summary = state.get("package_summary", "")

    html_content = generate_complete_html(travel_packages, package_summary)

    state["travel_packages_html"] = [html_content]
    state["complete_travel_html"] = html_content
    state["current_node"] = "to_html"

    return state

def generate_complete_html(packages: List[dict], summary: str) -> str:
    """Generate complete HTML with summary and package tables."""

    html_parts = []

    html_parts.append("""
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 20px;
            line-height: 1.6;
        }
        .travel-summary {
            border: 1px solid var(--border-color, #ddd);
            padding: 20px;
            margin-bottom: 30px;
            border-radius: 8px;
            border-left: 4px solid var(--accent-color, #007bff);
        }
        .package-container {
            margin-bottom: 30px;
            border: 1px solid var(--border-color, #ddd);
            border-radius: 8px;
            overflow: hidden;
        }
        .package-header {
            background: linear-gradient(135deg, var(--header-bg, #f8f9fa), var(--header-bg-alt, #e9ecef));
            padding: 15px 20px;
            font-size: 18px;
            font-weight: 600;
            border-bottom: 1px solid var(--border-color, #ddd);
        }
        .package-content { padding: 25px; }
        .data-table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 25px;
            border: 1px solid var(--border-color, #ddd);
            border-radius: 6px;
            overflow: hidden;
        }
        .data-table th {
            background: var(--table-header-bg, #f8f9fa);
            padding: 12px 15px;
            text-align: left;
            font-weight: 600;
            border-bottom: 2px solid var(--border-color, #ddd);
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .data-table td {
            padding: 12px 15px;
            border-bottom: 1px solid var(--border-light, #eee);
            vertical-align: top;
        }
        .data-table tr:nth-child(even) {
            background: var(--table-row-alt, #f9f9f9);
        }
        .data-table tr:hover {
            background: var(--table-row-hover, #f0f0f0);
        }
        .price-cell {
            font-weight: bold;
            font-size: 16px;
        }
        .section-title {
            font-size: 18px;
            font-weight: 600;
            margin: 25px 0 15px 0;
            padding-bottom: 8px;
            border-bottom: 2px solid var(--accent-color, #007bff);
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .no-packages {
            text-align: center;
            padding: 40px;
            font-style: italic;
            font-size: 16px;
        }
        .status-badge {
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 500;
            text-transform: uppercase;
        }
        .available {
            background: var(--success-bg, #d4edda);
            color: var(--success-text, #155724);
        }
        .route-info {
            font-family: monospace;
            font-weight: 500;
            font-size: 14px;
        }
        .duration-info {
            font-size: 13px;
            opacity: 0.8;
        }
        .hotel-name {
            font-weight: 600;
            margin-bottom: 4px;
        }
        .room-description {
            font-size: 13px;
            opacity: 0.8;
            line-height: 1.4;
        }
    </style>
    """)

    if summary:
        html_parts.append(f"""
        <div class="travel-summary">
            <div class="section-title">🌟 Your Travel Recommendations</div>
            <div>{escape(summary).replace(chr(10), '<br>')}</div>
        </div>
        """)

    if not packages:
        html_parts.append('<div class="no-packages">No travel packages available.</div>')
    else:
        for i, package in enumerate(packages, 1):
            if package:
                html_parts.append(generate_package_html(package, i))

    return "".join(html_parts)

def generate_package_html(package: dict, package_num: int) -> str:
    """Generate HTML for a single travel package."""

    package_id = package.get("package_id", package_num)
    travel_dates = package.get("travel_dates", {})
    flight_offers = package.get("flight_offers", [])
    hotel_info = package.get("hotels", {})
    pricing = package.get("pricing", {})

    duration = travel_dates.get("duration_nights", "N/A")
    checkin = travel_dates.get("checkin", "N/A")
    checkout = travel_dates.get("checkout", "N/A")

    html_parts = [f"""
    <div class="package-container">
        <div class="package-header">
            📦 Package {package_id} - {duration} Night{'s' if duration != 1 else ''}
            ({checkin} to {checkout})
        </div>
        <div class="package-content">
    """]

    html_parts.append(generate_pricing_table(pricing))
    html_parts.append(generate_flight_offers_table(flight_offers))
    html_parts.append(generate_hotel_table(hotel_info))

    html_parts.append("</div></div>")

    return "".join(html_parts)

def generate_pricing_table(pricing: dict) -> str:
    """Generate pricing summary table."""

    total_price = pricing.get("total_min_price", 0)
    currency = pricing.get("currency", "")
    flight_price = pricing.get("flight_price", 0)
    hotel_price = pricing.get("min_hotel_price", 0)

    return f"""
    <div class="section-title">💰 Pricing Summary</div>
    <table class="data-table">
        <thead>
            <tr>
                <th>Component</th>
                <th>Price</th>
                <th>Currency</th>
                <th>Notes</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><strong>Total Package</strong></td>
                <td class="price-cell">{total_price:,.2f}</td>
                <td>{currency}</td>
                <td>Flight only (hotels separate)</td>
            </tr>
            <tr>
                <td>Flight</td>
                <td class="price-cell">{flight_price:,.2f}</td>
                <td>{currency}</td>
                <td>Cheapest round trip</td>
            </tr>
            <tr>
                <td>Hotel (Starting from)</td>
                <td class="price-cell">{hotel_price:,.2f}</td>
                <td>{currency}</td>
                <td>Per stay, varies by selection</td>
            </tr>
        </tbody>
    </table>
    """

def generate_flight_offers_table(flight_offers: List[dict]) -> str:
    """Generate table for all flight offers."""

    html_parts = [f'<div class="section-title">✈️ Flight Offers</div>']

    if not flight_offers:
        return '<div class="section-title">✈️ Flight Offers</div><p>No flight information available.</p>'

    html_parts.append(f"""
    <table class="data-table">
        <thead>
            <tr>
                <th>Flight</th>
                <th>Route</th>
                <th>Departure</th>
                <th>Arrival</th>
                <th>Duration</th>
                <th>Stops</th>
                <th>Price</th>
                <th>Currency</th>
            </tr>
        </thead>
        <tbody>
    """)

    for flight_info in flight_offers:
        summary = flight_info.get("summary", {})
        price = flight_info.get("price", 0)
        currency = flight_info.get("currency", "")

        outbound = summary.get("outbound")
        if outbound:
            departure = outbound.get("departure", {})
            arrival = outbound.get("arrival", {})
            duration = outbound.get("duration", "N/A")
            stops = outbound.get("stops", 0)

            dep_time = format_datetime(departure.get("time", ""))
            arr_time = format_datetime(arrival.get("time", ""))
            route = f"{departure.get('airport', 'N/A')} → {arrival.get('airport', 'N/A')}"

            html_parts.append(f"""
            <tr>
                <td><strong>Outbound</strong><br><span class="duration-info">{dep_time}</span></td>
                <td class="route-info">{route}</td>
                <td>Terminal {departure.get('terminal', 'N/A')}<br>{dep_time}</td>
                <td>Terminal {arrival.get('terminal', 'N/A')}<br>{arr_time}</td>
                <td>{duration}</td>
                <td>{"Direct" if stops == 0 else f"{stops} stop{'s' if stops != 1 else ''}"}</td>
                <td rowspan="2" class="price-cell">{price:,.2f}</td>
                <td rowspan="2">{currency}</td>
            </tr>
            """)

        return_flight = summary.get("return")
        if return_flight:
            departure = return_flight.get("departure", {})
            arrival = return_flight.get("arrival", {})
            duration = return_flight.get("duration", "N/A")
            stops = return_flight.get("stops", 0)

            dep_time = format_datetime(departure.get("time", ""))
            arr_time = format_datetime(arrival.get("time", ""))
            route = f"{departure.get('airport', 'N/A')} → {arrival.get('airport', 'N/A')}"

            html_parts.append(f"""
            <tr>
                <td><strong>Return</strong><br><span class="duration-info">{dep_time}</span></td>
                <td class="route-info">{route}</td>
                <td>Terminal {departure.get('terminal', 'N/A')}<br>{dep_time}</td>
                <td>Terminal {arrival.get('terminal', 'N/A')}<br>{arr_time}</td>
                <td>{duration}</td>
                <td>{"Direct" if stops == 0 else f"{stops} stop{'s' if stops != 1 else ''}"}</td>
            </tr>
            """)

    html_parts.append("</tbody></table>")

    return "".join(html_parts)

def generate_hotel_table(hotel_info: dict) -> str:
    """Generate separate tables for API and company hotel options."""

    html_parts = [f'<div class="section-title">🏨 Hotel Options</div>']

    if not hotel_info:
        return '<div class="section-title">🏨 Hotel Options</div><p>No hotel information available.</p>'

    api_hotels = hotel_info.get("api_hotels", {})
    company_hotels = hotel_info.get("company_hotels", {})

    html_parts.append(f"""
    <div class="section-title">🌐 API Hotel Options</div>
    <table class="data-table">
        <thead>
            <tr>
                <th>Hotel Name</th>
                <th>Room Type & Description</th>
                <th>Price per Stay</th>
                <th>Currency</th>
                <th>Availability</th>
            </tr>
        </thead>
        <tbody>
    """)

    if api_hotels.get("total_found", 0) == 0:
        html_parts.append('<tr><td colspan="5">No API hotels available</td></tr>')
    else:
        for i, hotel in enumerate(api_hotels.get("top_options", [])[:5], 1):
            hotel_data = hotel.get("hotel", {})
            best_offers = hotel.get("best_offers", [])
            is_available = hotel.get("available", True)

            hotel_name = hotel_data.get("name", f"Hotel {i}")

            if best_offers:
                best_offer = best_offers[0]
                room_type = best_offer.get("room_type", "Standard Room")
                room_description = best_offer.get("description", "Standard accommodation")
                offer_price = float(best_offer.get("offer", {}).get("price", {}).get("total", 0))
                currency = best_offer.get("currency", "")

                if len(room_description) > 100:
                    room_description = room_description[:97] + "..."

                availability_badge = '<span class="status-badge available">Available</span>' if is_available else '<span class="status-badge">Not Available</span>'

                html_parts.append(f"""
                <tr>
                    <td><div class="hotel-name">{escape(hotel_name)}</div></td>
                    <td>
                        <div><strong>{escape(room_type)}</strong></div>
                        <div class="room-description">{escape(room_description)}</div>
                    </td>
                    <td class="price-cell">{offer_price:,.2f}</td>
                    <td>{currency}</td>
                    <td>{availability_badge}</td>
                </tr>
                """)
            else:
                html_parts.append(f"""
                <tr>
                    <td><div class="hotel-name">{escape(hotel_name)}</div></td>
                    <td>No room details available</td>
                    <td>-</td>
                    <td>-</td>
                    <td><span class="status-badge">No Offers</span></td>
                </tr>
                """)

    html_parts.append('</tbody></table>')

    html_parts.append(f"""
    <div class="section-title">🤝 Company Preferred Hotels</div>
    <table class="data-table">
        <thead>
            <tr>
                <th>Hotel Name</th>
                <th>Room Type</th>
                <th>Price per Stay</th>
                <th>Currency</th>
                <th>Contacts</th>
                <th>Notes</th>
                <th>Availability</th>
            </tr>
        </thead>
        <tbody>
    """)

    if company_hotels.get("total_found", 0) == 0:
        html_parts.append('<tr><td colspan="7">No company preferred hotels available</td></tr>')
    else:
        for i, hotel in enumerate(company_hotels.get("top_options", [])[:5], 1):
            hotel_data = hotel.get("hotel", {})
            best_offers = hotel.get("best_offers", [])
            is_available = hotel.get("available", True)

            hotel_name = hotel_data.get("name", f"Hotel {i}")

            if best_offers:
                best_offer = best_offers[0]
                room_type = best_offer.get("room_type", "Standard Room")
                offer_price = float(best_offer.get("offer", {}).get("price", {}).get("total", 0))
                currency = best_offer.get("currency", "")
                contacts = best_offer.get("contacts", "N/A")
                notes = best_offer.get("notes", "None")

                availability_badge = '<span class="status-badge available">Available</span>' if is_available else '<span class="status-badge">Not Available</span>'

                html_parts.append(f"""
                <tr>
                    <td><div class="hotel-name">{escape(hotel_name)}</div></td>
                    <td><strong>{escape(room_type)}</strong></td>
                    <td class="price-cell">{offer_price:,.2f}</td>
                    <td>{currency}</td>
                    <td>{escape(contacts)}</td>
                    <td>{escape(notes)}</td>
                    <td>{availability_badge}</td>
                </tr>
                """)
            else:
                html_parts.append(f"""
                <tr>
                    <td><div class="hotel-name">{escape(hotel_name)}</div></td>
                    <td>No room details</td>
                    <td>-</td>
                    <td>-</td>
                    <td>{escape(hotel.get("contacts", "N/A"))}</td>
                    <td>{escape(hotel.get("notes", "None"))}</td>
                    <td><span class="status-badge">No Offers</span></td>
                </tr>
                """)

    html_parts.append('</tbody></table>')

    return "".join(html_parts)

def format_datetime(datetime_str: str) -> str:
    """Format datetime string for display."""
    if not datetime_str:
        return "N/A"

    try:
        if "T" in datetime_str:
            dt = datetime.fromisoformat(datetime_str.replace("Z", "+00:00"))
            return dt.strftime("%b %d, %Y %H:%M")
        else:
            return datetime_str
    except:
        return datetime_str
