"""
Building-related data models.

Contains dataclasses for building records (from search results)
and building details (from GetTikFile API).
"""

from dataclasses import dataclass, field


@dataclass
class BuildingRecord:
    """
    A building file record from search results.

    This represents the basic information returned when searching
    for buildings by address (GetTikimByAddress or GetBakashotByAddress).
    """

    tik_number: str
    address: str = ""
    gush: str = ""
    helka: str = ""
    migrash: str = ""
    street_code: int = 0
    street_name: str = ""
    house_number: int = 0


@dataclass
class BuildingDetail:
    """
    Detailed building file information.

    This represents the full information returned by GetTikFile API,
    including addresses, parcel info, plans, and permit requests.
    """

    tik_number: str
    address: str = ""
    neighborhood: str = ""
    addresses: list = field(default_factory=list)
    gush_helka: list = field(default_factory=list)
    plans: list = field(default_factory=list)
    requests: list = field(default_factory=list)
    stakeholders: list = field(default_factory=list)
    documents: list = field(default_factory=list)
    fetch_status: str = "pending"
    fetch_error: str = ""
    fetched_at: str = ""
