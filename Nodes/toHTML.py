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
                <td>{flight_price:,.2f}</td>
                <td>{flight_currency}</td>
                <td>Complete round trip airfare</td>
            </tr>
            <tr>
                <td><strong>Hotel (Starting from)</strong></td>
                <td>{hotel_price:,.2f}</td>
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
        <div class="flight-offer">
            <div class="flight-header">
                <h4>Flight Option {flight_idx + 1}</h4>
                <div class="flight-price">
                    <div>{price:,.2f} {currency}</div>
                    <div>Available Seats: {bookable_seats}</div>
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
                        <div>{flight_info_display}</div>
                        <div>Carrier: {carrier_code}</div>
                    </td>
                    <td>{route}</td>
                    <td>
                        <div>{dep_time}</div>
                        <div>Terminal {departure.get('terminal', 'N/A')}</div>
                    </td>
                    <td>
                        <div>{arr_time}</div>
                        <div>Terminal {arrival.get('terminal', 'N/A')}</div>
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
                        <div>{flight_info_display}</div>
                        <div>Carrier: {carrier_code}</div>
                    </td>
                    <td>{route}</td>
                    <td>
                        <div>{dep_time}</div>
                        <div>Terminal {departure.get('terminal', 'N/A')}</div>
                    </td>
                    <td>
                        <div>{arr_time}</div>
                        <div>Terminal {arrival.get('terminal', 'N/A')}</div>
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

                availability_badge = 'Available' if is_available else 'Not Available'

                html_parts.append(f"""
                <tr>
                    <td><div>{escape(hotel_name)}</div></td>
                    <td>
                        <div><strong>{escape(room_type)}</strong></div>
                        <div>{escape(room_description)}</div>
                    </td>
                    <td>{offer_price:,.2f}</td>
                    <td>{currency}</td>
                    <td>{availability_badge}</td>
                </tr>
                """)
            else:
                html_parts.append(f"""
                <tr>
                    <td><div>{escape(hotel_name)}</div></td>
                    <td>No room details available</td>
                    <td>-</td>
                    <td>-</td>
                    <td>No Offers</td>
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

                availability_badge = 'Available' if is_available else 'Not Available'

                html_parts.append(f"""
                <tr>
                    <td><div>{escape(hotel_name)}</div></td>
                    <td><strong>{escape(room_type)}</strong></td>
                    <td>{offer_price:,.2f}</td>
                    <td>{currency}</td>
                    <td>{escape(contacts)}</td>
                    <td>{escape(notes)}</td>
                    <td>{availability_badge}</td>
                </tr>
                """)
            else:
                html_parts.append(f"""
                <tr>
                    <td><div>{escape(hotel_name)}</div></td>
                    <td>No room details</td>
                    <td>-</td>
                    <td>-</td>
                    <td>{escape(hotel.get("contacts", "N/A"))}</td>
                    <td>{escape(hotel.get("notes", "None"))}</td>
                    <td>No Offers</td>
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