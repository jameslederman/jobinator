"""Source adapters for job discovery."""

from jobinator.adapters.base import AdapterBrokenError, SourceAdapter
from jobinator.adapters.greenhouse import GreenhouseAdapter
from jobinator.adapters.hn_hiring import HNHiringAdapter
from jobinator.adapters.lever import LeverAdapter
from jobinator.adapters.wellfound import WellfoundAdapter

__all__ = [
    "SourceAdapter",
    "AdapterBrokenError",
    "GreenhouseAdapter",
    "LeverAdapter",
    "HNHiringAdapter",
    "WellfoundAdapter",
]
