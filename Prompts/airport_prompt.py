def airport_prompt(location):
    return f"""Convert this city or location to its primary IATA airport code: "{location}"

Rules:
- Return ONLY the 3-letter IATA airport code
- For cities with multiple airports, return the main international airport
- Examples: "New York" → "JFK", "Los Angeles" → "LAX", "London" → "LHR", "Paris" → "CDG"

Answer must be plain text (not JSON).

Airport code:"""