"""OpenAlex access layer and top-level facade APIs."""

from .client import OpenAlexClient
from .facade import OpenAlexFacade

__all__ = ["OpenAlexClient", "OpenAlexFacade"]

