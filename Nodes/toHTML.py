from typing import List, Optional, Any
from html import escape
from Models.TravelSearchState import TravelSearchState
from datetime import datetime

def toHTML(state: TravelSearchState) -> TravelSearchState:
    """Convert travel packages to clean HTML format with LLM summary."""
    
    travel_packages = state.get("travel_packages", [])
    package_summary = state.get("package_summary", "")
    
    try:
        print(f"toHTML: received {len(travel_packages)} packages")
    except Exception as _:
        print("toHTML: unable to determine package count")
    
    # Generate HTML content
    html_content = generate_complete_html(travel_packages, package_summary)
    
    # Store both individual package HTML and complete HTML
    state["travel_packages_html"] = [html_content]  # Single complete HTML
    state["complete_travel_html"] = html_content
    state["current_node"] = "to_html"
    
    print(f"toHTML: generated complete HTML content")
    return state

def generate_complete_html(packages: List[dict], summary: str) -> str:
    """Generate complete HTML with summary and package tables."""
    
    html_parts = []
    
    # Add CSS styles - designed to work with both light and dark modes
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
    
    # Add LLM Summary
    if summary:
        html_parts.append(f"""
        <div class="travel-summary">
            <div class="section-title">🌟 Your Travel Recommendations</div>
            <div>{escape(summary).replace(chr(10), '<br>')}</div>
        </div>
        """)
    
    # Add packages
    if not packages:
        html_parts.append('<div class="no-packages">No travel packages available.</div>')
    else:
        for i, package in enumerate(packages, 1):
            if package:  # Check if package is not None
                html_parts.append(generate_package_html(package, i))
    
    return "".join(html_parts)

def generate_package_html(package: dict, package_num: int) -> str:
    """Generate HTML for a single travel package."""
    
    # Extract package information safely
    package_id = package.get("package_id", package_num)
    travel_dates = package.get("travel_dates", {})
    flight_info = package.get("flight", {})
    hotel_info = package.get("hotels", {})
    pricing = package.get("pricing", {})
    
    # Package header
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
    
    # Pricing Summary Table
    html_parts.append(generate_pricing_table(pricing))
    
    # Flight Information Table
    html_parts.append(generate_flight_table(flight_info))
    
    # Hotel Information Table  
    html_parts.append(generate_hotel_table(hotel_info))
    
    html_parts.append("</div></div>")
    
    return "".join(html_parts)

