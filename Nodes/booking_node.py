"""
Nodes/booking_node.py
Handles package booking with passport and visa verification
"""
from Models.TravelSearchState import TravelSearchState
from typing import Dict, Any
import logging
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)


def booking_node(state: TravelSearchState) -> TravelSearchState:
    """
    Handle travel package booking with document verification.
    
    Flow:
    1. Check if package is selected
    2. Verify passport and visa uploads
    3. Confirm booking or request missing documents
    """
    
    logger.info("=" * 60)
    logger.info("BOOKING NODE STARTED")
    logger.info("=" * 60)
    
    thread_id = state.get("thread_id")
    selected_package_id = state.get("selected_package_id")
    travel_packages = state.get("travel_packages", [])
    
    # Check if we have packages to book
    if not travel_packages:
        state["booking_error"] = "No travel packages available for booking"
        state["booking_html"] = generate_error_html("No packages available. Please search for travel packages first.")
        state["current_node"] = "booking"
        return state
    
    # If no package selected yet, show selection interface
    if not selected_package_id:
        logger.info("No package selected - showing selection interface")
        state["booking_html"] = generate_package_selection_html(travel_packages)
        state["booking_in_progress"] = True
        state["needs_followup"] = True
        state["followup_question"] = "Which package would you like to book? Please specify the package number."
        state["current_node"] = "booking"
        return state
    
    # Find the selected package
    selected_package = None
    for pkg in travel_packages:
        if pkg.get("package_id") == selected_package_id:
            selected_package = pkg
            break
    
    if not selected_package:
        state["booking_error"] = f"Package {selected_package_id} not found"
        state["booking_html"] = generate_error_html(f"Package {selected_package_id} not found. Please select a valid package.")
        state["current_node"] = "booking"
        return state
    
    state["selected_package"] = selected_package
    logger.info(f"✓ Package {selected_package_id} selected")
    
    # Check document uploads
    passport_uploaded = state.get("passport_uploaded", False)
    visa_uploaded = state.get("visa_uploaded", False)
    
    passport_data = state.get("passport_data", [])
    visa_data = state.get("visa_data", [])
    
    # Validate passport data (not just uploaded, but successfully extracted)
    passport_valid = False
    if passport_uploaded and passport_data:
        # Check if any passport has actual data (not just errors)
        passport_valid = any("error" not in p for p in passport_data)
    
    # Validate visa data
    visa_valid = False
    if visa_uploaded and visa_data:
        visa_valid = any("error" not in v for v in visa_data)
    
    logger.info(f"Document status - Passport: {passport_valid}, Visa: {visa_valid}")
    
    # Generate status HTML
    missing_documents = []
    if not passport_valid:
        missing_documents.append("passport")
    if not visa_valid:
        missing_documents.append("visa")
    
    if missing_documents:
        logger.info(f"⚠️ Missing documents: {missing_documents}")
        state["booking_html"] = generate_document_request_html(
            selected_package, 
            passport_valid, 
            visa_valid,
            passport_data if passport_valid else None,
            visa_data if visa_valid else None
        )
        state["booking_in_progress"] = True
        state["needs_followup"] = True
        state["followup_question"] = f"Please upload your {' and '.join(missing_documents)} to continue with the booking."
        state["current_node"] = "booking"
        return state
    
    # All documents verified - confirm booking
    logger.info("✅ All documents verified - confirming booking")
    booking_reference = generate_booking_reference()
    
    state["booking_confirmed"] = True
    state["booking_reference"] = booking_reference
    state["booking_html"] = generate_booking_confirmation_html(
        selected_package,
        passport_data,
        visa_data,
        booking_reference
    )
    state["booking_in_progress"] = False
    state["needs_followup"] = False
    state["current_node"] = "booking"
    
    logger.info(f"✅ Booking confirmed: {booking_reference}")
    logger.info("=" * 60)
    
    return state


def generate_booking_reference() -> str:
    """Generate unique booking reference number"""
    timestamp = datetime.now().strftime("%Y%m%d")
    unique_id = str(uuid.uuid4())[:8].upper()
    return f"BK{timestamp}{unique_id}"


