"""
Nodes/booking_node.py
Handles package booking with passport and visa verification
Clean, professional HTML outputs without colors
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
    
    # DEBUG: Log critical state information
    logger.info(f"Thread ID: {thread_id}")
    logger.info(f"Selected Package ID: {selected_package_id}")
    logger.info(f"Travel Packages Count: {len(travel_packages)}")
    if travel_packages:
        logger.info(f"First Package Preview: {travel_packages[0].get('package_id', 'N/A')}")
    else:
        logger.error("❌ NO TRAVEL PACKAGES IN STATE!")
    logger.info(f"Passport Uploaded: {state.get('passport_uploaded', False)}")
    logger.info(f"Visa Uploaded: {state.get('visa_uploaded', False)}")
    logger.info(f"Booking In Progress: {state.get('booking_in_progress', False)}")
    logger.info(f"State Keys: {list(state.keys())[:10]}...")
    
    # Check if we have packages to book
    if not travel_packages:
        logger.error("❌ NO TRAVEL PACKAGES FOUND IN STATE!")
        logger.error(f"Available state keys: {list(state.keys())}")
        state["booking_error"] = "No travel packages available for booking"
        state["booking_html"] = generate_error_html(
            "No packages available. Please search for travel packages first."
        )
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
        logger.error(f"❌ Package {selected_package_id} not found in {len(travel_packages)} packages")
        state["booking_error"] = f"Package {selected_package_id} not found"
        state["booking_html"] = generate_error_html(
            f"Package {selected_package_id} not found. Please select a valid package."
        )
        state["current_node"] = "booking"
        return state
    
    state["selected_package"] = selected_package
    logger.info(f"✓ Package {selected_package_id} selected")
    
    # Check document uploads
    passport_uploaded = state.get("passport_uploaded", False)
    visa_uploaded = state.get("visa_uploaded", False)
    
    passport_data = state.get("passport_data", [])
    visa_data = state.get("visa_data", [])
    
    logger.info(f"Document data - Passports: {len(passport_data)}, Visas: {len(visa_data)}")
    
    # Validate passport data
    passport_valid = False
    if passport_uploaded and passport_data:
        passport_valid = any("error" not in p for p in passport_data)
        logger.info(f"Passport validation: {passport_valid} ({len(passport_data)} documents)")
    
    # Validate visa data
    visa_valid = False
    if visa_uploaded and visa_data:
        visa_valid = any("error" not in v for v in visa_data)
        logger.info(f"Visa validation: {visa_valid} ({len(visa_data)} documents)")
    
    logger.info(f"Final document status - Passport: {passport_valid}, Visa: {visa_valid}")
    
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
    """Generate clean, professional HTML for package selection"""
    
    html_parts = ["""
    <style>
        .booking-container {
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
        }
        .section-header {
            border-bottom: 2px solid #000;
            padding-bottom: 12px;
            margin-bottom: 24px;
        }
        .section-title {
            font-size: 24px;
            font-weight: 600;
            margin: 0;
            letter-spacing: -0.5px;
        }
        .section-subtitle {
            font-size: 14px;
            margin: 4px 0 0 0;
            opacity: 0.7;
        }
        .info-box {
            border: 1px solid #ddd;
            padding: 16px;
            margin-bottom: 24px;
            background: #fafafa;
        }
        .info-box p {
            margin: 0;
            font-size: 14px;
        }
        .package-card {
            border: 1px solid #ddd;
            padding: 20px;
            margin-bottom: 16px;
            position: relative;
        }
        .package-card.optimal {
            border: 2px solid #000;
        }
        .package-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
            padding-bottom: 12px;
            border-bottom: 1px solid #eee;
        }
        .package-title {
            font-size: 18px;
            font-weight: 600;
            margin: 0;
        }
        .optimal-badge {
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            padding: 4px 8px;
            border: 1px solid #000;
            background: #000;
            color: #fff;
        }
        .package-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
        }
        .detail-item {
            display: flex;
            flex-direction: column;
        }
        .detail-label {
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            opacity: 0.6;
            margin-bottom: 4px;
            font-weight: 500;
        }
        .detail-value {
            font-size: 15px;
            font-weight: 500;
        }
    </style>
    
    <div class="booking-container">
        <div class="section-header">
            <h1 class="section-title">Select Travel Package</h1>
            <p class="section-subtitle">Choose the package that best fits your needs</p>
        </div>
        
        <div class="info-box">
            <p><strong>How to book:</strong> Reply with the package number (e.g., "book package 1" or "package 1")</p>
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
        
        card_class = "package-card optimal" if is_optimal else "package-card"
        
        html_parts.append(f"""
        <div class="{card_class}">
            <div class="package-header">
                <h2 class="package-title">Package {pkg_id}</h2>
                {f'<span class="optimal-badge">Best Value</span>' if is_optimal else ''}
            </div>
            
            <div class="package-grid">
                <div class="detail-item">
                    <span class="detail-label">Duration</span>
                    <span class="detail-value">{duration} night{'s' if duration != 1 else ''}</span>
                </div>
                <div class="detail-item">
                    <span class="detail-label">Travel Dates</span>
                    <span class="detail-value">{checkin} to {checkout}</span>
                </div>
                <div class="detail-item">
                    <span class="detail-label">Flight Price</span>
                    <span class="detail-value">{flight_price:,.2f} {flight_currency}</span>
                </div>
                <div class="detail-item">
                    <span class="detail-label">Hotels From</span>
                    <span class="detail-value">{hotel_price:,.2f} {hotel_currency}</span>
                </div>
                <div class="detail-item">
                    <span class="detail-label">Flight Type</span>
                    <span class="detail-value">{stops_text}</span>
                </div>
                <div class="detail-item">
                    <span class="detail-label">Hotels Available</span>
                    <span class="detail-value">{available_hotels} options</span>
                </div>
            </div>
        </div>
        """)
    
    html_parts.append("</div>")
    
    return "".join(html_parts)


