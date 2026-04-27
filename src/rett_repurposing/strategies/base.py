"""Strategy interface — see IMPLEMENTATION_BRIEF.md §8.

Each strategy is shaped like an MCP tool: input is a Disease, output is a
CandidateList. This shape is deliberately stable — Phase 5+ will wrap each
Strategy as an MCP server with this exact contract.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from rett_repurposing.models import CandidateList, Disease


class Strategy(ABC):
    """Base class for repurposing strategies."""

    name: str  # set by subclass; used in logs and CandidateList.strategy

    @abstractmethod
    async def run(self, disease: Disease) -> CandidateList:
        """Generate ranked candidates for the given disease."""
