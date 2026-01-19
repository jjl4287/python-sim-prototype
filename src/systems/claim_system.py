"""Claim system - manages the lifecycle of claims about the world."""

from __future__ import annotations
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.models.world_state import WorldState

from src.models.claims import Claim, ClaimStatus


class ClaimSystem:
    """Manages claims about the world - validation pipeline for new facts."""
    
    def __init__(self, world_state: "WorldState"):
        self.world_state = world_state
        self._claims: dict[str, Claim] = {}
        self._next_id: int = 1  # Sequential ID counter
        self._id_map: dict[str, str] = {}  # Maps simple IDs ("1") to full IDs
    
    def add_claim(self, claim: Claim) -> str:
        """Add a new claim to the system. Returns the assigned simple ID."""
        # Assign sequential ID
        simple_id = str(self._next_id)
        self._next_id += 1
        
        # Store with the original UUID but create a mapping
        self._claims[claim.id] = claim
        self._id_map[simple_id] = claim.id
        
        # Also allow looking up by simple ID
        claim.__dict__['simple_id'] = simple_id
        
        return simple_id
    
    def get_claim(self, claim_id: str) -> Optional[Claim]:
        """Get a claim by ID (accepts both simple ID like '1' or full UUID)."""
        # Try simple ID first
        if claim_id in self._id_map:
            full_id = self._id_map[claim_id]
            return self._claims.get(full_id)
        
        # Try full ID
        return self._claims.get(claim_id)
    
    def list_claims(self) -> list[Claim]:
        """Get all claims."""
        return list(self._claims.values())
    
    def get_pending_claims(self) -> list[Claim]:
        """Get all pending claims."""
        return [c for c in self._claims.values() if c.status == ClaimStatus.PENDING]
    
    def get_contested_claims(self) -> list[Claim]:
        """Get all contested claims."""
        return [c for c in self._claims.values() if c.status == ClaimStatus.CONTESTED]
    
    def get_confirmed_claims(self) -> list[Claim]:
        """Get all confirmed claims."""
        return [c for c in self._claims.values() if c.status == ClaimStatus.CONFIRMED]
    
    def get_denied_claims(self) -> list[Claim]:
        """Get all denied claims."""
        return [c for c in self._claims.values() if c.status == ClaimStatus.DENIED]
    
    def get_claims_by_proposer(self, proposer: str) -> list[Claim]:
        """Get all claims by a specific proposer."""
        return [c for c in self._claims.values() if c.proposed_by == proposer]
    
    def has_pending_claims(self) -> bool:
        """Check if there are any pending claims."""
        return any(c.status == ClaimStatus.PENDING for c in self._claims.values())
    
    def pending_count(self) -> int:
        """Count of pending claims."""
        return sum(1 for c in self._claims.values() if c.status == ClaimStatus.PENDING)
    
    def get_simple_id(self, claim: Claim) -> str:
        """Get the simple ID for a claim."""
        return getattr(claim, 'simple_id', claim.id[:8])
    
    def summary(self) -> str:
        """Generate a summary of claims."""
        pending = self.get_pending_claims()
        contested = self.get_contested_claims()
        confirmed = self.get_confirmed_claims()
        denied = self.get_denied_claims()
        
        lines = [
            f"Claims Summary:",
            f"  Pending: {len(pending)}",
            f"  Contested: {len(contested)}",
            f"  Confirmed: {len(confirmed)}",
            f"  Denied: {len(denied)}",
        ]
        
        if pending:
            lines.append("")
            lines.append("Pending Claims:")
            for claim in pending:
                simple_id = self.get_simple_id(claim)
                lines.append(f"  [{simple_id}] {claim.description[:60]}...")
        
        if contested:
            lines.append("")
            lines.append("Contested Claims:")
            for claim in contested:
                simple_id = self.get_simple_id(claim)
                lines.append(f"  [{simple_id}] {claim.description[:60]}...")
        
        return "\n".join(lines)
    
    def export_claims(self) -> list[dict]:
        """Export all claims for serialization."""
        claims_data = []
        for claim in self._claims.values():
            data = claim.model_dump()
            data['simple_id'] = self.get_simple_id(claim)
            claims_data.append(data)
        return claims_data
    
    def import_claims(self, claims_data: list[dict]) -> None:
        """Import claims from serialized data."""
        self._claims.clear()
        self._id_map.clear()
        max_simple_id = 0
        
        for data in claims_data:
            simple_id = data.pop('simple_id', None)
            claim = Claim(**data)
            self._claims[claim.id] = claim
            
            if simple_id:
                claim.__dict__['simple_id'] = simple_id
                self._id_map[simple_id] = claim.id
                try:
                    max_simple_id = max(max_simple_id, int(simple_id))
                except ValueError:
                    pass
        
        self._next_id = max_simple_id + 1