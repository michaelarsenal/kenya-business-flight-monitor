from __future__ import annotations

import hashlib
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import requests

from src.config import SearchQuery


@dataclass
class FlightOffer:
    origin: str
    destination: str
    departure_date: str
    return_date: str
    trip_length_days: int
    price_usd: float
    airline: str
    stops: int
    provider: str
    booking_url: str = ""

    @property
    def route_key(self) -> str:
        return f"{self.origin}-{self.destination}-{self.departure_date}-{self.return_date}"


class FlightProvider(ABC):
    name: str

    @abstractmethod
    def search_lowest_offer(self, query: SearchQuery) -> Optional[FlightOffer]:
        """Return the lowest-priced Business Class offer for the given query, or None."""


class AmadeusProvider(FlightProvider):
    name = "amadeus"

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        env: Optional[str] = None,
    ) -> None:
        self.client_id = client_id or os.environ.get("AMADEUS_CLIENT_ID", "")
        self.client_secret = client_secret or os.environ.get("AMADEUS_CLIENT_SECRET", "")
        if not self.client_id or not self.client_secret:
            raise ValueError(
                "AMADEUS_CLIENT_ID and AMADEUS_CLIENT_SECRET environment variables are required for AmadeusProvider."
            )
        env_mode = (env or os.environ.get("AMADEUS_ENV", "production")).lower()
        self.base_url = (
            "https://test.api.amadeus.com" if env_mode == "test" else "https://api.amadeus.com"
        )
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._session = requests.Session()

    def _ensure_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token

        resp = self._session.post(
            f"{self.base_url}/v1/security/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=20,
        )
        resp.raise_for_status()
        payload = resp.json()
        self._token = payload["access_token"]
        self._token_expires_at = time.time() + int(payload.get("expires_in", 1799))
        return self._token

    def search_lowest_offer(self, query: SearchQuery) -> Optional[FlightOffer]:
        params = {
            "originLocationCode": query.origin,
            "destinationLocationCode": query.destination,
            "departureDate": query.departure_date,
            "returnDate": query.return_date,
            "adults": query.adults,
            "travelClass": query.cabin,
            "currencyCode": query.currency,
            "max": 5,
        }
        if query.nonstop_only:
            params["nonStop"] = "true"

        for attempt in range(3):
            token = self._ensure_token()
            resp = self._session.get(
                f"{self.base_url}/v2/shopping/flight-offers",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
                timeout=30,
            )
            if resp.status_code == 429:
                time.sleep(2 ** (attempt + 1))
                continue
            if resp.status_code == 401 and attempt == 0:
                self._token = None
                continue
            resp.raise_for_status()
            data = resp.json()
            offers = data.get("data", [])
            if not offers:
                return None

            carriers = data.get("dictionaries", {}).get("carriers", {})
            best = min(offers, key=lambda o: float(o["price"]["grandTotal"]))
            price = float(best["price"]["grandTotal"])

            validating_codes = best.get("validatingAirlineCodes", [])
            carrier_code = validating_codes[0] if validating_codes else ""
            if not carrier_code:
                itineraries = best.get("itineraries", [])
                if itineraries and itineraries[0].get("segments"):
                    carrier_code = itineraries[0]["segments"][0].get("carrierCode", "")
            airline_name = carriers.get(carrier_code, carrier_code or "Unknown")

            # Max stops across outbound and inbound legs
            max_stops = 0
            for itin in best.get("itineraries", []):
                segs = itin.get("segments", [])
                if segs:
                    max_stops = max(max_stops, len(segs) - 1)

            gf_url = (
                f"https://www.google.com/travel/flights?q=Flights%20to%20{query.destination}"
                f"%20from%20{query.origin}%20on%20{query.departure_date}%20through%20{query.return_date}"
                f"%20business%20class"
            )
            return FlightOffer(
                origin=query.origin,
                destination=query.destination,
                departure_date=query.departure_date,
                return_date=query.return_date,
                trip_length_days=query.trip_length_days,
                price_usd=round(price, 2),
                airline=airline_name,
                stops=max_stops,
                provider=self.name,
                booking_url=gf_url,
            )
        return None


