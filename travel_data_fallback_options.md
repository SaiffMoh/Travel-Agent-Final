# Travel Data Fallback – Query Options

You can use any of the following options when making a query to retrieve data from the fallback database (`travel_data.db`). To access it in the `.env`, add a key:
`USE_FALLBACK=true`.
Set it to `false` if you want to use the actual Amadeus API.

---

## Sample Query Format
I want to fly from Cairo to [DESTINATION] on [DEPARTURE_DATE] for [DURATION] nights in [CABIN_CLASS].

---

## Available Destinations
| Destination | Code |
|-------------|------|
| Dubai | DXB |
| Algiers | ALG |
| Riyadh | RUH |
| Abu Dhabi | AUH |
| Barcelona | BCN |
| Madrid | MAD |

---

## Available Departure Dates
| Date               |
|--------------------|
| October 30, 2025   |
| November 2, 2025   |
| November 5, 2025   |
| November 8, 2025   |
| November 11, 2025  |

---

## Available Durations
| Duration   |
|------------|
| 3 nights   |
| 5 nights   |
| 7 nights   |

---

## Available Cabin Classes by Destination

| Destination | Economy | Business |
|-------------|---------|----------|
| Dubai (DXB) | ✓ | ✓ |
| Algiers (ALG) | ✓ | ✓ |
| Riyadh (RUH) | ✓ | ✓ |
| Abu Dhabi (AUH) | ✓ | ✓ |
| Barcelona (BCN) | ✓ | ✓ |
| Madrid (MAD) | ✓ | ✓ |

---

## Database Statistics

### Total Data Available
- **Total Flights:** 750 offers across 6 destinations
- **Total Hotel Searches:** 148+
- **Cabin Classes:** Economy and Business
- **Cities with Hotels:** 5 (ALG, RUH, AUH, MAD, and partial DXB coverage)

### Flights by Destination
| Route | Economy | Business | Total |
|-------|---------|----------|-------|
| CAI → DXB | 75 | 75 | 150 |
| CAI → ALG | 75 | 75 | 150 |
| CAI → RUH | 75 | 75 | 150 |
| CAI → AUH | 75 | 75 | 150 |
| CAI → BCN | 75 | 75 | 150 |
| CAI → MAD | 75 | 75 | 150 |

### Hotel Availability
| City | Hotels Available |
|------|------------------|
| DXB | No |
| ALG | Yes (2 per search) |
| RUH | Yes (1-2 per search) |
| AUH | Yes (2-3 per search) |
| BCN | No |
| MAD | Yes (3-4 per search) |

---

## Example Queries

### Economy Class
- I want to fly from Cairo to Riyadh on November 2, 2025, for 5 nights in economy class.
- I want to fly from Cairo to Abu Dhabi on November 8, 2025, for 7 nights in economy class.
- I want to fly from Cairo to Algiers on October 30, 2025, for 3 nights in economy class.
- I want to fly from Cairo to Barcelona on November 5, 2025, for 5 nights in economy class.
- I want to fly from Cairo to Madrid on November 11, 2025, for 3 nights in economy class.

### Business Class
- I want to fly from Cairo to Dubai on November 2, 2025, for 7 nights in business class.
- I want to fly from Cairo to Riyadh on November 8, 2025, for 5 nights in business class.
- I want to fly from Cairo to Barcelona on October 30, 2025, for 3 nights in business class.
- I want to fly from Cairo to Madrid on November 5, 2025, for 7 nights in business class.

---

## Data Collection Details

**Date Range:** 7-22 days from current date (rolling window)  
**Search Interval:** Every 3 days  
**Trip Durations:** 3, 5, and 7 nights  
**Flights per Search:** Up to 5 offers  
**Hotels per City:** Up to 10 hotels per search