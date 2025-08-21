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
    
    # Add CSS styles
    html_parts.append("""
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .travel-summary { 
            background-color: #f8f9fa; 
            border-left: 4px solid #007bff; 
            padding: 15px; 
            margin-bottom: 25px; 
            border-radius: 5px;
        }
        .package-container { 
            margin-bottom: 30px; 
            border: 1px solid #ddd; 
            border-radius: 8px; 
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .package-header { 
            background-color: #007bff; 
            color: white; 
            padding: 15px; 
            font-size: 18px; 
            font-weight: bold;
        }
        .package-content { padding: 20px; }
        .info-table { 
            width: 100%; 
            border-collapse: collapse; 
            margin-bottom: 20px;
        }
        .info-table th { 
            background-color: #f1f3f4; 
            padding: 12px; 
            text-align: left; 
            font-weight: bold;
            border-bottom: 2px solid #dee2e6;
        }
        .info-table td { 
            padding: 10px 12px; 
            border-bottom: 1px solid #dee2e6;
            vertical-align: top;
        }
        .info-table tr:hover { background-color: #f8f9fa; }
        .price-highlight { 
            background-color: #d4edda; 
            color: #155724; 
            font-weight: bold; 
            padding: 5px 8px; 
            border-radius: 3px;
        }
        .section-title { 
            color: #495057; 
            font-size: 16px; 
            font-weight: bold; 
            margin: 20px 0 10px 0; 
            border-bottom: 2px solid #007bff;
            padding-bottom: 5px;
        }
        .flight-route { color: #007bff; font-weight: bold; }
        .hotel-count { color: #28a745; font-weight: bold; }
        .no-packages { 
            text-align: center; 
            padding: 40px; 
            color: #6c757d; 
            font-style: italic;
        }
    </style>
    """)
    
    # Add LLM Summary
    if summary:
        html_parts.append(f"""
        <div class="travel-summary">
            <h2>🌟 Your Travel Recommendations</h2>
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
    
    # Pricing Summary
    total_price = pricing.get("total_min_price", 0)
    currency = pricing.get("currency", "EGP")
    flight_price = pricing.get("flight_price", 0)
    hotel_price = pricing.get("min_hotel_price", 0)
    
    html_parts.append(f"""
    <div class="section-title">💰 Pricing Summary</div>
    <table class="info-table">
        <tr>
            <td><strong>Total Package Price</strong></td>
            <td><span class="price-highlight">{total_price:,.2f} {currency}</span></td>
        </tr>
        <tr>
            <td>Flight Price</td>
            <td>{flight_price:,.2f} {currency}</td>
        </tr>
        <tr>
            <td>Minimum Hotel Price</td>
            <td>{hotel_price:,.2f} {currency}</td>
        </tr>
    </table>
    """)
    
    # Flight Information
    html_parts.append(generate_flight_html(flight_info))
    
    # Hotel Information  
    html_parts.append(generate_hotel_html(hotel_info))
    
    html_parts.append("</div></div>")
    
    return "".join(html_parts)

def generate_flight_html(flight_info: dict) -> str:
    """Generate HTML for flight information."""
    
    html_parts = [f'<div class="section-title">✈️ Flight Details</div>']
    
    if not flight_info:
        return '<div class="section-title">✈️ Flight Details</div><p>No flight information available.</p>'
    
    summary = flight_info.get("summary", {})
    price = flight_info.get("price", 0)
    currency = flight_info.get("currency", "EGP")
    
    html_parts.append('<table class="info-table">')
    
    # Basic flight info
    trip_type = summary.get("trip_type", "unknown")
    html_parts.append(f"""
    <tr>
        <td><strong>Trip Type</strong></td>
        <td>{trip_type.replace("_", " ").title()}</td>
    </tr>
    <tr>
        <td><strong>Price</strong></td>
        <td>{price:,.2f} {currency}</td>
    </tr>
    """)
    
    # Outbound flight details
    outbound = summary.get("outbound")
    if outbound:
        departure = outbound.get("departure", {})
        arrival = outbound.get("arrival", {})
        duration = outbound.get("duration", "N/A")
        stops = outbound.get("stops", 0)
        
        dep_time = format_datetime(departure.get("time", ""))
        arr_time = format_datetime(arrival.get("time", ""))
        
        route_info = f"{departure.get('airport', 'N/A')} → {arrival.get('airport', 'N/A')}"
        
        html_parts.append(f"""
        <tr>
            <td><strong>Outbound Route</strong></td>
            <td><span class="flight-route">{route_info}</span></td>
        </tr>
        <tr>
            <td>Departure</td>
            <td>{dep_time} (Terminal {departure.get('terminal', 'N/A')})</td>
        </tr>
        <tr>
            <td>Arrival</td>
            <td>{arr_time} (Terminal {arrival.get('terminal', 'N/A')})</td>
        </tr>
        <tr>
            <td>Duration</td>
            <td>{duration}</td>
        </tr>
        <tr>
            <td>Stops</td>
            <td>{"Direct" if stops == 0 else f"{stops} stop{'s' if stops != 1 else ''}"}</td>
        </tr>
        """)
    
    # Return flight details (if exists)
    return_flight = summary.get("return")
    if return_flight:
        departure = return_flight.get("departure", {})
        arrival = return_flight.get("arrival", {})
        duration = return_flight.get("duration", "N/A")
        stops = return_flight.get("stops", 0)
        
        dep_time = format_datetime(departure.get("time", ""))
        arr_time = format_datetime(arrival.get("time", ""))
        
        route_info = f"{departure.get('airport', 'N/A')} → {arrival.get('airport', 'N/A')}"
        
        html_parts.append(f"""
        <tr>
            <td><strong>Return Route</strong></td>
            <td><span class="flight-route">{route_info}</span></td>
        </tr>
        <tr>
            <td>Return Departure</td>
            <td>{dep_time} (Terminal {departure.get('terminal', 'N/A')})</td>
        </tr>
        <tr>
            <td>Return Arrival</td>
            <td>{arr_time} (Terminal {arrival.get('terminal', 'N/A')})</td>
        </tr>
        <tr>
            <td>Return Duration</td>
            <td>{duration}</td>
        </tr>
        <tr>
            <td>Return Stops</td>
            <td>{"Direct" if stops == 0 else f"{stops} stop{'s' if stops != 1 else ''}"}</td>
        </tr>
        """)
    
    html_parts.append('</table>')
    return "".join(html_parts)

def generate_hotel_html(hotel_info: dict) -> str:
    """Generate HTML for hotel information."""
    
    html_parts = [f'<div class="section-title">🏨 Hotel Options</div>']
    
    if not hotel_info:
        return '<div class="section-title">🏨 Hotel Options</div><p>No hotel information available.</p>'
    
    total_found = hotel_info.get("total_found", 0)
    available_count = hotel_info.get("available_count", 0)
    min_price = hotel_info.get("min_price", 0)
    currency = hotel_info.get("currency", "EGP")
    top_options = hotel_info.get("top_options", [])
    
    html_parts.append(f"""
    <table class="info-table">
        <tr>
            <td><strong>Hotels Found</strong></td>
            <td><span class="hotel-count">{total_found} total</span></td>
        </tr>
        <tr>
            <td><strong>Available Hotels</strong></td>
            <td><span class="hotel-count">{available_count} available</span></td>
        </tr>
        <tr>
            <td><strong>Starting Price</strong></td>
            <td><span class="price-highlight">From {min_price:,.2f} {currency}</span></td>
        </tr>
    </table>
    """)
    
    # Top hotel options
    if top_options:
        html_parts.append('<div class="section-title">🌟 Top Hotel Options</div>')
        html_parts.append('<table class="info-table">')
        html_parts.append('<tr><th>Hotel</th><th>Room Type</th><th>Price</th></tr>')
        
        for i, hotel in enumerate(top_options[:3], 1):  # Show top 3
            hotel_data = hotel.get("hotel", {})
            best_offers = hotel.get("best_offers", [])
            
            hotel_name = hotel_data.get("name", f"Hotel {i}")
            
            if best_offers:
                best_offer = best_offers[0]  # Cheapest offer
                room_type = best_offer.get("room_type", "Standard")
                offer_price = best_offer.get("offer", {}).get("price", {}).get("total", 0)
                
                html_parts.append(f"""
                <tr>
                    <td><strong>{escape(hotel_name)}</strong></td>
                    <td>{escape(room_type)}</td>
                    <td>{float(offer_price):,.2f} {currency}</td>
                </tr>
                """)
        
        html_parts.append('</table>')
    
    return "".join(html_parts)

def format_datetime(datetime_str: str) -> str:
    """Format datetime string for display."""
    if not datetime_str:
        return "N/A"
    
    try:
        # Handle different datetime formats
        if "T" in datetime_str:
            dt = datetime.fromisoformat(datetime_str.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M")
        else:
            return datetime_str
    except:
        return datetime_str