def generate_package_selection_html(packages: list) -> str:
    """Generate HTML for package selection interface"""
    
    html_parts = ["""
    <style>
        .booking-container {
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }
        .booking-header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 24px;
            border-radius: 12px;
            margin-bottom: 24px;
            text-align: center;
        }
        .package-selection-card {
            background: white;
            border: 2px solid #e5e7eb;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 16px;
            transition: all 0.3s ease;
            cursor: pointer;
        }
        .package-selection-card:hover {
            border-color: #667eea;
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.15);
            transform: translateY(-2px);
        }
        .package-selection-card.optimal {
            border-color: #10b981;
            background: linear-gradient(to right, #ecfdf5, #ffffff);
        }
        .optimal-badge {
            background: #10b981;
            color: white;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.85em;
            font-weight: 600;
            display: inline-block;
            margin-left: 12px;
        }
        .package-summary {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-top: 16px;
        }
        .summary-item {
            display: flex;
            flex-direction: column;
        }
        .summary-label {
            font-size: 0.85em;
            color: #6b7280;
            margin-bottom: 4px;
        }
        .summary-value {
            font-weight: 600;
            color: #111827;
        }
        .instruction-box {
            background: #eff6ff;
            border: 1px solid #bfdbfe;
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 24px;
        }
    </style>
    
    <div class="booking-container">
        <div class="booking-header">
            <h2 style="margin: 0 0 8px 0; font-size: 28px;">📦 Select Your Travel Package</h2>
            <p style="margin: 0; opacity: 0.9;">Choose the package that best fits your travel needs</p>
        </div>
        
        <div class="instruction-box">
            <p style="margin: 0; color: #1e40af; font-weight: 500;">
                💡 <strong>How to book:</strong> Reply with the package number you'd like to book (e.g., "book package 1" or just "package 1")
            </p>
        </div>
    """]
    
    for pkg in packages:
        pkg_id = pkg.get("package_id", 0)
        is_optimal = pkg.get("is_optimal", False)
        travel_dates = pkg.get("travel_dates", {})
        pricing = pkg.get("pricing", {})
        hotels = pkg.get("hotels", {})
        flight_offer = pkg.get("flight_offer", {})
        
        duration = travel_dates.get("duration_nights", "N/A")
        checkin = travel_dates.get("checkin", "N/A")
        checkout = travel_dates.get("checkout", "N/A")
        
        flight_price = pricing.get("flight_price", 0)
        flight_currency = pricing.get("flight_currency", "")
        hotel_price = hotels.get("min_price", 0)
        hotel_currency = hotels.get("currency", "N/A")
        available_hotels = hotels.get("available_count", 0)
        
        # Get flight summary
        summary = flight_offer.get("summary", {})
        outbound = summary.get("outbound", {})
        stops = outbound.get("stops", 0)
        stops_text = "Direct flight" if stops == 0 else f"{stops} stop(s)"
        
        card_class = "package-selection-card optimal" if is_optimal else "package-selection-card"
        
        html_parts.append(f"""
        <div class="{card_class}">
            <h3 style="margin: 0 0 16px 0; color: #111827; font-size: 20px;">
                Package {pkg_id}
                {f'<span class="optimal-badge">⭐ Best Value</span>' if is_optimal else ''}
            </h3>
            
            <div class="package-summary">
                <div class="summary-item">
                    <span class="summary-label">📅 Duration</span>
                    <span class="summary-value">{duration} night{'s' if duration != 1 else ''}</span>
                </div>
                <div class="summary-item">
                    <span class="summary-label">📆 Dates</span>
                    <span class="summary-value">{checkin} to {checkout}</span>
                </div>
                <div class="summary-item">
                    <span class="summary-label">✈️ Flight</span>
                    <span class="summary-value">{flight_price:,.2f} {flight_currency}</span>
                </div>
                <div class="summary-item">
                    <span class="summary-label">🏨 Hotels from</span>
                    <span class="summary-value">{hotel_price:,.2f} {hotel_currency}</span>
                </div>
                <div class="summary-item">
                    <span class="summary-label">🛫 Flight Type</span>
                    <span class="summary-value">{stops_text}</span>
                </div>
                <div class="summary-item">
                    <span class="summary-label">🏨 Hotels Available</span>
                    <span class="summary-value">{available_hotels} options</span>
                </div>
            </div>
        </div>
        """)
    
    html_parts.append("</div>")
    
    return "".join(html_parts)


