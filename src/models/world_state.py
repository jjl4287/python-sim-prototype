"""World state schemas - the canonical representation of the game world."""

from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Optional, Any
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


class DynamicRule(BaseModel):
    """A dynamic game rule created by the AI during play."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    trigger: str = Field(description="When this rule activates (natural language condition)")
    effect: str = Field(description="What happens when triggered (natural language effect)")
    reason: str = Field(description="Why this rule exists")
    created_by: str = Field(default="system")
    created_at: datetime = Field(default_factory=datetime.now)
    active: bool = True
    
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
    
    # Starting tensions (for display/reference)
    starting_tensions: list[str] = Field(default_factory=list)
    
    # Core state (structured, typed)
    settlements: list[Settlement] = Field(default_factory=list)
    terrain: list[Terrain] = Field(default_factory=list)
    resources: Resources = Field(default_factory=Resources)
    populations: list[Population] = Field(default_factory=list)
    factions: list[Faction] = Field(default_factory=list)
    infrastructure: list[Infrastructure] = Field(default_factory=list)
    legal_claims: list[LegalClaim] = Field(default_factory=list)
    
    # Advisor context
    advisor_context: AdvisorContext = Field(default_factory=AdvisorContext)
    
    # Dynamic extensions (AI-writable, freeform)
    extensions: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary nested data created by AI during play"
    )
    
    # Dynamic rules (AI-created game mechanics)
    dynamic_rules: list[DynamicRule] = Field(default_factory=list)
    
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
    
    # ===== Extension Path Methods =====
    
    def get_extension(self, path: str, default: Any = None) -> Any:
        """Get a value from extensions using dot-notation path.
        
        Example: get_extension("advisors.marshal.resentment.clockmaker_incident")
        """
        keys = path.split(".")
        current = self.extensions
        
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        
        return current
    
    def set_extension(self, path: str, value: Any, metadata: Optional[dict] = None) -> bool:
        """Set a value in extensions using dot-notation path.
        
        Example: set_extension("advisors.marshal.resentment.incident", {"severity": "high"})
        
        If metadata is provided, it's merged with the value if value is a dict.
        """
        keys = path.split(".")
        current = self.extensions
        
        # Navigate/create path to parent
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            elif not isinstance(current[key], dict):
                # Can't traverse through non-dict
                return False
            current = current[key]
        
        # Set the final value
        final_key = keys[-1]
        
        if isinstance(value, dict) and metadata:
            value = {**value, "_meta": metadata}
        elif metadata:
            value = {"_value": value, "_meta": metadata}
        
        current[final_key] = value
        return True
    
    def delete_extension(self, path: str) -> bool:
        """Delete a value from extensions using dot-notation path."""
        keys = path.split(".")
        current = self.extensions
        
        # Navigate to parent
        for key in keys[:-1]:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return False
        
        # Delete the final key
        final_key = keys[-1]
        if isinstance(current, dict) and final_key in current:
            del current[final_key]
            return True
        return False
    
    def list_extensions(self, prefix: str = "") -> list[str]:
        """List all extension paths, optionally filtered by prefix."""
        paths = []
        
        def _collect_paths(obj: dict, current_path: str):
            for key, value in obj.items():
                full_path = f"{current_path}.{key}" if current_path else key
                if isinstance(value, dict) and not key.startswith("_"):
                    # Check if this is a leaf node with metadata or a branch
                    if "_value" in value or "_meta" in value:
                        paths.append(full_path)
                    else:
                        _collect_paths(value, full_path)
                else:
                    paths.append(full_path)
        
        _collect_paths(self.extensions, "")
        
        if prefix:
            paths = [p for p in paths if p.startswith(prefix)]
        
        return sorted(paths)
    
    def has_extension(self, path: str) -> bool:
        """Check if an extension path exists."""
        return self.get_extension(path) is not None
    
    # ===== Dynamic Rules =====
    
    def add_rule(self, trigger: str, effect: str, reason: str, created_by: str = "system") -> DynamicRule:
        """Add a new dynamic rule."""
        rule = DynamicRule(
            trigger=trigger,
            effect=effect,
            reason=reason,
            created_by=created_by,
        )
        self.dynamic_rules.append(rule)
        return rule
    
    def get_active_rules(self) -> list[DynamicRule]:
        """Get all active dynamic rules."""
        return [r for r in self.dynamic_rules if r.active]
    
    # ===== Core Entity Lookups =====
    
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
        
        # Show extensions summary if any exist
        ext_paths = self.list_extensions()
        if ext_paths:
            lines.append("")
            lines.append("--- Dynamic State ---")
            for path in ext_paths[:10]:  # Limit to 10
                value = self.get_extension(path)
                if isinstance(value, dict):
                    summary = value.get("summary", value.get("reason", str(value)[:40]))
                else:
                    summary = str(value)[:40]
                lines.append(f"  {path}: {summary}")
            if len(ext_paths) > 10:
                lines.append(f"  ... and {len(ext_paths) - 10} more")
        
        # Show active rules if any
        active_rules = self.get_active_rules()
        if active_rules:
            lines.append("")
            lines.append("--- Active Rules ---")
            for rule in active_rules[:5]:
                lines.append(f"  • {rule.trigger} → {rule.effect}")
            if len(active_rules) > 5:
                lines.append(f"  ... and {len(active_rules) - 5} more")
        
        return "\n".join(lines)
