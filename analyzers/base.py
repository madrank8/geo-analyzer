"""Base class for all GEO analyzers."""
from abc import ABC, abstractmethod


class AnalyzerBase(ABC):
    """Abstract base for the 5 parallel GEO analyzers."""
    name: str = "base"

    @abstractmethod
    async def analyze(self, page_data: dict, business_type: str, api_keys: dict = None) -> dict:
        """
        Run analysis and return results.

        Returns:
            {
                "scores": {"category_name": 0-100, ...},
                "findings": [{"severity": str, "title": str, "description": str}, ...],
                "recommendations": [str, ...],
                "details": { ... }  # analyzer-specific data
            }
        """
        raise NotImplementedError
