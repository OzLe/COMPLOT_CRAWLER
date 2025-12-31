"""
Permit request data model.

Contains the RequestDetail dataclass for detailed permit information
from the GetBakashaFile API.
"""

from dataclasses import dataclass, field


@dataclass
class RequestDetail:
    """
    Detailed permit request information from GetBakashaFile.

    This represents the full lifecycle of a building permit request,
    including stakeholders, events, requirements, and committee meetings.
    """

    request_number: str
    tik_number: str = ""  # Associated building file
    address: str = ""
    submission_date: str = ""

    # General info
    request_type: str = ""  # סוג הבקשה (e.g., בקשה להיתר)
    primary_use: str = ""  # שימוש עיקרי (e.g., בית דו משפחתי)
    description: str = ""  # תיאור הבקשה
    permit_number: str = ""
    permit_date: str = ""
    main_area_sqm: str = ""  # שטח עיקרי
    service_area_sqm: str = ""  # שטח שירות
    housing_units: str = ""  # יחידות דיור

    # Related data
    stakeholders: list = field(default_factory=list)  # בעלי עניין
    events: list = field(default_factory=list)  # אירועים (timeline)
    requirements: list = field(default_factory=list)  # דרישות
    meetings: list = field(default_factory=list)  # ישיבות ועדה
    documents: list = field(default_factory=list)  # ארכיב מסמכים
    gush_helka: list = field(default_factory=list)  # גוש וחלקה

    # Fetch metadata
    fetch_status: str = "pending"
    fetch_error: str = ""
    fetched_at: str = ""
