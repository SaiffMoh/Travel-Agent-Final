from Models.TravelSearchState import TravelSearchState
from Utils.getLLM import get_text_llm
from Prompts.summary_prompt import summary_prompt
from langchain.schema import HumanMessage

def summarize_packages(state: TravelSearchState) -> TravelSearchState:
    """Generate LLM summary and recommendation for travel packages."""
    
    # Get the 3 travel packages
    travel_packages = state.get("travel_packages", [])
    
    if not travel_packages:
        state["package_summary"] = "No travel packages found for your search. Please try different dates or destinations."
        return state
    
    # Generate the LLM prompt
    package1 = travel_packages[0] if len(travel_packages) > 0 else None
    package2 = travel_packages[1] if len(travel_packages) > 1 else None
    package3 = travel_packages[2] if len(travel_packages) > 2 else None
    
    llm_prompt = summary_prompt(package1, package2, package3)
    
    try:
        # Use LLM to generate the summary
        response = get_text_llm().invoke([HumanMessage(content=llm_prompt)])
        llm_summary = response.content
        
        # Append the package details after the summary
        package_details = "\n\nHere are the details for the available packages:\n"
        
        for pkg in travel_packages:
            package_details += f"Package {pkg['package_id']}: {pkg['package_summary']}\n"
        
        state["package_summary"] = f"{llm_summary}\n{package_details}"
    except Exception as e:
        print(f"Error generating package summary: {e}")
        state["package_summary"] = create_fallback_summary(travel_packages)
    
    state["current_node"] = "summarize_packages_node"
    return state

def create_fallback_summary(packages):
    """Create a basic summary if LLM fails."""
    
    if not packages:
        return "No travel packages available."
    
    package_count = len(packages)
    cheapest_package = min(packages, key=lambda x: x.get("pricing", {}).get("total_min_price", float('inf')))
    cheapest_price = cheapest_package.get("pricing", {}).get("total_min_price", 0)
    currency = cheapest_package.get("pricing", {}).get("currency", "EGP")
    
    summary = f"""Great! I found {package_count} travel package{'s' if package_count != 1 else ''} for your trip. 

The packages include flights and hotel options for different departure dates. The most affordable option starts from {cheapest_price} {currency}, including both flight and hotel.

Each package offers various hotel choices, so you can pick based on your preferences for location, amenities, and budget. 

I recommend comparing the flight times and hotel locations to find what works best for your travel style. Don't forget to check cancellation policies before booking!"""

    return summary