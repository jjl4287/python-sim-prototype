"""Tool handler implementations - actual logic for each tool."""

from __future__ import annotations
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.models.world_state import WorldState
    from src.systems.claim_system import ClaimSystem
    from src.systems.time_system import TimeSystem
    from src.systems.event_log import EventLog as EventLogSystem

from src.models.claims import Claim, ClaimStatus, ClaimType, ClaimProposal, ClaimEvidence
from src.models.actions import ActionSpec, ActionType, ActionProposal
from src.models.events import Event, EventType


class ToolHandlers:
    """Handlers for all game tools."""
    
    def __init__(
        self,
        world_state: "WorldState",
        claim_system: "ClaimSystem",
        time_system: "TimeSystem",
        event_log: "EventLogSystem",
    ):
        self.world_state = world_state
        self.claim_system = claim_system
        self.time_system = time_system
        self.event_log = event_log
        self._pending_actions: list[ActionSpec] = []
    
    def get_world_state(self, scope: str = "full") -> dict[str, Any]:
        """Get world state (or a scoped portion)."""
        ws = self.world_state
        
        if scope == "full":
            return ws.model_dump()
        elif scope == "resources":
            return {"resources": ws.resources.model_dump()}
        elif scope == "settlements":
            return {"settlements": [s.model_dump() for s in ws.settlements]}
        elif scope == "factions":
            return {"factions": [f.model_dump() for f in ws.factions]}
        elif scope == "populations":
            return {"populations": [p.model_dump() for p in ws.populations]}
        elif scope == "terrain":
            return {"terrain": [t.model_dump() for t in ws.terrain]}
        elif scope == "infrastructure":
            return {"infrastructure": [i.model_dump() for i in ws.infrastructure]}
        elif scope == "claims":
            return {"claims": self.claim_system.list_claims()}
        else:
            return ws.model_dump()
    
    def propose_claim(
        self,
        claim_type: str,
        description: str,
        proposed_by: str,
        evidence: list[dict[str, Any]] | None = None,
        effects_on_confirm: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Propose a new claim about the world."""
        claim_type_enum = ClaimType(claim_type)
        
        evidence_list = []
        if evidence:
            for e in evidence:
                evidence_list.append(ClaimEvidence(
                    type=e.get("type", "observation"),
                    description=e.get("description", ""),
                    confidence=e.get("confidence", 50),
                    source=e.get("source"),
                ))
        
        claim = Claim(
            claim_type=claim_type_enum,
            description=description,
            proposed_by=proposed_by,
            proposed_tick=self.world_state.current_tick,
            evidence=evidence_list,
            effects_on_confirm=effects_on_confirm or {},
        )
        
        self.claim_system.add_claim(claim)
        
        # Log the event
        self.event_log.add(Event(
            event_type=EventType.CLAIM_PROPOSED,
            description=f"Claim proposed: {description}",
            actor=proposed_by,
            game_tick=self.world_state.current_tick,
            game_date=self.world_state.current_date,
            related_claim_id=claim.id,
        ))
        
        return {
            "success": True,
            "claim_id": claim.id,
            "message": f"Claim '{claim.id}' submitted for review",
            "status": claim.status.value,
        }
    
    def list_open_claims(self, status_filter: str = "pending") -> dict[str, Any]:
        """List claims by status."""
        if status_filter == "all":
            claims = self.claim_system.list_claims()
        elif status_filter == "pending":
            claims = self.claim_system.get_pending_claims()
        elif status_filter == "contested":
            claims = self.claim_system.get_contested_claims()
        else:
            claims = self.claim_system.get_pending_claims()
        
        return {
            "count": len(claims),
            "claims": [c.model_dump() for c in claims],
        }
    
    def resolve_claim(
        self,
        claim_id: str,
        verdict: str,
        reasoning: str,
        resolved_by: str,
    ) -> dict[str, Any]:
        """Resolve a pending claim."""
        claim = self.claim_system.get_claim(claim_id)
        if not claim:
            return {"success": False, "error": f"Claim '{claim_id}' not found"}
        
        if claim.status != ClaimStatus.PENDING and claim.status != ClaimStatus.CONTESTED:
            return {"success": False, "error": f"Claim '{claim_id}' already resolved"}
        
        if verdict == "confirmed":
            claim.confirm(resolved_by, reasoning)
            # Apply effects
            if claim.effects_on_confirm:
                self._apply_claim_effects(claim)
            event_type = EventType.CLAIM_CONFIRMED
        elif verdict == "denied":
            claim.deny(resolved_by, reasoning)
            event_type = EventType.CLAIM_DENIED
        elif verdict == "contested":
            claim.contest(resolved_by, reasoning)
            event_type = EventType.CLAIM_CONTESTED
        else:
            return {"success": False, "error": f"Invalid verdict: {verdict}"}
        
        # Log the event
        self.event_log.add(Event(
            event_type=event_type,
            description=f"Claim {verdict}: {claim.description} - {reasoning}",
            actor=resolved_by,
            game_tick=self.world_state.current_tick,
            game_date=self.world_state.current_date,
            related_claim_id=claim.id,
        ))
        
        return {
            "success": True,
            "claim_id": claim_id,
            "verdict": verdict,
            "message": f"Claim '{claim_id}' {verdict}",
        }
    
    def _apply_claim_effects(self, claim: Claim) -> None:
        """Apply the effects of a confirmed claim to world state."""
        effects = claim.effects_on_confirm
        
        # Handle different effect types
        if "add_settlement" in effects:
            from src.models.world_state import Settlement, SettlementType
            data = effects["add_settlement"]
            settlement = Settlement(
                name=data.get("name", "Unknown"),
                type=SettlementType(data.get("type", "village")),
                description=data.get("description"),
                population=data.get("population", 0),
            )
            self.world_state.settlements.append(settlement)
        
        if "add_terrain" in effects:
            from src.models.world_state import Terrain, TerrainType
            data = effects["add_terrain"]
            terrain = Terrain(
                name=data.get("name", "Unknown"),
                type=TerrainType(data.get("type", "plains")),
                description=data.get("description"),
                resources_available=data.get("resources_available", []),
            )
            self.world_state.terrain.append(terrain)
        
        if "add_faction" in effects:
            from src.models.world_state import Faction
            data = effects["add_faction"]
            faction = Faction(
                name=data.get("name", "Unknown"),
                description=data.get("description"),
                power=data.get("power", 5),
                disposition=data.get("disposition", 50),
                goals=data.get("goals", []),
            )
            self.world_state.factions.append(faction)
        
        if "modify_resources" in effects:
            for resource, amount in effects["modify_resources"].items():
                self.world_state.resources.adjust(resource, amount)
    
    def apply_action(
        self,
        action_type: str,
        description: str,
        proposed_by: str,
        target: str | None = None,
        parameters: dict[str, Any] | None = None,
        costs: dict[str, int] | None = None,
        effects: list[dict[str, Any]] | None = None,
        risks: list[str] | None = None,
    ) -> dict[str, Any]:
        """Propose an action for approval."""
        proposal = ActionProposal(
            action_type=ActionType(action_type),
            description=description,
            target=target,
            parameters=parameters or {},
            costs=costs or {},
            effects=effects or [],
            risks=risks or [],
        )
        
        action_spec = proposal.to_action_spec(proposed_by)
        self._pending_actions.append(action_spec)
        
        # Log the event
        self.event_log.add(Event(
            event_type=EventType.ACTION_PROPOSED,
            description=f"Action proposed: {description}",
            actor=proposed_by,
            game_tick=self.world_state.current_tick,
            game_date=self.world_state.current_date,
            related_action_id=action_spec.id,
        ))
        
        return {
            "success": True,
            "action_id": action_spec.id,
            "requires_approval": action_spec.requires_approval,
            "cost_summary": action_spec.cost_summary(),
            "message": f"Action '{action_spec.id}' proposed" + (
                " (requires approval)" if action_spec.requires_approval else ""
            ),
        }
    
    def get_pending_actions(self) -> list[ActionSpec]:
        """Get all pending actions."""
        return [a for a in self._pending_actions if a.approved is None]
    
    def approve_action(self, action_id: str, approved_by: str) -> dict[str, Any]:
        """Approve a pending action."""
        for action in self._pending_actions:
            if action.id == action_id:
                action.approved = True
                action.approved_by = approved_by
                return self._execute_action(action)
        return {"success": False, "error": f"Action '{action_id}' not found"}
    
    def reject_action(self, action_id: str, rejected_by: str) -> dict[str, Any]:
        """Reject a pending action."""
        for action in self._pending_actions:
            if action.id == action_id:
                action.approved = False
                action.approved_by = rejected_by
                
                self.event_log.add(Event(
                    event_type=EventType.ACTION_REJECTED,
                    description=f"Action rejected: {action.description}",
                    actor=rejected_by,
                    game_tick=self.world_state.current_tick,
                    game_date=self.world_state.current_date,
                    related_action_id=action.id,
                ))
                
                return {"success": True, "message": f"Action '{action_id}' rejected"}
        return {"success": False, "error": f"Action '{action_id}' not found"}
    
    def _execute_action(self, action: ActionSpec) -> dict[str, Any]:
        """Execute an approved action."""
        from datetime import datetime
        
        # Deduct costs
        resources = self.world_state.resources
        costs = action.costs
        
        if costs.treasury and not resources.adjust("treasury", -costs.treasury):
            return {"success": False, "error": "Insufficient treasury"}
        if costs.food and not resources.adjust("food", -costs.food):
            return {"success": False, "error": "Insufficient food"}
        if costs.timber and not resources.adjust("timber", -costs.timber):
            return {"success": False, "error": "Insufficient timber"}
        if costs.iron and not resources.adjust("iron", -costs.iron):
            return {"success": False, "error": "Insufficient iron"}
        if costs.labor and not resources.adjust("labor", -costs.labor):
            return {"success": False, "error": "Insufficient labor"}
        
        # Apply effects
        for effect in action.effects:
            self._apply_effect(effect)
        
        action.executed = True
        action.executed_at = datetime.now()
        
        # Log the event
        self.event_log.add(Event(
            event_type=EventType.ACTION_EXECUTED,
            description=f"Action executed: {action.description}",
            actor=action.approved_by or "system",
            game_tick=self.world_state.current_tick,
            game_date=self.world_state.current_date,
            related_action_id=action.id,
        ))
        
        return {
            "success": True,
            "action_id": action.id,
            "message": f"Action '{action.id}' executed successfully",
        }
    
    def _apply_effect(self, effect: Any) -> None:
        """Apply a single action effect."""
        from src.models.actions import ActionEffect
        
        if isinstance(effect, dict):
            effect = ActionEffect(**effect)
        
        target_type = effect.target_type
        
        if target_type == "resource":
            if effect.is_delta:
                self.world_state.resources.adjust(effect.field, effect.change)
            else:
                setattr(self.world_state.resources, effect.field, effect.change)
        
        elif target_type == "settlement":
            settlement = self.world_state.get_settlement(effect.target_id or "")
            if settlement:
                if effect.is_delta:
                    current = getattr(settlement, effect.field, 0)
                    setattr(settlement, effect.field, current + effect.change)
                else:
                    setattr(settlement, effect.field, effect.change)
        
        elif target_type == "faction":
            faction = self.world_state.get_faction(effect.target_id or "")
            if faction:
                if effect.is_delta:
                    current = getattr(faction, effect.field, 0)
                    setattr(faction, effect.field, current + effect.change)
                else:
                    setattr(faction, effect.field, effect.change)
    
    def advance_time(self, days: int) -> dict[str, Any]:
        """Advance game time."""
        old_tick = self.world_state.current_tick
        result = self.time_system.advance(days)
        
        self.event_log.add(Event(
            event_type=EventType.TIME_ADVANCE,
            description=f"Time advanced by {days} days",
            actor="player",
            game_tick=self.world_state.current_tick,
            game_date=self.world_state.current_date,
        ))
        
        return result
    
    def log_event(
        self,
        description: str,
        actor: str,
        event_type: str = "custom",
        effects: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Log an event."""
        from src.models.events import EventEffect
        
        event_type_enum = EventType(event_type) if event_type in EventType.__members__.values() else EventType.CUSTOM
        
        effect_objs = []
        if effects:
            for e in effects:
                effect_objs.append(EventEffect(**e))
        
        event = Event(
            event_type=event_type_enum,
            description=description,
            actor=actor,
            game_tick=self.world_state.current_tick,
            game_date=self.world_state.current_date,
            effects=effect_objs,
        )
        
        self.event_log.add(event)
        
        return {
            "success": True,
            "event_id": event.id,
            "message": "Event logged",
        }
    
    def survey_area(
        self,
        area_name: str,
        survey_type: str = "general",
        depth: str = "standard",
    ) -> dict[str, Any]:
        """Survey an area - returns info and potential claims."""
        # Check if area exists in world state
        terrain = self.world_state.get_terrain(area_name)
        settlement = self.world_state.get_settlement(area_name)
        
        if terrain:
            return {
                "found": True,
                "type": "terrain",
                "data": terrain.model_dump(),
                "message": f"Surveyed known terrain: {terrain.name}",
            }
        
        if settlement:
            return {
                "found": True,
                "type": "settlement",
                "data": settlement.model_dump(),
                "message": f"Surveyed known settlement: {settlement.name}",
            }
        
        # Area not in world state - suggest proposing a claim
        return {
            "found": False,
            "area_name": area_name,
            "survey_type": survey_type,
            "depth": depth,
            "message": f"Area '{area_name}' not found in world state. Consider proposing a claim if you believe it exists.",
            "suggested_action": "propose_claim",
        }
