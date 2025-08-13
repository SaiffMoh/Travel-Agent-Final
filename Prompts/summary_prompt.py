import json

def summary_prompt(package1, package2, package3):
    return f"""
    You are a helpful travel assistant.
    Based on the following 3 flight+hotel package options, provide a concise, friendly summary and recommendation.
    Make it brief and conversational, as strings only (no markdown or emojis).

    Package1 offers:
    {json.dumps(package1, indent=2)}

    Package2 offers:
    {json.dumps(package2, indent=2)}

    Package3 offers:
    {json.dumps(package3, indent=2)}

    Please provide:
    1. A short, enthusiastic summary of the available packages.
    2. Your recommendation for the best overall package considering:
       - Price
       - Flight timing & duration
       - Hotel quality & amenities
       - Overall convenience
    3. Clearly mention the cheapest option.
    4. Any helpful travel tips or considerations (e.g., layovers, cancellation policies, hidden fees).

    Keep it conversational and helpful.
    Start with something like: "Great! I found 3 exciting packages for your trip..."
    """