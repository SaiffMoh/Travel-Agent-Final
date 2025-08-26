from Models.TravelSearchState import TravelSearchState
import requests
from collections import defaultdict
import time

def get_hotel_offers_node(state: TravelSearchState) -> TravelSearchState:
    """Get hotel offers for 3 durations sequentially using extracted flight dates."""
    url = "https://test.api.amadeus.com/v3/shopping/hotel-offers"
    headers = {
        "Authorization": f"Bearer {state['access_token']}",
        "Content-Type": "application/json"
    }

    hotel_ids = state.get("hotel_id", [])

    if not hotel_ids:
        print("No hotel IDs available for hotel search")
        state["hotel_offers_duration_1"] = []
        state["hotel_offers_duration_2"] = []
        state["hotel_offers_duration_3"] = []
        return state

    # Prepare requests for up to 3 durations
    duration_requests = []
    for day in [1, 2, 3]:
        checkin_key = f"checkin_date_day_{day}"
        checkout_key = f"checkout_date_day_{day}"
        checkin = state.get(checkin_key)
        checkout = state.get(checkout_key)

        duration_requests.append({
            "duration_number": day,
            "checkin": checkin,
            "checkout": checkout
        })

    def fetch_hotels_for_duration(duration_info):
        """Fetch hotel offers for a specific duration."""
        duration_num = duration_info["duration_number"]
        checkin = duration_info["checkin"]
        checkout = duration_info["checkout"]

        if not checkin or not checkout:
            print(f"No check-in or check-out dates for duration {duration_num}")
            return duration_num, []

        params = {
            "hotelIds": ",".join(hotel_ids),
            "checkInDate": checkin,
            "checkOutDate": checkout,
            "currencyCode": "EGP"
        }

        try:
            print(f"Fetching hotel offers for duration {duration_num}: {checkin} to {checkout}")
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            hotel_offers = data.get("data", [])

            # Process hotel offers to find cheapest by room type
            processed_offers = process_hotel_offers(hotel_offers)
            print(f"Found {len(processed_offers)} hotel offers for duration {duration_num}")

            return duration_num, processed_offers

        except requests.exceptions.HTTPError as e:
            if response.status_code == 429:
                print(f"Rate limit exceeded for duration {duration_num}. Waiting before retrying...")
                time.sleep(2)  # Wait 2 seconds before retrying
                try:
                    response = requests.get(url, headers=headers, params=params, timeout=10)
                    response.raise_for_status()
                    data = response.json()
                    hotel_offers = data.get("data", [])
                    processed_offers = process_hotel_offers(hotel_offers)
                    print(f"Found {len(processed_offers)} hotel offers for duration {duration_num} after retry")
                    return duration_num, processed_offers
                except Exception as retry_e:
                    print(f"Retry failed for duration {duration_num} ({checkin} to {checkout}): {retry_e}")
                    return duration_num, []
            else:
                print(f"Error getting hotel offers for duration {duration_num} ({checkin} to {checkout}): {e}")
                return duration_num, []
        except Exception as e:
            print(f"Error getting hotel offers for duration {duration_num} ({checkin} to {checkout}): {e}")
            return duration_num, []

    def process_hotel_offers(hotel_offers):
        """Process hotel offers to find cheapest offer by room type for each hotel."""
        processed = []

        for hotel in hotel_offers:
            hotel_info = {
                "hotel": hotel.get("hotel", {}),
                "available": hotel.get("available", True),
                "best_offers": []
            }

            if not hotel_info["available"]:
                processed.append(hotel_info)
                continue

            offers = hotel.get("offers", [])
            if not offers:
                processed.append(hotel_info)
                continue

            # Group offers by room type
            offers_by_room_type = defaultdict(list)

            for offer in offers:
                room_info = offer.get("room", {})
                room_type = room_info.get("type", "UNKNOWN")
                offers_by_room_type[room_type].append(offer)

            # Find cheapest offer for each room type
            for room_type, room_offers in offers_by_room_type.items():
                cheapest_offer = min(room_offers, key=lambda x: float(x.get("price", {}).get("total", float('inf'))))
                currency = cheapest_offer.get("price", {}).get("currency", "EGP")
                hotel_info["best_offers"].append({
                    "room_type": room_type,
                    "offer": cheapest_offer,
                    "currency": currency
                })

            # Sort by price (cheapest first)
            hotel_info["best_offers"].sort(key=lambda x: float(x["offer"].get("price", {}).get("total", float('inf'))))

            processed.append(hotel_info)

        # Sort hotels by their cheapest offer
        processed.sort(key=lambda x: (
            float(x["best_offers"][0]["offer"].get("price", {}).get("total", float('inf')))
            if x["best_offers"] else float('inf')
        ))

        return processed

    # Sequential hotel search across 3 durations
    for duration_info in duration_requests:
        duration_number, offers = fetch_hotels_for_duration(duration_info)

        # Save hotel offers by duration
        if duration_number == 1:
            state["hotel_offers_duration_1"] = offers
        elif duration_number == 2:
            state["hotel_offers_duration_2"] = offers
        elif duration_number == 3:
            state["hotel_offers_duration_3"] = offers
        
        # Add a small delay between requests to avoid rate limiting
        time.sleep(1)  # Wait 1 second between requests

    # Keep legacy format for compatibility (use first duration)
    state["hotel_offers"] = state.get("hotel_offers_duration_1", [])

    return state