def generate_pricing_table(pricing: dict) -> str:
    """Generate pricing summary table."""
    
    total_price = pricing.get("total_min_price", 0)
    currency = pricing.get("currency", "EGP")
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
                <td>Round trip included</td>
            </tr>
            <tr>
                <td>Hotel (Starting from)</td>
                <td class="price-cell">{hotel_price:,.2f}</td>
                <td>{currency}</td>
                <td>Per night, varies by selection</td>
            </tr>
        </tbody>
    </table>
    """

def generate_flight_table(flight_info: dict) -> str:
    """Generate comprehensive flight information table."""
    
    html_parts = [f'<div class="section-title">✈️ Flight Details</div>']
    
    if not flight_info:
        return '<div class="section-title">✈️ Flight Details</div><p>No flight information available.</p>'
    
    summary = flight_info.get("summary", {})
    price = flight_info.get("price", 0)
    currency = flight_info.get("currency", "EGP")
    
    # Flight Overview Table
    trip_type = summary.get("trip_type", "unknown").replace("_", " ").title()
    
    html_parts.append(f"""
    <table class="data-table">
        <thead>
            <tr>
                <th>Flight Info</th>
                <th>Details</th>
                <th>Route</th>
                <th>Duration</th>
                <th>Stops</th>
            </tr>
        </thead>
        <tbody>
    """)
    
    # Outbound flight
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
            <td>
                <div>Departure: Terminal {departure.get('terminal', 'N/A')}</div>
                <div>Arrival: Terminal {arrival.get('terminal', 'N/A')}</div>
                <div>Arrives: {arr_time}</div>
            </td>
            <td class="route-info">{route}</td>
            <td>{duration}</td>
            <td>{"Direct" if stops == 0 else f"{stops} stop{'s' if stops != 1 else ''}"}</td>
        </tr>
        """)
    
    # Return flight
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
            <td>
                <div>Departure: Terminal {departure.get('terminal', 'N/A')}</div>
                <div>Arrival: Terminal {arrival.get('terminal', 'N/A')}</div>
                <div>Arrives: {arr_time}</div>
            </td>
            <td class="route-info">{route}</td>
            <td>{duration}</td>
            <td>{"Direct" if stops == 0 else f"{stops} stop{'s' if stops != 1 else ''}"}</td>
        </tr>
        """)
    
    html_parts.append(f"""
        </tbody>
    </table>
    <table class="data-table">
        <thead>
            <tr>
                <th>Trip Type</th>
                <th>Total Price</th>
                <th>Currency</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td>{trip_type}</td>
                <td class="price-cell">{price:,.2f}</td>
                <td>{currency}</td>
            </tr>
        </tbody>
    </table>
    """)
    
    return "".join(html_parts)

def generate_hotel_table(hotel_info: dict) -> str:
    """Generate comprehensive hotel information table."""
    
    html_parts = [f'<div class="section-title">🏨 Hotel Options</div>']
    
    if not hotel_info:
        return '<div class="section-title">🏨 Hotel Options</div><p>No hotel information available.</p>'
    
    total_found = hotel_info.get("total_found", 0)
    available_count = hotel_info.get("available_count", 0)
    min_price = hotel_info.get("min_price", 0)
    currency = hotel_info.get("currency", "EGP")
    top_options = hotel_info.get("top_options", [])
    
    # Hotel Summary Table
    html_parts.append(f"""
    <table class="data-table">
        <thead>
            <tr>
                <th>Hotel Summary</th>
                <th>Count</th>
                <th>Starting Price</th>
                <th>Status</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><strong>Total Hotels Found</strong></td>
                <td>{total_found}</td>
                <td class="price-cell">{min_price:,.2f} {currency}</td>
                <td><span class="status-badge available">{available_count} Available</span></td>
            </tr>
        </tbody>
    </table>
    """)
    
    # Top hotel options table
    if top_options:
        html_parts.append("""
        <div class="section-title">🌟 Top Hotel Options</div>
        <table class="data-table">
            <thead>
                <tr>
                    <th>Hotel Name</th>
                    <th>Room Type & Description</th>
                    <th>Price per Night</th>
                    <th>Currency</th>
                    <th>Availability</th>
                </tr>
            </thead>
            <tbody>
        """)
        
        for i, hotel in enumerate(top_options[:5], 1):  # Show top 5
            hotel_data = hotel.get("hotel", {})
            best_offers = hotel.get("best_offers", [])
            is_available = hotel.get("available", True)
            
            hotel_name = hotel_data.get("name", f"Hotel {i}")
            
            if best_offers:
                best_offer = best_offers[0]  # Cheapest offer
                room_type = best_offer.get("room_type", "Standard Room")
                room_description = best_offer.get("description", "Standard accommodation")
                offer_price = best_offer.get("offer", {}).get("price", {}).get("total", 0)
                
                # Clean up room description if it's too long
                if len(room_description) > 100:
                    room_description = room_description[:97] + "..."
                
                availability_badge = '<span class="status-badge available">Available</span>' if is_available else '<span class="status-badge">Not Available</span>'
                
                html_parts.append(f"""
                <tr>
                    <td>
                        <div class="hotel-name">{escape(hotel_name)}</div>
                    </td>
                    <td>
                        <div><strong>{escape(room_type)}</strong></div>
                        <div class="room-description">{escape(room_description)}</div>
                    </td>
                    <td class="price-cell">{float(offer_price):,.2f}</td>
                    <td>{currency}</td>
                    <td>{availability_badge}</td>
                </tr>
                """)
            else:
                html_parts.append(f"""
                <tr>
                    <td>
                        <div class="hotel-name">{escape(hotel_name)}</div>
                    </td>
                    <td>No room details available</td>
                    <td>-</td>
                    <td>-</td>
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
        # Handle different datetime formats
        if "T" in datetime_str:
            dt = datetime.fromisoformat(datetime_str.replace("Z", "+00:00"))
            return dt.strftime("%b %d, %Y %H:%M")
        else:
            return datetime_str
    except:
        return datetime_str