def generate_document_request_html(package: dict, passport_valid: bool, visa_valid: bool, 
                                   passport_data: list = None, visa_data: list = None) -> str:
    """Generate HTML showing selected package and requesting missing documents"""
    
    pkg_id = package.get("package_id", 0)
    travel_dates = package.get("travel_dates", {})
    pricing = package.get("pricing", {})
    
    checkin = travel_dates.get("checkin", "N/A")
    checkout = travel_dates.get("checkout", "N/A")
    duration = travel_dates.get("duration_nights", "N/A")
    flight_price = pricing.get("flight_price", 0)
    flight_currency = pricing.get("flight_currency", "")
    
    html = f"""
    <style>
        .booking-container {{
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }}
        .selected-package {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 24px;
            border-radius: 12px;
            margin-bottom: 24px;
        }}
        .document-status {{
            background: white;
            border: 2px solid #e5e7eb;
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 16px;
        }}
        .status-item {{
            display: flex;
            align-items: center;
            padding: 16px;
            border-radius: 8px;
            margin-bottom: 12px;
        }}
        .status-item.complete {{
            background: #ecfdf5;
            border: 1px solid #10b981;
        }}
        .status-item.incomplete {{
            background: #fef2f2;
            border: 1px solid #ef4444;
        }}
        .status-icon {{
            font-size: 24px;
            margin-right: 16px;
        }}
        .warning-box {{
            background: #fef3c7;
            border: 2px solid #f59e0b;
            border-radius: 8px;
            padding: 20px;
            margin-top: 16px;
        }}
    </style>
    
    <div class="booking-container">
        <div class="selected-package">
            <h2 style="margin: 0 0 8px 0; font-size: 24px;">✅ Package {pkg_id} Selected</h2>
            <p style="margin: 0; opacity: 0.9; font-size: 14px;">
                {duration} nights: {checkin} to {checkout} • Flight: {flight_price:,.2f} {flight_currency}
            </p>
        </div>
        
        <div class="document-status">
            <h3 style="margin: 0 0 20px 0; color: #111827;">📋 Document Verification Status</h3>
            
            <div class="status-item {'complete' if passport_valid else 'incomplete'}">
                <span class="status-icon">{'✅' if passport_valid else '❌'}</span>
                <div style="flex: 1;">
                    <div style="font-weight: 600; color: #111827; margin-bottom: 4px;">Passport</div>
                    <div style="font-size: 0.9em; color: #6b7280;">
                        {f'Verified ({len(passport_data)} document(s))' if passport_valid else 'Not uploaded or invalid'}
                    </div>
                </div>
            </div>
            
            <div class="status-item {'complete' if visa_valid else 'incomplete'}">
                <span class="status-icon">{'✅' if visa_valid else '❌'}</span>
                <div style="flex: 1;">
                    <div style="font-weight: 600; color: #111827; margin-bottom: 4px;">Visa</div>
                    <div style="font-size: 0.9em; color: #6b7280;">
                        {f'Verified ({len(visa_data)} document(s))' if visa_valid else 'Not uploaded or invalid'}
                    </div>
                </div>
            </div>
        </div>
        
        <div class="warning-box">
            <h4 style="margin: 0 0 12px 0; color: #92400e; font-size: 18px;">⚠️ Action Required</h4>
            <p style="margin: 0 0 12px 0; color: #78350f; line-height: 1.6;">
                To complete your booking, please upload the following document(s):
            </p>
            <ul style="margin: 0; padding-left: 20px; color: #78350f;">
                {f'<li><strong>Passport</strong> - Valid travel document required</li>' if not passport_valid else ''}
                {f'<li><strong>Visa</strong> - Valid visa document required</li>' if not visa_valid else ''}
            </ul>
            <p style="margin: 16px 0 0 0; color: #78350f; font-size: 0.9em; font-style: italic;">
                Once you upload the required documents, I'll automatically verify them and confirm your booking.
            </p>
        </div>
    </div>
    """
    
    return html


