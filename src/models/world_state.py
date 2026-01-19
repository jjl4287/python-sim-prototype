"""World state schemas - the canonical representation of the game world."""

from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
import uuid


class SettlementType(str, Enum):
    """Types of settlements in the world."""
    CASTLE = "castle"
    TOWN = "town"
    VILLAGE = "village"
    OUTPOST = "outpost"
    CAMP = "camp"


class TerrainType(str, Enum):
    """Types of terrain."""
    FOREST = "forest"
    PLAINS = "plains"
    HILLS = "hills"
    MOUNTAINS = "mountains"
    MARSH = "marsh"
    RIVER = "river"
    COAST = "coast"
    DESERT = "desert"
    FARMLAND = "farmland"
    WASTELAND = "wasteland"


class PopulationClass(str, Enum):
    """Social classes in the population."""
    NOBILITY = "nobility"
    CLERGY = "clergy"
    MERCHANTS = "merchants"
    ARTISANS = "artisans"
    PEASANTS = "peasants"
    SOLDIERS = "soldiers"
    SLAVES = "slaves"
    REFUGEES = "refugees"


class Settlement(BaseModel):
    """A settlement in the world."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str
    type: SettlementType
    description: Optional[str] = None
    population: int = 0
    defense_level: int = Field(default=0, ge=0, le=10)
    prosperity: int = Field(default=5, ge=0, le=10)
    
    model_config = {"extra": "allow"}


class Terrain(BaseModel):
    """A terrain feature or region."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str
    type: TerrainType
    description: Optional[str] = None
    controlled: bool = False
    resources_available: list[str] = Field(default_factory=list)
    hazards: list[str] = Field(default_factory=list)
    
    model_config = {"extra": "allow"}


class Resources(BaseModel):
    """Core resources tracked by the game."""
    treasury: int = Field(default=100, description="Gold/currency units")
    food: int = Field(default=100, description="Food supply units")
    timber: int = Field(default=50, description="Wood/lumber units")
    iron: int = Field(default=25, description="Metal/ore units")
    labor: int = Field(default=50, description="Available workforce")
    
    # Allow scenario-specific resources
    model_config = {"extra": "allow"}
    
    def adjust(self, resource: str, amount: int) -> bool:
        """Adjust a resource by amount. Returns True if successful."""
        current = getattr(self, resource, None)
        if current is None:
            return False
        new_value = current + amount
        if new_value < 0:
            return False
        setattr(self, resource, new_value)
        return True


class Population(BaseModel):
    """Population segment with approval tracking."""
    social_class: PopulationClass
    count: int = Field(default=0, ge=0)
    approval: int = Field(default=50, ge=0, le=100, description="0-100 approval rating")
    notes: Optional[str] = None
    
    model_config = {"extra": "allow"}


class Faction(BaseModel):
    """A political or social faction."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str
    description: Optional[str] = None
    power: int = Field(default=5, ge=0, le=10, description="Political influence 0-10")
    disposition: int = Field(default=50, ge=0, le=100, description="Disposition toward ruler 0-100")
    goals: list[str] = Field(default_factory=list)
    members: list[str] = Field(default_factory=list, description="Notable members")
    
    model_config = {"extra": "allow"}


class Infrastructure(BaseModel):
    """Infrastructure and improvements."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str
    type: str  # road, bridge, workshop, mill, etc.
    description: Optional[str] = None
    condition: int = Field(default=100, ge=0, le=100, description="Condition 0-100")
    location: Optional[str] = None  # Settlement or terrain id
    effects: dict[str, int] = Field(default_factory=dict)  # e.g. {"food_production": 10}
    
    model_config = {"extra": "allow"}


class LegalClaim(BaseModel):
    """A legal claim or right in the world."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    holder: str  # Who holds this right
    type: str  # land, title, privilege, etc.
    target: str  # What the claim is over
    description: Optional[str] = None
    contested_by: list[str] = Field(default_factory=list)
    granted_date: Optional[str] = None
    
    model_config = {"extra": "allow"}


class AdvisorContext(BaseModel):
    """Context and framing for advisor behavior."""
    historical_period: str = "medieval"
    cultural_norms: list[str] = Field(default_factory=list)
    taboos: list[str] = Field(default_factory=list)
    technology_level: str = "pre-industrial"
    special_rules: list[str] = Field(default_factory=list)
    
    model_config = {"extra": "allow"}


class WorldState(BaseModel):
    """The complete canonical state of the game world."""
    # Metadata
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    scenario_title: str = "Untitled Realm"
    scenario_description: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    version: int = 1
    
    # Time tracking
    current_tick: int = Field(default=0, description="Current game tick (days elapsed)")
    current_date: str = Field(default="Day 1", description="Display date")
    
    # Core state
    settlements: list[Settlement] = Field(default_factory=list)
    terrain: list[Terrain] = Field(default_factory=list)
    resources: Resources = Field(default_factory=Resources)
    populations: list[Population] = Field(default_factory=list)
    factions: list[Faction] = Field(default_factory=list)
    infrastructure: list[Infrastructure] = Field(default_factory=list)
    legal_claims: list[LegalClaim] = Field(default_factory=list)
    
    # Advisor context
    advisor_context: AdvisorContext = Field(default_factory=AdvisorContext)
    
    # Allow scenario-specific extensions
    model_config = {"extra": "allow"}
    
    def get_settlement(self, id_or_name: str) -> Optional[Settlement]:
        """Find a settlement by ID or name."""
        for s in self.settlements:
            if s.id == id_or_name or s.name.lower() == id_or_name.lower():
                return s
        return None
    
    def get_terrain(self, id_or_name: str) -> Optional[Terrain]:
        """Find terrain by ID or name."""
        for t in self.terrain:
            if t.id == id_or_name or t.name.lower() == id_or_name.lower():
                return t
        return None
    
    def get_faction(self, id_or_name: str) -> Optional[Faction]:
        """Find a faction by ID or name."""
        for f in self.factions:
            if f.id == id_or_name or f.name.lower() == id_or_name.lower():
                return f
        return None
    
    def summary(self) -> str:
        """Generate a text summary of the world state."""
        lines = [
            f"=== {self.scenario_title} ===",
            f"Date: {self.current_date} (Tick {self.current_tick})",
            "",
            "--- Resources ---",
            f"  Treasury: {self.resources.treasury}",
            f"  Food: {self.resources.food}",
            f"  Timber: {self.resources.timber}",
            f"  Iron: {self.resources.iron}",
            f"  Labor: {self.resources.labor}",
        ]
        
        if self.settlements:
            lines.append("")
            lines.append("--- Settlements ---")
            for s in self.settlements:
                lines.append(f"  {s.name} ({s.type.value}): pop {s.population}, defense {s.defense_level}")
        
        if self.factions:
            lines.append("")
            lines.append("--- Factions ---")
            for f in self.factions:
                lines.append(f"  {f.name}: power {f.power}, disposition {f.disposition}")
        
        if self.populations:
            lines.append("")
            lines.append("--- Populations ---")
            for p in self.populations:
                lines.append(f"  {p.social_class.value}: {p.count} (approval: {p.approval}%)")
        
        return "\n".join(lines)
