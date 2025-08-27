import pandas as pd
from Models.TravelSearchState import TravelSearchState
import re

def parse_company_hotels_node(state: TravelSearchState) -> TravelSearchState:
    """Parse the company hotels Excel sheet with city codes and store in state."""
    try:
        # Use provided path or default
        excel_path = state.get("company_hotels_path", "data/International Hotels - Copy.xlsx")

        # Read Excel file
        df = pd.read_excel(excel_path, sheet_name="International Hotels")

        # Normalize column names
        df.columns = [col.strip().lower().replace(" ", "_") for col in df.columns]

        # Clean data and handle merged cells
        df["country"] = df["country"].fillna(method='ffill').str.lower().str.strip()
        df["city_code"] = df["city_code"].fillna(method='ffill').str.lower().str.strip()
        df["hotel_name"] = df["hotel_name"].fillna("").str.strip()
        df["rate_per_night"] = df["rate_per_night"].fillna("").str.strip()
        df["contacts"] = df["contacts"].fillna("").str.strip()
        df["notes"] = df["notes"].fillna("").str.strip()

        # Parse rate_per_night into value and currency
        def parse_rate(rate):
            if not rate:
                return None, None
            # Handle different rate formats
            rate_str = str(rate).strip()
            if not rate_str:
                return None, None

            # Try to match number followed by currency
            match = re.match(r"(\d+\.?\d*)\s*([A-Z]{3})", rate_str)
            if match:
                return float(match.group(1)), match.group(2)

            # Try to match just numbers (assume default currency)
            match = re.match(r"(\d+\.?\d*)", rate_str)
            if match:
                return float(match.group(1)), "USD"  # Default currency

            return None, None

        # Apply rate parsing
        rate_results = df["rate_per_night"].apply(parse_rate)
        df[["rate_value", "rate_currency"]] = pd.DataFrame(rate_results.tolist(), index=df.index)

        # Filter out invalid rows upfront
        valid_df = df[
            (df["country"].str.len() > 0) &
            (df["city_code"].str.len() > 0) &
            (df["hotel_name"].str.len() > 0) &
            (df["rate_value"].notna())
        ].copy()

        # Build the company hotels structure
        company_hotels = {}
        total_hotels_added = 0

        # Group by country first
        for country in valid_df["country"].unique():
            country_df = valid_df[valid_df["country"] == country]
            country_hotels = {}

            # Group by city_code within each country
            for city_code in country_df["city_code"].unique():
                city_df = country_df[country_df["city_code"] == city_code]
                hotels_list = []

                # Process each hotel in this city
                for idx, row in city_df.iterrows():
                    hotel_data = {
                        "hotel_name": row["hotel_name"],
                        "rate_per_night": float(row["rate_value"]),  # Ensure float
                        "currency": row["rate_currency"],
                        "contacts": row["contacts"] if pd.notna(row["contacts"]) else "",
                        "notes": row["notes"] if pd.notna(row["notes"]) else "",
                        "source": "company_excel"
                    }
                    hotels_list.append(hotel_data)

                # Store all hotels for this city
                country_hotels[city_code] = hotels_list
                total_hotels_added += len(hotels_list)

            # Store country data if it has any cities
            if country_hotels:
                company_hotels[country] = country_hotels

        state["company_hotels"] = company_hotels
        return state

    except FileNotFoundError:
        state["company_hotels"] = {}
        return state
    except Exception as e:
        state["company_hotels"] = {}
        return state