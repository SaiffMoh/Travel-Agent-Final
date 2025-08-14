def get_cabin_type_prompt(cabin: str):
    return f"""
    You are a travel booking expert.
    Your task is to return the standard cabin type that matches the given input.
    The possible cabin types are:
    - ECONOMY
    - PREMIUM_ECONOMY
    - BUSINESS
    - FIRST_CLASS

    If the cabin type is unclear or misspelled, guess the most likely match.
    Return ONLY one of the above cabin types exactly as written, with no extra words.
    Answer must be plain text (not JSON).

    Cabin type input: {cabin}
    """