def generate_document_request_html(package: dict, passport_valid: bool, visa_valid: bool, 
                                   passport_data: list = None, visa_data: list = None) -> str:
    """Generate clean HTML showing selected package and requesting documents"""
    
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
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
        }}
        .section-header {{
            border-bottom: 2px solid #000;
            padding-bottom: 12px;
            margin-bottom: 24px;
        }}
        .section-title {{
            font-size: 24px;
            font-weight: 600;
            margin: 0;
            letter-spacing: -0.5px;
        }}
        .section-subtitle {{
            font-size: 14px;
            margin: 4px 0 0 0;
            opacity: 0.7;
        }}
        .info-card {{
            border: 1px solid #ddd;
            padding: 20px;
            margin-bottom: 16px;
        }}
        .card-title {{
            font-size: 16px;
            font-weight: 600;
            margin: 0 0 16px 0;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            font-size: 12px;
        }}
        .status-list {{
            list-style: none;
            padding: 0;
            margin: 0;
        }}
        .status-item {{
            display: flex;
            align-items: center;
            padding: 12px 0;
            border-bottom: 1px solid #eee;
        }}
        .status-item:last-child {{
            border-bottom: none;
        }}
        .status-icon {{
            margin-right: 12px;
            font-size: 18px;
        }}
        .status-content {{
            flex: 1;
        }}
        .status-title {{
            font-weight: 600;
            margin: 0 0 4px 0;
        }}
        .status-description {{
            font-size: 13px;
            opacity: 0.7;
            margin: 0;
        }}
        .alert-box {{
            border: 2px solid #000;
            padding: 20px;
            margin-top: 16px;
            background: #fafafa;
        }}
        .alert-title {{
            font-weight: 600;
            margin: 0 0 12px 0;
            font-size: 16px;
        }}
        .alert-text {{
            margin: 0 0 12px 0;
            font-size: 14px;
        }}
        .required-list {{
            margin: 12px 0;
            padding-left: 20px;
        }}
        .required-list li {{
            margin-bottom: 8px;
        }}
    </style>
    
    <div class="booking-container">
        <div class="section-header">
            <h1 class="section-title">Package {pkg_id} Selected</h1>
            <p class="section-subtitle">{duration} nights: {checkin} to {checkout} • Flight: {flight_price:,.2f} {flight_currency}</p>
        </div>
        
        <div class="info-card">
            <h2 class="card-title">Document Verification Status</h2>
            
            <ul class="status-list">
                <li class="status-item">
                    <span class="status-icon">{'✓' if passport_valid else '✗'}</span>
                    <div class="status-content">
                        <p class="status-title">Passport</p>
                        <p class="status-description">
                            {f'Verified ({len(passport_data)} document(s))' if passport_valid else 'Not uploaded or invalid'}
                        </p>
                    </div>
                </li>
                
                <li class="status-item">
                    <span class="status-icon">{'✓' if visa_valid else '✗'}</span>
                    <div class="status-content">
                        <p class="status-title">Visa</p>
                        <p class="status-description">
                            {f'Verified ({len(visa_data)} document(s))' if visa_valid else 'Not uploaded or invalid'}
                        </p>
                    </div>
                </li>
            </ul>
        </div>
        
        <div class="alert-box">
            <h3 class="alert-title">Action Required</h3>
            <p class="alert-text">To complete your booking, please upload the following document(s):</p>
            <ul class="required-list">
                {f'<li><strong>Passport</strong> — Valid travel document required</li>' if not passport_valid else ''}
                {f'<li><strong>Visa</strong> — Valid visa document required</li>' if not visa_valid else ''}
            </ul>
            <p class="alert-text" style="font-size: 13px; opacity: 0.8; font-style: italic; margin-top: 16px;">
                Once you upload the required documents, the system will automatically verify them and confirm your booking.
            </p>
        </div>
    </div>
    """
    
    return html


def generate_booking_confirmation_html(package: dict, passport_data: list, visa_data: list, booking_ref: str) -> str:
    """Generate clean HTML for booking confirmation"""
    
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
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
        }}
        .confirmation-banner {{
            border: 3px solid #000;
            padding: 32px;
            margin-bottom: 24px;
            text-align: center;
            background: #fafafa;
        }}
        .confirmation-icon {{
            font-size: 48px;
            margin-bottom: 16px;
        }}
        .confirmation-title {{
            font-size: 28px;
            font-weight: 700;
            margin: 0 0 8px 0;
            letter-spacing: -0.5px;
        }}
        .confirmation-subtitle {{
            font-size: 14px;
            margin: 0 0 20px 0;
            opacity: 0.7;
        }}
        .booking-reference {{
            font-family: 'Courier New', monospace;
            font-size: 20px;
            font-weight: 700;
            letter-spacing: 2px;
            padding: 12px 24px;
            border: 2px solid #000;
            display: inline-block;
            background: #fff;
        }}
        .info-section {{
            border: 1px solid #ddd;
            padding: 20px;
            margin-bottom: 16px;
        }}
        .section-title {{
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin: 0 0 16px 0;
            padding-bottom: 8px;
            border-bottom: 1px solid #ddd;
        }}
        .info-table {{
            width: 100%;
            border-collapse: collapse;
        }}
        .info-row {{
            display: flex;
            justify-content: space-between;
            padding: 10px 0;
            border-bottom: 1px solid #eee;
        }}
        .info-row:last-child {{
            border-bottom: none;
        }}
        .info-label {{
            opacity: 0.6;
            font-size: 14px;
        }}
        .info-value {{
            font-weight: 600;
            font-size: 14px;
        }}
        .notice-box {{
            border: 1px solid #ddd;
            padding: 20px;
            text-align: center;
            background: #fafafa;
            margin-top: 16px;
        }}
        .notice-box p {{
            margin: 0;
            font-size: 13px;
            line-height: 1.6;
        }}
    </style>
    
    <div class="booking-container">
        <div class="confirmation-banner">
            <div class="confirmation-icon">✓</div>
            <h1 class="confirmation-title">Booking Confirmed</h1>
            <p class="confirmation-subtitle">Your travel package has been successfully booked</p>
            <div class="booking-reference">{booking_ref}</div>
        </div>
        
        <div class="info-section">
            <h2 class="section-title">Traveler Information</h2>
            <div class="info-row">
                <span class="info-label">Full Name</span>
                <span class="info-value">{traveler_name}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Passport Number</span>
                <span class="info-value">{passport_number}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Documents</span>
                <span class="info-value">Passport & Visa Verified</span>
            </div>
        </div>
        
        <div class="info-section">
            <h2 class="section-title">Package Details</h2>
            <div class="info-row">
                <span class="info-label">Package ID</span>
                <span class="info-value">Package {pkg_id}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Duration</span>
                <span class="info-value">{duration} night{'s' if duration != 1 else ''}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Check-in Date</span>
                <span class="info-value">{checkin}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Check-out Date</span>
                <span class="info-value">{checkout}</span>
            </div>
        </div>
        
        <div class="info-section">
            <h2 class="section-title">Pricing Summary</h2>
            <div class="info-row">
                <span class="info-label">Flight</span>
                <span class="info-value">{flight_price:,.2f} {flight_currency}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Hotel (starting from)</span>
                <span class="info-value">{hotel_price:,.2f} {hotel_currency}</span>
            </div>
        </div>
        
        <div class="notice-box">
            <p>
                A confirmation email has been sent to your registered email address.<br>
                Please keep your booking reference <strong>{booking_ref}</strong> for future correspondence.
            </p>
        </div>
    </div>
    """
    
    return html


def generate_error_html(message: str) -> str:
    """Generate clean error HTML"""
    return f"""
    <style>
        .error-container {{
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
        }}
        .error-box {{
            border: 2px solid #000;
            padding: 32px;
            text-align: center;
            background: #fafafa;
        }}
        .error-icon {{
            font-size: 48px;
            margin-bottom: 16px;
        }}
        .error-title {{
            font-size: 20px;
            font-weight: 600;
            margin: 0 0 12px 0;
        }}
        .error-message {{
            margin: 0;
            font-size: 14px;
            line-height: 1.6;
        }}
    </style>
    
    <div class="error-container">
        <div class="error-box">
            <div class="error-icon">✗</div>
            <h3 class="error-title">Booking Error</h3>
            <p class="error-message">{message}</p>
        </div>
    </div>
    """