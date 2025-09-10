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
        .currency-note {
            background: #fff3cd;
            color: #856404;
            padding: 10px;
            border-radius: 4px;
            font-size: 14px;
            border: 1px solid #ffeaa7;
            margin-bottom: 15px;
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
    """Generate pricing summary table with separate currencies."""

    flight_price = pricing.get("flight_price", 0)
    flight_currency = pricing.get("flight_currency", "")
    hotel_price = pricing.get("min_hotel_price", 0)
    hotel_currency = pricing.get("hotel_currency", "N/A")

    return f"""
    <div class="section-title">💰 Pricing Summary</div>
    <div class="currency-note">
        ⚠️ Note: Flight and hotel prices are in different currencies and cannot be combined directly.
    </div>
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
                <td><strong>Flight (Round Trip)</strong></td>
                <td class="price-cell">{flight_price:,.2f}</td>
                <td>{flight_currency}</td>
                <td>Complete round trip airfare</td>
            </tr>
            <tr>
                <td><strong>Hotel (Starting from)</strong></td>
                <td class="price-cell">{hotel_price:,.2f}</td>
                <td>{hotel_currency}</td>
                <td>Per stay, varies by selection</td>
            </tr>
        </tbody>
    </table>
    """

def generate_flight_offers_table(flight_offers: List[dict]) -> str:
    """Generate table for all flight offers with enhanced details."""

    html_parts = [f'<div class="section-title">✈️ Flight Offers</div>']

    if not flight_offers:
        return '<div class="section-title">✈️ Flight Offers</div><p>No flight information available.</p>'

    for flight_idx, flight_info in enumerate(flight_offers):
        summary = flight_info.get("summary", {})
        price = flight_info.get("price", 0)
        currency = flight_info.get("currency", "")
        bookable_seats = summary.get("numberOfBookableSeats", 0)

        html_parts.append(f"""
        <div class="flight-offer" style="margin-bottom: 25px; border: 1px solid #ddd; border-radius: 8px; padding: 20px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                <h4>Flight Option {flight_idx + 1}</h4>
                <div style="text-align: right;">
                    <div class="price-cell">{price:,.2f} {currency}</div>
                    <div style="font-size: 12px; color: #666;">Available Seats: {bookable_seats}</div>
                </div>
            </div>

            <table class="data-table">
                <thead>
                    <tr>
                        <th>Direction</th>
                        <th>Flight Details</th>
                        <th>Route</th>
                        <th>Departure</th>
                        <th>Arrival</th>
                        <th>Aircraft</th>
                        <th>Duration</th>
                    </tr>
                </thead>
                <tbody>
        """)

        # Outbound flights
        outbound = summary.get("outbound")
        if outbound:
            flight_details = outbound.get("flight_details", [])
            
            for seg_idx, flight_detail in enumerate(flight_details):
                carrier_code = flight_detail.get("carrierCode", "")
                flight_number = flight_detail.get("number", "")
                aircraft_code = flight_detail.get("aircraft", {}).get("code", "")
                operating_carrier = flight_detail.get("operating", {}).get("carrierCode", "")
                
                departure = flight_detail.get("departure", {})
                arrival = flight_detail.get("arrival", {})
                duration = flight_detail.get("duration", "")
                
                dep_time = format_datetime(departure.get("time", ""))
                arr_time = format_datetime(arrival.get("time", ""))
                route = f"{departure.get('airport', 'N/A')} → {arrival.get('airport', 'N/A')}"
                
                direction_label = f"Outbound" if seg_idx == 0 else f"Outbound (Seg {seg_idx + 1})"
                
                # Flight details display
                flight_info_display = f"{carrier_code} {flight_number}"
                if operating_carrier and operating_carrier != carrier_code:
                    flight_info_display += f" (operated by {operating_carrier})"
                
                aircraft_display = aircraft_code if aircraft_code else "N/A"
                
                html_parts.append(f"""
                <tr>
                    <td><strong>{direction_label}</strong></td>
                    <td>
                        <div style="font-weight: 600;">{flight_info_display}</div>
                        <div style="font-size: 12px; color: #666;">Carrier: {carrier_code}</div>
                    </td>
                    <td class="route-info">{route}</td>
                    <td>
                        <div>{dep_time}</div>
                        <div style="font-size: 12px; color: #666;">Terminal {departure.get('terminal', 'N/A')}</div>
                    </td>
                    <td>
                        <div>{arr_time}</div>
                        <div style="font-size: 12px; color: #666;">Terminal {arrival.get('terminal', 'N/A')}</div>
                    </td>
                    <td>{aircraft_display}</td>
                    <td>{duration}</td>
                </tr>
                """)

        # Return flights
        return_flight = summary.get("return")
        if return_flight:
            flight_details = return_flight.get("flight_details", [])
            
            for seg_idx, flight_detail in enumerate(flight_details):
                carrier_code = flight_detail.get("carrierCode", "")
                flight_number = flight_detail.get("number", "")
                aircraft_code = flight_detail.get("aircraft", {}).get("code", "")
                operating_carrier = flight_detail.get("operating", {}).get("carrierCode", "")
                
                departure = flight_detail.get("departure", {})
                arrival = flight_detail.get("arrival", {})
                duration = flight_detail.get("duration", "")
                
                dep_time = format_datetime(departure.get("time", ""))
                arr_time = format_datetime(arrival.get("time", ""))
                route = f"{departure.get('airport', 'N/A')} → {arrival.get('airport', 'N/A')}"
                
                direction_label = f"Return" if seg_idx == 0 else f"Return (Seg {seg_idx + 1})"
                
                # Flight details display
                flight_info_display = f"{carrier_code} {flight_number}"
                if operating_carrier and operating_carrier != carrier_code:
                    flight_info_display += f" (operated by {operating_carrier})"
                
                aircraft_display = aircraft_code if aircraft_code else "N/A"
                
                html_parts.append(f"""
                <tr>
                    <td><strong>{direction_label}</strong></td>
                    <td>
                        <div style="font-weight: 600;">{flight_info_display}</div>
                        <div style="font-size: 12px; color: #666;">Carrier: {carrier_code}</div>
                    </td>
                    <td class="route-info">{route}</td>
                    <td>
                        <div>{dep_time}</div>
                        <div style="font-size: 12px; color: #666;">Terminal {departure.get('terminal', 'N/A')}</div>
                    </td>
                    <td>
                        <div>{arr_time}</div>
                        <div style="font-size: 12px; color: #666;">Terminal {arrival.get('terminal', 'N/A')}</div>
                    </td>
                    <td>{aircraft_display}</td>
                    <td>{duration}</td>
                </tr>
                """)

        html_parts.append("</tbody></table></div>")

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
