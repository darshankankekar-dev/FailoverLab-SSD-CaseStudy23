from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class ClientProfile(BaseModel):
    client_region_id: str
    display_name: str
    cloud_zone: str
    # Nominal one-way or round-trip WAN latencies in milliseconds to all 5 regions
    latencies_ms: Dict[str, float] = Field(default_factory=dict)


# Truthful nominal WAN delay models from geographic customer origins to regional cloud data centers.
# These delays model realistic cross-continental fiber-optic propagation and routing hops.
CLIENT_PROFILES: Dict[str, ClientProfile] = {
    "india": ClientProfile(
        client_region_id="india",
        display_name="India (South Asia)",
        cloud_zone="ap-south-1",
        latencies_ms={
            "region-a": 18.0,   # Mumbai (domestic)
            "region-b": 48.0,   # Singapore (subsea cable)
            "region-c": 120.0,  # Frankfurt (Europe terrestrial/subsea)
            "region-d": 190.0,  # Virginia (Transatlantic/Pacific hop)
            "region-e": 290.0,  # São Paulo (Inter-hemisphere)
        },
    ),
    "southeast-asia": ClientProfile(
        client_region_id="southeast-asia",
        display_name="Southeast Asia",
        cloud_zone="ap-southeast-1",
        latencies_ms={
            "region-b": 14.0,   # Singapore (domestic/metro)
            "region-a": 48.0,   # Mumbai (Bay of Bengal cable)
            "region-c": 150.0,  # Frankfurt
            "region-d": 205.0,  # Virginia (Transpacific)
            "region-e": 310.0,  # São Paulo
        },
    ),
    "europe": ClientProfile(
        client_region_id="europe",
        display_name="Europe",
        cloud_zone="eu-central-1",
        latencies_ms={
            "region-c": 16.0,   # Frankfurt (continental)
            "region-d": 95.0,   # Virginia (Transatlantic link)
            "region-a": 120.0,  # Mumbai (Middle East corridor)
            "region-b": 150.0,  # Singapore
            "region-e": 215.0,  # São Paulo (South Atlantic)
        },
    ),
    "north-america": ClientProfile(
        client_region_id="north-america",
        display_name="North America",
        cloud_zone="us-east-1",
        latencies_ms={
            "region-d": 15.0,   # Virginia (metro/domestic)
            "region-c": 95.0,   # Frankfurt (Transatlantic link)
            "region-e": 135.0,  # São Paulo (Pan-American subsea)
            "region-a": 190.0,  # Mumbai
            "region-b": 205.0,  # Singapore (Transpacific)
        },
    ),
    "south-america": ClientProfile(
        client_region_id="south-america",
        display_name="South America",
        cloud_zone="sa-east-1",
        latencies_ms={
            "region-e": 18.0,   # São Paulo (metro/domestic)
            "region-d": 135.0,  # Virginia (Pan-American link)
            "region-c": 215.0,  # Frankfurt
            "region-a": 290.0,  # Mumbai
            "region-b": 310.0,  # Singapore
        },
    ),
}

# Aliases mapping common header inputs, country codes, and cloud zone identifiers to standard profiles
_PROFILE_ALIASES: Dict[str, str] = {
    # India
    "india": "india",
    "in": "india",
    "ap-south-1": "india",
    "mumbai": "india",
    "region-a": "india",
    # Southeast Asia
    "southeast-asia": "southeast-asia",
    "sea": "southeast-asia",
    "sg": "southeast-asia",
    "singapore": "southeast-asia",
    "ap-southeast-1": "southeast-asia",
    "region-b": "southeast-asia",
    # Europe
    "europe": "europe",
    "eu": "europe",
    "de": "europe",
    "frankfurt": "europe",
    "eu-central-1": "europe",
    "region-c": "europe",
    # North America
    "north-america": "north-america",
    "na": "north-america",
    "us": "north-america",
    "usa": "north-america",
    "virginia": "north-america",
    "us-east-1": "north-america",
    "region-d": "north-america",
    # South America
    "south-america": "south-america",
    "sa": "south-america",
    "br": "south-america",
    "brazil": "south-america",
    "sao-paulo": "south-america",
    "sa-east-1": "south-america",
    "region-e": "south-america",
}


def resolve_client_profile(identifier: Optional[str]) -> ClientProfile:
    """
    Resolves client profile from header or parameter (e.g. 'ap-south-1', 'europe', 'us-east-1').
    Defaults to 'india' profile if unidentified or omitted.
    """
    if not identifier:
        return CLIENT_PROFILES["india"]
    norm = identifier.strip().lower()
    profile_key = _PROFILE_ALIASES.get(norm, "india")
    return CLIENT_PROFILES.get(profile_key, CLIENT_PROFILES["india"])


def get_simulated_wan_delay(client_profile: ClientProfile, target_region_id: str) -> float:
    """Returns nominal WAN delay in ms for the given client profile and target region."""
    return client_profile.latencies_ms.get(target_region_id, 25.0)
