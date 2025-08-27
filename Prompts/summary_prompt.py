import json

def summary_prompt(package1, package2, package3, package4, package5, package6, package7):
    packages = [package1, package2, package3, package4, package5, package6, package7]
    package_offers = []
    for i, pkg in enumerate(packages):
        if pkg:
            api_hotels = pkg.get("hotels", {}).get("api_hotels", {})
            company_hotels = pkg.get("hotels", {}).get("company_hotels", {})
            package_offers.append(f"""
Package{i+1} offers:
Flights: {json.dumps(pkg.get("flight_offers", []), indent=2)}
API Hotels: {json.dumps(api_hotels, indent=2)}
Company Preferred Hotels: {json.dumps(company_hotels, indent=2)}
""")
        else:
            package_offers.append(f"Package{i+1} offers:\nNot available")
    
    return f"""
You are a helpful travel assistant.
Based on the following 7 flight+hotel package options, provide a concise, friendly summary and recommendation.
Make it brief and conversational, as strings only (no markdown or emojis).

{chr(10).join(package_offers)}

Please provide:
1. A short, enthusiastic summary of the available packages.
2. Your recommendation for the best overall package considering:
   - Price
   - Flight timing & duration
   - Hotel quality & amenities
   - Overall convenience
3. Clearly mention the cheapest option, comparing API hotels and company preferred hotels if both are available.
   If company preferred hotels exist, note their price and compare to API hotels, highlighting if Amadeus found better deals.
4. Any helpful travel tips or considerations (e.g., layovers, cancellation policies, hidden fees, or company hotel notes).

Keep it conversational and helpful.
Start with something like: "Great! I found up to 7 exciting packages for your trip..."

Answer must be plain text (not JSON).
"""