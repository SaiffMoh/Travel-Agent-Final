from Models.TravelSearchState import TravelSearchState
from Utils.watson_config import llm  # Import Watsonx LLM client
from Prompts.summary_prompt import summary_prompt
import json
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def summarize_packages(state: TravelSearchState) -> TravelSearchState:
    """Generate LLM summary and recommendation for travel packages."""
    travel_packages = state.get("travel_packages", [])

    if not travel_packages or len(travel_packages) == 0:
        state["package_summary"] = "No travel packages found for your search. Please try different dates or destinations."
        return state

    packages_padded = travel_packages + [None] * (7 - len(travel_packages))
    package1, package2, package3, package4, package5, package6, package7 = packages_padded[:7]

    if not package1:
        state["package_summary"] = "No valid travel packages could be created. Please check your search criteria."
        return state

    try:
        llm_prompt = summary_prompt(package1, package2, package3, package4, package5, package6, package7)
        prompt = f"<|SYSTEM|>{llm_prompt}<|USER|>Return the response as plain text, with no markdown or emojis.<|END|>"
        logger.info(f"Watsonx summary prompt: {prompt[:500]}...")
        response = llm.generate(prompt=prompt)
        state["package_summary"] = response["results"][0]["generated_text"].strip()
        logger.info(f"Watsonx summary response: {state['package_summary']}")
    except Exception as e:
        logger.error(f"Error summarizing packages: {e}")
        fallback_summary = create_fallback_summary(travel_packages)
        state["package_summary"] = fallback_summary

    state["current_node"] = "summarize_packages_node"
    return state

def create_fallback_summary(packages):
    """Create a basic summary if LLM fails."""
    if not packages:
        return "No travel packages available."

    package_count = len(packages)
    cheapest_package = min(packages, key=lambda x: x.get("pricing", {}).get("total_min_price", float('inf')))
    cheapest_price = cheapest_package.get("pricing", {}).get("total_min_price", 0)
    currency = cheapest_package.get("pricing", {}).get("currency", "")

    summary = f"""Great! I found {package_count} travel package{'s' if package_count != 1 else ''} for your trip.
The packages include flights and hotel options for different departure dates. The most affordable option starts from {cheapest_price} {currency}, including both flight and hotel.
Each package offers various hotel choices and multiple flight options, so you can pick based on your preferences for timing, stops, and budget.
I recommend comparing the flight times, stops, and hotel locations to find what works best for your travel style. Don't forget to check cancellation policies before booking!"""
    return summary