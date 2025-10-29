def build_compact_summary_prompt(compressed_packages):
    """
    Build a compact prompt using compressed package data.
    This keeps prompt size manageable even with 7 packages.
    Includes optimal package identification and savings information.
    """
    
    # Filter out None packages
    valid_packages = [p for p in compressed_packages if p is not None]
    
    if not valid_packages:
        return "No valid packages to summarize."
    
    # Identify optimal package
    optimal_package = None
    for pkg in valid_packages:
        if pkg.get("is_optimal", False):
            optimal_package = pkg
            break
    
    # Build package summaries
    package_descriptions = []
    for pkg in valid_packages:
        pkg_id = pkg.get("package_id", "?")
        search_date = pkg.get("search_date", "")
        nights = pkg.get("nights", 0)
        is_optimal = pkg.get("is_optimal", False)
        savings_vs_optimal = pkg.get("savings_vs_optimal")
        
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
        
        # Build package description with optimal/savings info
        package_desc = f"Package {pkg_id} (searched {search_date}): {nights} nights, {flight_summary}, {hotel_summary}"
        
        if is_optimal:
            package_desc += " [⭐ BEST VALUE - Optimal price and convenience]"
        elif savings_vs_optimal:
            total_diff = savings_vs_optimal.get("total_difference", 0)
            percentage_more = savings_vs_optimal.get("percentage_more", 0)
            if total_diff > 0:
                package_desc += f" [+{percentage_more:.0f}% more expensive than optimal]"
        
        package_descriptions.append(package_desc)
    
    # Build final prompt
    packages_text = "\n".join(package_descriptions)
    
    # Add optimal package context
    optimal_context = ""
    if optimal_package:
        optimal_id = optimal_package.get("package_id")
        optimal_context = f"\n\nIMPORTANT: Package {optimal_id} has been identified as the BEST VALUE option based on lowest total price (flight + hotel), convenience (direct flights preferred), and hotel availability. This is the recommended choice for most travelers."
    
    prompt = f"""<|SYSTEM|>
You are a helpful travel assistant.
Based on the following {len(valid_packages)} flight+hotel package options, provide a concise, friendly summary and recommendation.
Make it brief and conversational, as strings only (no markdown or emojis).

PACKAGE OPTIONS:
{packages_text}{optimal_context}

Important details to consider:
- Flight routes, departure/arrival times, durations, and number of stops
- Direct flights vs flights with layovers (direct flights are more convenient)
- Price differences between packages (both flight and hotel costs)
- The BEST VALUE package offers the optimal balance of price and convenience
- Other packages may cost more but could offer different departure times
- Hotel availability and pricing
- Overall trip duration

Provide a 4-5 sentence summary highlighting:
1. Clearly recommend the BEST VALUE package (the optimal one) and explain why it's the best choice (e.g., "Package X offers the best value with direct flights for only...")
2. Mention the total cost for the optimal package (flight + hotel starting price)
3. Note any key advantages (e.g., direct flights, convenient times, good hotel availability)
4. Briefly mention if other packages are available at higher prices and what trade-offs they might offer (e.g., "Package Y costs 15% more but departs 2 hours earlier")
5. End with encouragement to explore the details

Keep it natural and helpful - write as if talking to a friend planning a trip. Focus on helping them understand why the optimal package is recommended while acknowledging alternatives exist.
<|USER|>Return the response as plain text, with no markdown or emojis.<|END|>"""
    
    return prompt