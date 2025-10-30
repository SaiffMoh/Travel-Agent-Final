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
    """Generate complete HTML with summary and collapsible package cards using native HTML details/summary."""
    html_parts = []
    
    # Add enhanced CSS styling - NO JAVASCRIPT
    html_parts.append("""
    <style>
        .travel-summary {
            border-left: 4px solid #007bff;
            padding: 16px;
            margin-bottom: 24px;
            background: rgba(0, 123, 255, 0.05);
            border-radius: 4px;
        }
        
        .package-container {
            border: 1px solid rgba(0, 0, 0, 0.1);
            border-radius: 8px;
            margin-bottom: 24px;
            overflow: hidden;
            transition: all 0.3s ease;
        }
        
        .package-container.optimal {
            border: 2px solid #28a745;
            box-shadow: 0 2px 8px rgba(40, 167, 69, 0.2);
        }
        
        /* Native details/summary styling */
        .package-details {
            border: none;
        }
        
        .package-details[open] {
            background: rgba(0, 0, 0, 0.01);
        }
        
        .package-header {
            background: rgba(0, 0, 0, 0.02);
            padding: 16px;
            border-bottom: 1px solid rgba(0, 0, 0, 0.1);
            cursor: pointer;
            transition: background 0.2s ease;
            display: flex;
            justify-content: space-between;
            align-items: center;
            list-style: none;
        }
        
        .package-header::-webkit-details-marker {
            display: none;
        }
        
        .package-header:hover {
            background: rgba(0, 0, 0, 0.04);
        }
        
        .package-container.optimal .package-header {
            background: rgba(40, 167, 69, 0.08);
            border-bottom: 1px solid rgba(40, 167, 69, 0.2);
        }
        
        .package-header-left {
            flex: 1;
        }
        
        .package-header-right {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        
        .optimal-badge {
            background: #28a745;
            color: white;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.85em;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            gap: 4px;
        }
        
        .savings-badge {
            background: #dc3545;
            color: white;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.85em;
            font-weight: 600;
        }
        
        .collapse-indicator {
            font-size: 1.2em;
            transition: transform 0.3s ease;
            color: #007bff;
        }
        
        .package-details[open] .collapse-indicator {
            transform: rotate(180deg);
        }
        
        .package-summary-row {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 12px;
            margin-top: 8px;
            font-size: 0.9em;
        }
        
        .summary-item {
            display: flex;
            flex-direction: column;
        }
        
        .summary-label {
            color: rgba(0, 0, 0, 0.6);
            font-size: 0.85em;
            margin-bottom: 2px;
        }
        
        .summary-value {
            font-weight: 600;
            color: #007bff;
        }
        
        .package-content {
            padding: 16px;
        }
        
        .section-title {
            color: #007bff;
            margin: 20px 0 12px 0;
            padding-bottom: 8px;
            border-bottom: 2px solid rgba(0, 123, 255, 0.2);
        }
        
        .subsection-title {
            color: #495057;
            margin: 16px 0 8px 0;
            font-size: 1.1em;
        }
        
        .data-table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 16px;
            border: 1px solid rgba(0, 0, 0, 0.1);
            border-radius: 4px;
            overflow: hidden;
        }
        
        .data-table th {
            background: rgba(0, 0, 0, 0.05);
            padding: 12px 8px;
            text-align: left;
            font-weight: 600;
            font-size: 0.9em;
            border-bottom: 1px solid rgba(0, 0, 0, 0.1);
        }
        
        .data-table td {
            padding: 10px 8px;
            border-bottom: 1px solid rgba(0, 0, 0, 0.05);
            vertical-align: top;
        }
        
        .data-table tr:nth-child(even) {
            background: rgba(0, 0, 0, 0.02);
        }
        
        .flight-offer {
            border: 1px solid rgba(0, 0, 0, 0.1);
            border-radius: 6px;
            margin-bottom: 16px;
            overflow: hidden;
        }
        
        .flight-offer-header {
            background: rgba(0, 123, 255, 0.05);
            padding: 12px 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid rgba(0, 0, 0, 0.1);
        }
        
        .flight-total-price {
            font-weight: bold;
            font-size: 1.1em;
            color: #007bff;
        }
        
        .currency-note {
            background: rgba(255, 193, 7, 0.1);
            border: 1px solid rgba(255, 193, 7, 0.3);
            color: #856404;
            padding: 12px;
            border-radius: 4px;
            margin-bottom: 12px;
            font-size: 0.9em;
        }
        
        .price-cell {
            font-weight: 600;
            color: #007bff;
        }
        
        .time-info {
            font-weight: 500;
        }
        
        .terminal-info, .carrier-info, .flight-seats {
            font-size: 0.85em;
            color: rgba(0, 0, 0, 0.6);
        }
        
        .no-data, .no-data-cell {
            text-align: center;
            font-style: italic;
            color: rgba(0, 0, 0, 0.5);
            padding: 20px;
        }
        
        .info-label {
            font-weight: 500;
            width: 30%;
        }
        
        .description-cell {
            max-width: 200px;
            word-wrap: break-word;
        }
        
        @media (max-width: 768px) {
            .flight-offer-header {
                flex-direction: column;
                align-items: flex-start;
                gap: 8px;
            }
            
            .data-table {
                font-size: 0.85em;
            }
            
            .data-table th,
            .data-table td {
                padding: 8px 6px;
            }
            
            .package-summary-row {
                grid-template-columns: 1fr;
            }
        }
    </style>
    """)

    if summary:
        html_parts.append(f"""
        <div class="travel-summary">
            <h3 class="section-title">🌟 Your Travel Recommendations</h3>
            <div class="summary-content">{escape(summary).replace(chr(10), '<br>')}</div>
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
    """Generate HTML for a single collapsible travel package using native HTML details/summary."""
    package_id = package.get("package_id", package_num)
    travel_dates = package.get("travel_dates", {})
    flight_offer = package.get("flight_offer", {})  # Changed from flight_offers to flight_offer
    hotel_info = package.get("hotels", {})
    pricing = package.get("pricing", {})
    is_optimal = package.get("is_optimal", False)
    savings_vs_optimal = package.get("savings_vs_optimal")
    
    duration = travel_dates.get("duration_nights", "N/A")
    checkin = travel_dates.get("checkin", "N/A")
    checkout = travel_dates.get("checkout", "N/A")
    
    flight_price = pricing.get("flight_price", 0)
    flight_currency = pricing.get("flight_currency", "")
    hotel_price = hotel_info.get("min_price", 0)
    hotel_currency = hotel_info.get("currency", "N/A")
    available_hotels = hotel_info.get("available_count", 0)
    
    # Get flight summary from single flight offer
    flight_summary = ""
    if flight_offer:
        summary = flight_offer.get("summary", {})
        outbound = summary.get("outbound", {})
        outbound_stops = outbound.get("stops", 0)
        stops_text = "Direct" if outbound_stops == 0 else f"{outbound_stops} stop{'s' if outbound_stops > 1 else ''}"
        flight_summary = f"{stops_text}"

    # Container classes
    container_classes = "package-container"
    if is_optimal:
        container_classes += " optimal"

    # Use 'open' attribute only for optimal package
    details_open = ' open' if is_optimal else ''

    html_parts = [f"""
    <div class="{container_classes}">
        <details class="package-details"{details_open}>
            <summary class="package-header">
                <div class="package-header-left">
                    <h3>📦 Package {package_id} - {duration} Night{'s' if duration != 1 else ''}</h3>
                    <div class="package-summary-row">
                        <div class="summary-item">
                            <span class="summary-label">Dates</span>
                            <span class="summary-value">{checkin} to {checkout}</span>
                        </div>
                        <div class="summary-item">
                            <span class="summary-label">Flight</span>
                            <span class="summary-value">{flight_price:,.2f} {flight_currency} • {flight_summary}</span>
                        </div>
                        <div class="summary-item">
                            <span class="summary-label">Hotels</span>
                            <span class="summary-value">{available_hotels} available from {hotel_price:,.2f} {hotel_currency}</span>
                        </div>
                    </div>
                </div>
                <div class="package-header-right">
    """]

    # Add optimal badge
    if is_optimal:
        html_parts.append("""
                    <span class="optimal-badge">⭐ Best Value</span>
        """)
    elif savings_vs_optimal:
        total_diff = savings_vs_optimal.get("total_difference", 0)
        if total_diff > 0:
            percentage = savings_vs_optimal.get("percentage_more", 0)
            html_parts.append(f"""
                    <span class="savings-badge">+{percentage:.0f}% more</span>
            """)

    html_parts.append("""
                    <span class="collapse-indicator">▼</span>
                </div>
            </summary>
            <div class="package-content">
    """)

    # Add detailed package content
    html_parts.append(generate_package_info_table(travel_dates, pricing))
    
    # Add savings comparison if not optimal
    if not is_optimal and savings_vs_optimal:
        html_parts.append(generate_savings_comparison(savings_vs_optimal))
    
    html_parts.append(generate_pricing_table(pricing))
    html_parts.append(generate_flight_details_section(flight_offer))  # Changed function call
    html_parts.append(generate_hotel_table(hotel_info))

    html_parts.append("""
            </div>
        </details>
    </div>
    """)

    return "".join(html_parts)

def generate_savings_comparison(savings_vs_optimal: dict) -> str:
    """Generate savings comparison section."""
    
    flight_diff = savings_vs_optimal.get("flight_difference", 0)
    hotel_diff = savings_vs_optimal.get("hotel_difference", 0)
    total_diff = savings_vs_optimal.get("total_difference", 0)
    percentage = savings_vs_optimal.get("percentage_more", 0)
    flight_curr = savings_vs_optimal.get("flight_currency", "EGP")
    hotel_curr = savings_vs_optimal.get("hotel_currency", "N/A")
    
    return f"""
    <div class="currency-note" style="background: rgba(220, 53, 69, 0.1); border-color: rgba(220, 53, 69, 0.3);">
        <strong>💡 Price Comparison vs. Best Value Package:</strong><br>
        This package costs <strong>{percentage:.1f}% more</strong> than the optimal option:<br>
        • Flight: +{flight_diff:,.2f} {flight_curr}<br>
        • Hotel: +{hotel_diff:,.2f} {hotel_curr}<br>
        Consider the Best Value package for better savings!
    </div>
    """

def generate_package_info_table(travel_dates: dict, pricing: dict) -> str:
    """Generate basic package information table."""
    
    return f"""
    <h4 class="section-title">📅 Package Overview</h4>
    <table class="data-table package-info-table">
        <tbody>
            <tr>
                <td class="info-label">Check-in Date</td>
                <td class="info-value">{travel_dates.get('checkin', 'N/A')}</td>
            </tr>
            <tr>
                <td class="info-label">Check-out Date</td>
                <td class="info-value">{travel_dates.get('checkout','N/A')}</td>
            </tr>
            <tr>
                <td class="info-label">Duration</td>
                <td class="info-value">{travel_dates.get('duration_nights', 'N/A')} nights</td>
            </tr>
            <tr>
                <td class="info-label">Flight Currency</td>
                <td class="info-value">{pricing.get('flight_currency', 'N/A')}</td>
            </tr>
            <tr>
                <td class="info-label">Hotel Currency</td>
                <td class="info-value">{pricing.get('hotel_currency', 'N/A')}</td>
            </tr>
        </tbody>
    </table>
    """

def generate_pricing_table(pricing: dict) -> str:
    """Generate pricing summary table with separate currencies."""
    flight_price = pricing.get("flight_price", 0)
    flight_currency = pricing.get("flight_currency", "")
    hotel_price = pricing.get("min_hotel_price", 0)
    hotel_currency = pricing.get("hotel_currency", "N/A")

    return f"""
    <h4 class="section-title">💰 Pricing Summary</h4>
    <div class="currency-note">
        ⚠️ Note: Flight and hotel prices are in different currencies and cannot be combined directly.
    </div>
    <table class="data-table pricing-table">
        <thead>
            <tr>
                <th class="pricing-header">Component</th>
                <th class="pricing-header">Price</th>
                <th class="pricing-header">Currency</th>
                <th class="pricing-header">Notes</th>
            </tr>
        </thead>
        <tbody>
            <tr class="flight-price-row">
                <td class="component-cell"><strong>Flight (Round Trip)</strong></td>
                <td class="price-cell">{flight_price:,.2f}</td>
                <td class="currency-cell">{flight_currency}</td>
                <td class="notes-cell">Complete round trip airfare</td>
            </tr>
            <tr class="hotel-price-row">
                <td class="component-cell"><strong>Hotel (Starting from)</strong></td>
                <td class="price-cell">{hotel_price:,.2f}</td>
                <td class="currency-cell">{hotel_currency}</td>
                <td class="notes-cell">Per stay, varies by selection</td>
            </tr>
        </tbody>
    </table>
    """

def generate_flight_details_section(flight_offer: dict) -> str:
    """Generate section for single flight offer with enhanced details."""
    html_parts = [f'<h4 class="section-title">✈️ Flight Details</h4>']

    if not flight_offer:
        return '<h4 class="section-title">✈️ Flight Details</h4><p class="no-data">No flight information available.</p>'

    summary = flight_offer.get("summary", {})
    price = flight_offer.get("price", 0)
    currency = flight_offer.get("currency", "")
    bookable_seats = summary.get("numberOfBookableSeats", 0)

    html_parts.append(f"""
    <div class="flight-offer">
        <div class="flight-offer-header">
            <h5 class="flight-option-title">Selected Flight</h5>
            <div class="flight-price-info">
                <div class="flight-total-price">{price:,.2f} {currency}</div>
                <div class="flight-seats">Available Seats: {bookable_seats}</div>
            </div>
        </div>
        <table class="data-table flight-details-table">
            <thead>
                <tr>
                    <th class="flight-header">Direction</th>
                    <th class="flight-header">Flight Details</th>
                    <th class="flight-header">Route</th>
                    <th class="flight-header">Departure</th>
                    <th class="flight-header">Arrival</th>
                    <th class="flight-header">Aircraft</th>
                    <th class="flight-header">Duration</th>
                </tr>
            </thead>
            <tbody>
    """)

    # Process outbound flights
    html_parts.append(process_flight_segments(summary.get("outbound"), "Outbound"))
    
    # Process return flights  
    html_parts.append(process_flight_segments(summary.get("return"), "Return"))

    html_parts.append("</tbody></table></div>")

    return "".join(html_parts)

def process_flight_segments(flight_data: dict, direction: str) -> str:
    """Process flight segments for a given direction."""
    if not flight_data:
        return ""
        
    html_parts = []
    flight_details = flight_data.get("flight_details", [])
    
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
        
        direction_label = f"{direction}" if seg_idx == 0 else f"{direction} (Seg {seg_idx + 1})"
        
        # Flight details display
        flight_info_display = f"{carrier_code} {flight_number}"
        if operating_carrier and operating_carrier != carrier_code:
            flight_info_display += f" (operated by {operating_carrier})"
        
        aircraft_display = aircraft_code if aircraft_code else "N/A"
        
        html_parts.append(f"""
        <tr class="flight-segment-row">
            <td class="direction-cell"><strong>{direction_label}</strong></td>
            <td class="flight-info-cell">
                <div class="flight-number">{flight_info_display}</div>
                <div class="carrier-info">Carrier: {carrier_code}</div>
            </td>
            <td class="route-cell">{route}</td>
            <td class="departure-cell">
                <div class="time-info">{dep_time}</div>
                <div class="terminal-info">Terminal {departure.get('terminal', 'N/A')}</div>
            </td>
            <td class="arrival-cell">
                <div class="time-info">{arr_time}</div>
                <div class="terminal-info">Terminal {arrival.get('terminal', 'N/A')}</div>
            </td>
            <td class="aircraft-cell">{aircraft_display}</td>
            <td class="duration-cell">{duration}</td>
        </tr>
        """)
    
    return "".join(html_parts)

def generate_hotel_table(hotel_info: dict) -> str:
    """Generate separate tables for API and company hotel options."""
    html_parts = [f'<h4 class="section-title">🏨 Hotel Options</h4>']

    if not hotel_info:
        return '<h4 class="section-title">🏨 Hotel Options</h4><p class="no-data">No hotel information available.</p>'

    api_hotels = hotel_info.get("api_hotels", {})
    company_hotels = hotel_info.get("company_hotels", {})

    # API Hotels Section
    html_parts.append(f"""
    <h5 class="subsection-title">🌐 Other Hotel Options</h5>
    <table class="data-table api-hotels-table">
        <thead>
            <tr>
                <th class="hotel-header">Hotel Name</th>
                <th class="hotel-header">Room Type</th>
                <th class="hotel-header">Description</th>
                <th class="hotel-header">Price per Stay</th>
                <th class="hotel-header">Currency</th>
                <th class="hotel-header">Availability</th>
            </tr>
        </thead>
        <tbody>
    """)

    if api_hotels.get("total_found", 0) == 0:
        html_parts.append('<tr><td colspan="6" class="no-data-cell">No Other hotels available</td></tr>')
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

                if len(room_description) > 80:
                    room_description = room_description[:77] + "..."

                availability_status = 'Available' if is_available else 'Not Available'

                html_parts.append(f"""
                <tr class="hotel-row">
                    <td class="hotel-name-cell">{escape(hotel_name)}</td>
                    <td class="room-type-cell"><strong>{escape(room_type)}</strong></td>
                    <td class="description-cell">{escape(room_description)}</td>
                    <td class="hotel-price-cell">{offer_price:,.2f}</td>
                    <td class="hotel-currency-cell">{currency}</td>
                    <td class="availability-cell">{availability_status}</td>
                </tr>
                """)
            else:
                html_parts.append(f"""
                <tr class="hotel-row">
                    <td class="hotel-name-cell">{escape(hotel_name)}</td>
                    <td class="room-type-cell">-</td>
                    <td class="description-cell">No room details available</td>
                    <td class="hotel-price-cell">-</td>
                    <td class="hotel-currency-cell">-</td>
                    <td class="availability-cell">No Offers</td>
                </tr>
                """)

    html_parts.append('</tbody></table>')

    # Company Hotels Section
    html_parts.append(f"""
    <h5 class="subsection-title">🤝 Company Preferred Hotels</h5>
    <table class="data-table company-hotels-table">
        <thead>
            <tr>
                <th class="hotel-header">Hotel Name</th>
                <th class="hotel-header">Room Type</th>
                <th class="hotel-header">Price per Stay</th>
                <th class="hotel-header">Currency</th>
                <th class="hotel-header">Contacts</th>
                <th class="hotel-header">Notes</th>
                <th class="hotel-header">Availability</th>
            </tr>
        </thead>
        <tbody>
    """)

    if company_hotels.get("total_found", 0) == 0:
        html_parts.append('<tr><td colspan="7" class="no-data-cell">No company preferred hotels available</td></tr>')
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

                availability_status = 'Available' if is_available else 'Not Available'

                html_parts.append(f"""
                <tr class="company-hotel-row">
                    <td class="hotel-name-cell">{escape(hotel_name)}</td>
                    <td class="room-type-cell"><strong>{escape(room_type)}</strong></td>
                    <td class="hotel-price-cell">{offer_price:,.2f}</td>
                    <td class="hotel-currency-cell">{currency}</td>
                    <td class="contacts-cell">{escape(contacts)}</td>
                    <td class="notes-cell">{escape(notes)}</td>
                    <td class="availability-cell">{availability_status}</td>
                </tr>
                """)
            else:
                html_parts.append(f"""
                <tr class="company-hotel-row">
                    <td class="hotel-name-cell">{escape(hotel_name)}</td>
                    <td class="room-type-cell">-</td>
                    <td class="hotel-price-cell">-</td>
                    <td class="hotel-currency-cell">-</td>
                    <td class="contacts-cell">{escape(hotel.get("contacts", "N/A"))}</td>
                    <td class="notes-cell">{escape(hotel.get("notes", "None"))}</td>
                    <td class="availability-cell">No Offers</td>
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