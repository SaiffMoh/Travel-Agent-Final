def build_compact_summary_prompt(compressed_packages):
    """
    Build a compact prompt using compressed package data.
    This keeps prompt size manageable even with 7 packages.
    """
    
    # Filter out None packages
    valid_packages = [p for p in compressed_packages if p is not None]
    
    if not valid_packages:
        return "No valid packages to summarize."
    
    # Build package summaries
    package_descriptions = []
    for pkg in valid_packages:
        pkg_id = pkg.get("package_id", "?")
        search_date = pkg.get("search_date", "")
        nights = pkg.get("nights", 0)
        
        flight = pkg.get("flight", {})
        hotels = pkg.get("hotels", {})
        
        # Flight summary
        if flight:
            outbound = flight.get("outbound", {})
            return_flight = flight.get("return", {})
            flight_price = flight.get("price", 0)
            flight_curr = flight.get("currency", "EGP")
            
            # Build detailed flight description
            from_airport = outbound.get('from', '')
            to_airport = outbound.get('to', '')
            dep_date = outbound.get('departure_time', '')[:10]  # Just the date
            dep_time = outbound.get('departure_time', '')[11:16] if len(outbound.get('departure_time', '')) > 11 else ''  # Just HH:MM
            arr_time = outbound.get('arrival_time', '')[11:16] if len(outbound.get('arrival_time', '')) > 11 else ''
            outbound_duration = outbound.get('duration', '')
            outbound_stops = outbound.get('stops', 0)
            
            flight_summary = f"{from_airport}→{to_airport}"
            if dep_date:
                flight_summary += f" on {dep_date}"
            if dep_time and arr_time:
                flight_summary += f" ({dep_time}-{arr_time})"
            if outbound_duration:
                flight_summary += f" {outbound_duration}"
            
            stops_text = "direct" if outbound_stops == 0 else f"{outbound_stops} stop{'s' if outbound_stops > 1 else ''}"
            flight_summary += f" {stops_text}"
            
            # Add return flight info if exists
            if return_flight:
                ret_date = return_flight.get('departure_time', '')[:10]
                ret_dep_time = return_flight.get('departure_time', '')[11:16] if len(return_flight.get('departure_time', '')) > 11 else ''
                ret_arr_time = return_flight.get('arrival_time', '')[11:16] if len(return_flight.get('arrival_time', '')) > 11 else ''
                return_duration = return_flight.get('duration', '')
                return_stops = return_flight.get('stops', 0)
                
                return_stops_text = "direct" if return_stops == 0 else f"{return_stops} stop{'s' if return_stops > 1 else ''}"
                
                flight_summary += f" | Return {ret_date}"
                if ret_dep_time and ret_arr_time:
                    flight_summary += f" ({ret_dep_time}-{ret_arr_time})"
                if return_duration:
                    flight_summary += f" {return_duration}"
                flight_summary += f" {return_stops_text}"
            
            flight_summary += f" • {flight_price:,.0f} {flight_curr}"
            
            if flight.get('alternatives', 1) > 1:
                flight_summary += f" ({flight.get('alternatives')} options)"
        else:
            flight_summary = "No flight data"
        
        # Hotel summary
        hotel_count = hotels.get("total_available", 0)
        hotel_price = hotels.get("min_price", 0)
        hotel_curr = hotels.get("currency", "N/A")
        hotel_summary = f"{hotel_count} hotels from {hotel_price:,.0f} {hotel_curr}"
        
        package_descriptions.append(
            f"Package {pkg_id} (searched {search_date}): {nights} nights, {flight_summary}, {hotel_summary}"
        )
    
    # Build final prompt
    packages_text = "\n".join(package_descriptions)
    
    prompt = f"""<|SYSTEM|>
You are a helpful travel assistant.
Based on the following {len(valid_packages)} flight+hotel package options, provide a concise, friendly summary and recommendation.
Make it brief and conversational, as strings only (no markdown or emojis).

PACKAGE OPTIONS:
{packages_text}

Important details to consider:
- Flight routes, departure/arrival times, durations, and number of stops
- Direct flights vs flights with layovers
- Price differences between packages
- Hotel availability and pricing
- Overall trip duration

Provide a 3-4 sentence summary highlighting:
1. The best value option considering price, flight times, and stops
2. Key trade-offs between packages (e.g., "Package 2 is slightly cheaper but has a layover")
3. Which package you'd recommend and why (consider convenience vs price)

Keep it natural and helpful - write as if talking to a friend planning a trip.
<|USER|>Return the response as plain text, with no markdown or emojis.<|END|>"""
    
    return prompt