def generate_booking_confirmation_html(package: dict, passport_data: list, visa_data: list, booking_ref: str) -> str:
    """Generate HTML for confirmed booking"""
    
    pkg_id = package.get("package_id", 0)
    travel_dates = package.get("travel_dates", {})
    pricing = package.get("pricing", {})
    hotels = package.get("hotels", {})
    
    checkin = travel_dates.get("checkin", "N/A")
    checkout = travel_dates.get("checkout", "N/A")
    duration = travel_dates.get("duration_nights", "N/A")
    flight_price = pricing.get("flight_price", 0)
    flight_currency = pricing.get("flight_currency", "")
    hotel_price = hotels.get("min_price", 0)
    hotel_currency = hotels.get("currency", "N/A")
    
    # Get traveler info from passport
    traveler_name = "N/A"
    passport_number = "N/A"
    if passport_data and len(passport_data) > 0:
        first_passport = passport_data[0]
        if "error" not in first_passport:
            traveler_name = first_passport.get("full_name", "N/A")
            passport_number = first_passport.get("passport_number", "N/A")
    
    html = f"""
    <style>
        .booking-container {{
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }}
        .confirmation-header {{
            background: linear-gradient(135deg, #10b981 0%, #059669 100%);
            color: white;
            padding: 32px;
            border-radius: 12px;
            margin-bottom: 24px;
            text-align: center;
        }}
        .booking-ref {{
            background: rgba(255, 255, 255, 0.2);
            padding: 12px 24px;
            border-radius: 8px;
            display: inline-block;
            margin-top: 16px;
            font-family: monospace;
            font-size: 20px;
            font-weight: 700;
            letter-spacing: 2px;
        }}
        .info-card {{
            background: white;
            border: 1px solid #e5e7eb;
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 16px;
        }}
        .info-row {{
            display: flex;
            justify-content: space-between;
            padding: 12px 0;
            border-bottom: 1px solid #f3f4f6;
        }}
        .info-row:last-child {{
            border-bottom: none;
        }}
        .info-label {{
            color: #6b7280;
            font-weight: 500;
        }}
        .info-value {{
            color: #111827;
            font-weight: 600;
        }}
        .success-icon {{
            font-size: 64px;
            margin-bottom: 16px;
        }}
    </style>
    
    <div class="booking-container">
        <div class="confirmation-header">
            <div class="success-icon">🎉</div>
            <h2 style="margin: 0 0 8px 0; font-size: 32px;">Booking Confirmed!</h2>
            <p style="margin: 0; opacity: 0.9;">Your travel package has been successfully booked</p>
            <div class="booking-ref">{booking_ref}</div>
        </div>
        
        <div class="info-card">
            <h3 style="margin: 0 0 16px 0; color: #111827;">👤 Traveler Information</h3>
            <div class="info-row">
                <span class="info-label">Name</span>
                <span class="info-value">{traveler_name}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Passport Number</span>
                <span class="info-value">{passport_number}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Documents Verified</span>
                <span class="info-value">✅ Passport & Visa</span>
            </div>
        </div>
        
        <div class="info-card">
            <h3 style="margin: 0 0 16px 0; color: #111827;">📦 Package Details</h3>
            <div class="info-row">
                <span class="info-label">Package ID</span>
                <span class="info-value">Package {pkg_id}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Duration</span>
                <span class="info-value">{duration} night{'s' if duration != 1 else ''}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Check-in</span>
                <span class="info-value">{checkin}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Check-out</span>
                <span class="info-value">{checkout}</span>
            </div>
        </div>
        
        <div class="info-card">
            <h3 style="margin: 0 0 16px 0; color: #111827;">💰 Pricing Summary</h3>
            <div class="info-row">
                <span class="info-label">Flight</span>
                <span class="info-value">{flight_price:,.2f} {flight_currency}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Hotel (starting from)</span>
                <span class="info-value">{hotel_price:,.2f} {hotel_currency}</span>
            </div>
        </div>
        
        <div style="background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px; padding: 20px; text-align: center;">
            <p style="margin: 0; color: #1e40af; line-height: 1.6;">
                📧 A confirmation email has been sent to your registered email address.<br>
                Please keep your booking reference <strong>{booking_ref}</strong> for future correspondence.
            </p>
        </div>
    </div>
    """
    
    return html


def generate_error_html(message: str) -> str:
    """Generate error HTML"""
    return f"""
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: #fef2f2; border: 2px solid #ef4444; border-radius: 12px; padding: 24px; text-align: center;">
            <div style="font-size: 48px; margin-bottom: 16px;">❌</div>
            <h3 style="margin: 0 0 12px 0; color: #991b1b; font-size: 20px;">Booking Error</h3>
            <p style="margin: 0; color: #7f1d1d; line-height: 1.6;">{message}</p>
        </div>
    </div>
    """