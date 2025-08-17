from typing import List, Optional, Any
from html import escape
from Models.ExtractedInfo import ExtractedInfo
from Utils.get_html_attributes import get_html_attributes
from Models.TravelSearchState import TravelSearchState
from typing import Any, List
from dataclasses import dataclass, field
import html
import re
from datetime import datetime


def toHTML(state: TravelSearchState) -> TravelSearchState:
    def create_simple_package_html(package: dict) -> str:
        """Create very simple HTML for a single package with more hotel details"""
        try:
            # Extract details as before
            package_id = package.get('package_id', 1)
            pricing = package.get('pricing', {})
            travel_dates = package.get('travel_dates', {})
            flight_data = package.get('flight', {})
            hotel_data = package.get('hotels', {})
            
            # Get basic info only
            total_price = pricing.get('total_min_price', 0)
            currency = pricing.get('currency', 'EGP')
            duration = travel_dates.get('duration_nights', 0)
            checkin = travel_dates.get('checkin', '')
            checkout = travel_dates.get('checkout', '')
            
            # Flight summary
            flight_summary = flight_data.get('summary', {})
            outbound = flight_summary.get('outbound', {})
            
            departure_airport = outbound.get('departure', {}).get('airport', 'N/A')
            arrival_airport = outbound.get('arrival', {}).get('airport', 'N/A')
            departure_time = outbound.get('departure', {}).get('time', '')
            stops = outbound.get('stops', 0)
            
            # Display hotels horizontally in a grid
            hotel_list = hotel_data.get('best_offers', [])
            
            hotel_html = ""
            for hotel in hotel_list:
                hotel_name = hotel.get('hotel', {}).get('name', 'N/A')
                hotel_location = hotel.get('hotel', {}).get('location', 'N/A')
                hotel_price_per_night = hotel.get('offer', {}).get('price', {}).get('total', 0)
                hotel_currency = hotel.get('offer', {}).get('price', {}).get('currency', 'EGP')
                room_type = hotel.get('offer', {}).get('room', {}).get('type', 'Standard Room')
                hotel_rating = hotel.get('hotel', {}).get('rating', 'N/A')
                
                hotel_html += f"""
                <div class="hotel-card">
                    <h4>{hotel_name}</h4>
                    <p>{hotel_location}</p>
                    <p>{room_type} - {hotel_price_per_night} {hotel_currency}/night</p>
                    <p>Rating: {hotel_rating}</p>
                </div>
                """
        
            html = f"""
            <div class="package-card">
                <div class="package-header">
                    <span class="package-title">Package {package_id}</span>
                    <span class="package-price">{total_price:,.0f} {currency}</span>
                </div>
                <div class="trip-info">
                    <div class="dates">{checkin} to {checkout} ({duration} nights)</div>
                </div>
                <div class="flight-simple">
                    <div class="route">{departure_airport} → {arrival_airport}</div>
                    <div class="departure">Departs: {format_datetime(departure_time)}</div>
                    <div class="stops">{"Direct flight" if stops == 0 else f"{stops} stop{'s' if stops > 1 else ''}"}</div>
                </div>
                <div class="hotel-list">
                    {hotel_html}
                </div>
            </div>
            """
        
            return html
    
        except Exception as e:
            print(f"Error creating simple package HTML: {e}")
            return f"<div class='package-error'>Package {package.get('package_id', '?')} - Error loading details</div>"

    # CSS for horizontal display of packages
    styles = """
    <style>
        .package-container {
            display: flex;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 20px;
        }

        .package-card {
            width: 30%;
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 15px;
            background-color: #fff;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        }
        
        .package-header {
            background-color: #4CAF50;
            color: white;
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 15px;
        }
        
        .package-title {
            font-weight: bold;
            font-size: 1.1em;
        }
        
        .package-price {
            font-size: 1.2em;
            font-weight: bold;
        }

        .trip-info, .flight-simple {
            margin-bottom: 15px;
        }

        .hotel-list {
            display: flex;
            overflow-x: auto;
            gap: 15px;
        }

        .hotel-card {
            width: 200px;
            border: 1px solid #ddd;
            padding: 10px;
            border-radius: 5px;
            background-color: #f9f9f9;
            box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
        }
        
        .hotel-card h4 {
            font-size: 1.1em;
            font-weight: bold;
        }
        
        .hotel-card p {
            font-size: 0.9em;
            color: #555;
        }
    </style>
    """

    # Process packages
    travel_packages = state.get("travel_packages", [])
    html_packages = []

    for i, package in enumerate(travel_packages):
        if isinstance(package, dict):
            package_html = create_simple_package_html(package)
            if i == 0:
                package_html = styles + package_html
            html_packages.append(package_html)

    # Package container that holds all the packages horizontally
    package_container_html = f"""
    <div class="package-container">
        {''.join(html_packages)}
    </div>
    """

    # Attach HTML to state
    state["travel_packages_html"] = package_container_html
    state["current_node"] = "to_html"
    
    return state
 
def format_extracted_info_html(extracted_info: ExtractedInfo) -> str:
    """Format extracted information as minimal HTML"""
    details = []
    if extracted_info.origin:
        details.append(f"{extracted_info.origin}")
    if extracted_info.destination:
        details.append(f"→ {extracted_info.destination}")
    if extracted_info.departure_date:
        details.append(f"• {extracted_info.departure_date}")
    if extracted_info.duration:
        details.append(f"• {extracted_info.duration} days")
    
    if not details:
        return ""
    
    html_content = f"""
    <div style="background: #f0f8ff; padding: 12px; margin: 10px 0; border-radius: 6px; border-left: 3px solid #4CAF50;">
        ✈️ {' '.join(details)}
    </div>
    """
    
    return html_content
from datetime import datetime

def format_datetime(dt_str: str) -> str:
    """Format datetime string to readable format"""
    if not dt_str:
        return dt_str
    try:
        if 'T' in dt_str:
            dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
            return dt.strftime('%b %d, %I:%M %p')
        return dt_str
    except Exception as e:
        print(f"Error formatting datetime: {e}")
        return dt_str
