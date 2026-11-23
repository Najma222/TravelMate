"""Outbound *search* links for hotels / flights / trains / buses.

These are deep links into public search pages, built with URL encoding. They do not
check availability, hold seats, or take payment — v1 never books or pays.
"""
from __future__ import annotations

from datetime import timedelta
from urllib.parse import urlencode

DISCLAIMER = ("Search links only. Availability and prices are not checked or guaranteed; "
              "TravelMate does not make reservations or take payments.")


def build_links(trip) -> dict:
    origin, dest = trip.origin, trip.destination
    start, end = trip.start_date, trip.end_date
    checkout = end if end > start else start + timedelta(days=1)
    links = [
        {
            "booking_type": "hotel",
            "provider": "Booking.com",
            "url": "https://www.booking.com/searchresults.html?" + urlencode({
                "ss": dest,
                "checkin": start.isoformat(),
                "checkout": checkout.isoformat(),
                "group_adults": trip.traveller_count,
                "no_rooms": 1,
            }),
            "prefilled": True,
        },
        {
            "booking_type": "flight",
            "provider": "Google Flights",
            "url": "https://www.google.com/travel/flights?" + urlencode({
                "q": f"Flights from {origin} to {dest} on {start.isoformat()} "
                     f"returning {end.isoformat()} for {trip.traveller_count} adults",
            }),
            "prefilled": True,
        },
        {
            "booking_type": "train",
            "provider": "IRCTC",
            "url": "https://www.irctc.co.in/nget/train-search",
            "prefilled": False,
        },
        {
            "booking_type": "bus",
            "provider": "redBus",
            "url": "https://www.redbus.in/",
            "prefilled": False,
        },
    ]
    return {"trip_id": trip.id, "links": links, "disclaimer": DISCLAIMER}