class SerpApiProvider(FlightProvider):
    name = "serpapi"

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or os.environ.get("SERPAPI_API_KEY", "")
        if not self.api_key:
            raise ValueError("SERPAPI_API_KEY environment variable is required for SerpApiProvider.")
        self._session = requests.Session()

    def search_lowest_offer(self, query: SearchQuery) -> Optional[FlightOffer]:
        # Google Flights travel_class: 1=Economy, 2=Premium Economy, 3=Business, 4=First
        params = {
            "engine": "google_flights",
            "departure_id": query.origin,
            "arrival_id": query.destination,
            "outbound_date": query.departure_date,
            "return_date": query.return_date,
            "travel_class": 3,
            "adults": query.adults,
            "currency": query.currency,
            "hl": "en",
            "api_key": self.api_key,
        }
        if query.nonstop_only:
            params["stops"] = 1  # 1 = Nonstop only in SerpApi Google Flights
        elif query.max_stops == 1:
            params["stops"] = 2  # 2 = 1 stop or fewer
        elif query.max_stops == 2:
            params["stops"] = 3  # 3 = 2 stops or fewer
        resp = self._session.get("https://serpapi.com/search.json", params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        candidates = data.get("best_flights", []) + data.get("other_flights", [])
        priced = [c for c in candidates if isinstance(c.get("price"), (int, float))]
        if query.max_stops is not None:
            priced = [
                c for c in priced if max(0, len(c.get("flights", [])) - 1) <= query.max_stops
            ]
        if not priced:
            return None

        best = min(priced, key=lambda c: float(c["price"]))
        flights = best.get("flights", [])
        airline = flights[0].get("airline", "Unknown") if flights else "Unknown"
        stops = max(0, len(flights) - 1)
        booking_url = data.get("search_metadata", {}).get("google_flights_url", "")

        return FlightOffer(
            origin=query.origin,
            destination=query.destination,
            departure_date=query.departure_date,
            return_date=query.return_date,
            trip_length_days=query.trip_length_days,
            price_usd=round(float(best["price"]), 2),
            airline=airline,
            stops=stops,
            provider=self.name,
            booking_url=booking_url,
        )


class SearchApiProvider(FlightProvider):
    name = "searchapi"

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or os.environ.get("SEARCHAPI_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "SEARCHAPI_API_KEY environment variable is required for SearchApiProvider."
            )
        self._session = requests.Session()

    def search_lowest_offer(self, query: SearchQuery) -> Optional[FlightOffer]:
        params = {
            "engine": "google_flights",
            "departure_id": query.origin,
            "arrival_id": query.destination,
            "outbound_date": query.departure_date,
            "return_date": query.return_date,
            "travel_class": "business",
            "adults": query.adults,
            "currency": query.currency,
            "hl": "en",
            "api_key": self.api_key,
        }
        if query.nonstop_only:
            params["stops"] = "nonstop"
        elif query.max_stops == 1:
            params["stops"] = "one_stop_or_fewer"
        elif query.max_stops == 2:
            params["stops"] = "two_stops_or_fewer"
        resp = self._session.get("https://www.searchapi.io/api/v1/search", params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        candidates = data.get("best_flights", []) + data.get("other_flights", [])
        priced = [c for c in candidates if isinstance(c.get("price"), (int, float))]
        if query.max_stops is not None:
            priced = [
                c for c in priced if max(0, len(c.get("flights", [])) - 1) <= query.max_stops
            ]
        if not priced:
            return None

        best = min(priced, key=lambda c: float(c["price"]))
        flights = best.get("flights", [])
        airline = flights[0].get("airline", "Unknown") if flights else "Unknown"
        stops = max(0, len(flights) - 1)
        booking_url = data.get("search_metadata", {}).get("google_flights_url", "")

        return FlightOffer(
            origin=query.origin,
            destination=query.destination,
            departure_date=query.departure_date,
            return_date=query.return_date,
            trip_length_days=query.trip_length_days,
            price_usd=round(float(best["price"]), 2),
            airline=airline,
            stops=stops,
            provider=self.name,
            booking_url=booking_url,
        )


class MockProvider(FlightProvider):
    """Deterministic mock provider for testing and dry-runs without API credentials."""

    name = "mock"

    def __init__(self, simulate_deal: bool = True) -> None:
        self.simulate_deal = simulate_deal

    def search_lowest_offer(self, query: SearchQuery) -> Optional[FlightOffer]:
        digest = int(hashlib.sha256(query.route_key.encode()).hexdigest()[:8], 16)
        base_price = 3850.0 + (digest % 1600)

        # Simulate a strong deal on JFK 2027-06-08 11-day trip
        if self.simulate_deal and query.origin == "JFK" and query.departure_date in {"2027-06-08", "2027-06-10"} and query.trip_length_days == 11:
            base_price = 3190.0

        if query.nonstop_only:
            airline = "Kenya Airways"
            stops = 0
        else:
            airlines = ["Qatar Airways", "Kenya Airways", "British Airways", "KLM", "Lufthansa", "Turkish Airlines"]
            airline = airlines[digest % len(airlines)]
            if query.max_stops == 1:
                stops = 0 if airline == "Kenya Airways" else 1
            else:
                stops = 1 if (digest % 3 != 0) else 2

        return FlightOffer(
            origin=query.origin,
            destination=query.destination,
            departure_date=query.departure_date,
            return_date=query.return_date,
            trip_length_days=query.trip_length_days,
            price_usd=round(base_price, 2),
            airline=airline,
            stops=stops,
            provider=self.name,
            booking_url=(
                f"https://www.google.com/travel/flights?q=Flights%20to%20{query.destination}"
                f"%20from%20{query.origin}%20on%20{query.departure_date}%20through%20{query.return_date}"
            ),
        )


def get_provider(provider_name: Optional[str] = None) -> FlightProvider:
    name = (provider_name or os.environ.get("FLIGHT_PROVIDER", "")).strip().lower()
    if not name:
        if os.environ.get("SERPAPI_API_KEY"):
            name = "serpapi"
        elif os.environ.get("SEARCHAPI_API_KEY"):
            name = "searchapi"
        elif os.environ.get("AMADEUS_CLIENT_ID") and os.environ.get("AMADEUS_CLIENT_SECRET"):
            name = "amadeus"
        else:
            name = "mock"

    if name == "serpapi":
        return SerpApiProvider()
    if name == "searchapi":
        return SearchApiProvider()
    if name == "amadeus":
        return AmadeusProvider()
    if name == "mock":
        return MockProvider()
    raise ValueError(f"Unsupported flight provider: {name}")
