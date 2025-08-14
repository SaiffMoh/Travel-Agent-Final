from Models import TravelSearchState
from Utils.getLLM import get_llm
from Prompts.summary_prompt import summary_prompt
from langchain.schema import HumanMessage

def summarize_packages(state: TravelSearchState) -> TravelSearchState:
    """Generate LLM summary and recommendation for travel packages."""


    # Get the 3 travel packages
    travel_packages = state.get("travel_packages", [])
    
    if not travel_packages or len(travel_packages) == 0:
        state["package_summary"] = "No travel packages found for your search. Please try different dates or destinations."
        return state
    
    # Ensure we have 3 packages (pad with None if needed)
    package1 = travel_packages[0] if len(travel_packages) > 0 else None
    package2 = travel_packages[1] if len(travel_packages) > 1 else None
    package3 = travel_packages[2] if len(travel_packages) > 2 else None
    
    # Handle cases where we have fewer than 3 packages
    if not package1:
        state["package_summary"] = "No valid travel packages could be created. Please check your search criteria."
        return state
    
    try:
        # Generate the prompt with the 3 packages
        llm_prompt = summary_prompt(package1, package2, package3)
        
        # Use OpenAI LLM to generate summary
        response = get_llm().invoke([HumanMessage(content=llm_prompt)])
        state["package_summary"] = response.content
        
        print("Generated package summary:", response.content)
        
    except Exception as e:
        print(f"Error generating package summary: {e}")
        import traceback
        traceback.print_exc()
        
        # Fallback summary if LLM fails
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
    currency = cheapest_package.get("pricing", {}).get("currency", "EGP")
    
    summary = f"""Great! I found {package_count} travel package{'s' if package_count != 1 else ''} for your trip. 

The packages include flights and hotel options for different departure dates. The most affordable option starts from {cheapest_price} {currency}, including both flight and hotel.

Each package offers various hotel choices, so you can pick based on your preferences for location, amenities, and budget. 

I recommend comparing the flight times and hotel locations to find what works best for your travel style. Don't forget to check cancellation policies before booking!"""

    return summary