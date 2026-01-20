"""Validation pipeline for state changes - prevents slop and contradictions."""

from __future__ import annotations
from typing import TYPE_CHECKING, Any, Optional
import re
import json

if TYPE_CHECKING:
    from src.models.world_state import WorldState
    from src.llm.openrouter import OpenRouterClient

from src.models.state_change import (
    StateChange, 
    ChangeType, 
    ValidationStatus, 
    SemanticValidation,
)


class StructuralValidator:
    """Stage 1: Validates structure, types, and references."""
    
    # Valid top-level prefixes for extensions
    VALID_PREFIXES = {
        "advisors",    # Advisor-related state
        "factions",    # Faction-related state
        "settlements", # Settlement-related state
        "terrain",     # Terrain-related state
        "plots",       # Ongoing plots/schemes
        "relationships", # Relationships between entities
        "conditions",  # Current conditions/situations
        "history",     # Historical events/facts
        "rules",       # Dynamic game rules
        "secrets",     # Hidden information
        "rumors",      # Unconfirmed information
    }
    
    def __init__(self, world_state: "WorldState"):
        self.world_state = world_state
    
    def validate(self, change: StateChange) -> bool:
        """Run structural validation. Returns True if passed."""
        change.validation_issues = []  # Clear previous issues
        
        # 1. Check path format
        if not self._validate_path_format(change):
            change.status = ValidationStatus.REJECTED_STRUCTURAL
            return False
        
        # 2. Check path prefix is valid
        if not self._validate_path_prefix(change):
            change.status = ValidationStatus.REJECTED_STRUCTURAL
            return False
        
        # 3. Check references exist
        if not self._validate_references(change):
            change.status = ValidationStatus.REJECTED_STRUCTURAL
            return False
        
        # 4. Check type consistency
        if not self._validate_type_consistency(change):
            change.status = ValidationStatus.REJECTED_STRUCTURAL
            return False
        
        # 5. Check value quality (basic slop detection)
        if not self._validate_value_quality(change):
            # This is a warning, not an error
            pass
        
        change.status = ValidationStatus.PASSED_STRUCTURAL
        return True
    
    def _validate_path_format(self, change: StateChange) -> bool:
        """Check that the path is valid dot-notation."""
        path = change.path
        
        if not path:
            change.add_issue(
                stage="structural",
                severity="error",
                code="EMPTY_PATH",
                message="Path cannot be empty",
            )
            return False
        
        # Must be valid identifier segments separated by dots
        pattern = r'^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$'
        if not re.match(pattern, path, re.IGNORECASE):
            change.add_issue(
                stage="structural",
                severity="error",
                code="INVALID_PATH_FORMAT",
                message=f"Path '{path}' is not valid dot-notation (use lowercase with underscores)",
                path=path,
                suggestion="Use format like 'advisors.marshal.resentment.incident_name'",
            )
            return False
        
        return True
    
    def _validate_path_prefix(self, change: StateChange) -> bool:
        """Check that the path starts with a valid prefix."""
        if change.change_type == ChangeType.ADD_RULE:
            return True  # Rules don't need path validation
        
        prefix = change.path.split(".")[0]
        
        if prefix not in self.VALID_PREFIXES:
            change.add_issue(
                stage="structural",
                severity="error",
                code="INVALID_PREFIX",
                message=f"Path prefix '{prefix}' is not valid",
                path=change.path,
                suggestion=f"Use one of: {', '.join(sorted(self.VALID_PREFIXES))}",
            )
            return False
        
        return True
    
    def _validate_references(self, change: StateChange) -> bool:
        """Check that referenced entities exist."""
        path_parts = change.path.split(".")
        
        if len(path_parts) < 2:
            return True
        
        prefix = path_parts[0]
        entity_ref = path_parts[1]
        
        # Check advisor references
        if prefix == "advisors":
            valid_advisors = {"steward", "marshal", "chancellor"}
            if entity_ref not in valid_advisors:
                change.add_issue(
                    stage="structural",
                    severity="error",
                    code="INVALID_ADVISOR_REF",
                    message=f"Unknown advisor '{entity_ref}'",
                    path=change.path,
                    suggestion=f"Use one of: {', '.join(valid_advisors)}",
                )
                return False
        
        # Check faction references
        elif prefix == "factions":
            faction = self.world_state.get_faction(entity_ref)
            # Also check by converting underscores to spaces
            if not faction:
                faction_name = entity_ref.replace("_", " ")
                faction = self.world_state.get_faction(faction_name)
            
            if not faction:
                # This is a warning - we might be creating info about a new faction
                change.add_issue(
                    stage="structural",
                    severity="warning",
                    code="UNKNOWN_FACTION_REF",
                    message=f"Faction '{entity_ref}' not found in world state",
                    path=change.path,
                    suggestion="This might be intentional if creating info about an external faction",
                )
        
        # Check settlement references
        elif prefix == "settlements":
            settlement = self.world_state.get_settlement(entity_ref)
            if not settlement:
                settlement_name = entity_ref.replace("_", " ")
                settlement = self.world_state.get_settlement(settlement_name)
            
            if not settlement:
                change.add_issue(
                    stage="structural",
                    severity="warning",
                    code="UNKNOWN_SETTLEMENT_REF",
                    message=f"Settlement '{entity_ref}' not found in world state",
                    path=change.path,
                )
        
        return True
    
    def _validate_type_consistency(self, change: StateChange) -> bool:
        """Check that we're not overwriting a dict with a primitive or vice versa."""
        if change.change_type == ChangeType.DELETE_EXTENSION:
            return True
        
        existing = self.world_state.get_extension(change.path)
        
        if existing is not None:
            # Check type consistency
            existing_is_dict = isinstance(existing, dict)
            new_is_dict = isinstance(change.new_value, dict)
            
            if existing_is_dict and not new_is_dict:
                change.add_issue(
                    stage="structural",
                    severity="error",
                    code="TYPE_MISMATCH",
                    message=f"Cannot replace dict at '{change.path}' with non-dict value",
                    path=change.path,
                    suggestion="Use a dict value or delete the existing data first",
                )
                return False
        
        return True
    
    def _validate_value_quality(self, change: StateChange) -> bool:
        """Basic quality checks on the value being set."""
        if change.change_type == ChangeType.DELETE_EXTENSION:
            return True
        
        value = change.new_value
        
        # Check for empty/meaningless values
        if value is None or value == "" or value == {}:
            change.add_issue(
                stage="structural",
                severity="warning",
                code="EMPTY_VALUE",
                message="Value is empty or meaningless",
                suggestion="Provide a meaningful value with context",
            )
            return False
        
        # Check for required reason
        if not change.reason or len(change.reason) < 10:
            change.add_issue(
                stage="structural",
                severity="warning",
                code="MISSING_REASON",
                message="Reason is missing or too short",
                suggestion="Provide a detailed reason for this change",
            )
        
        return True


class SemanticValidator:
    """Stage 2: LLM-powered validation for consistency and quality."""
    
    # Quality thresholds
    MIN_QUALITY_SCORE = 60
    
    def __init__(self, llm: "OpenRouterClient", world_state: "WorldState"):
        self.llm = llm
        self.world_state = world_state
    
    def validate(self, change: StateChange) -> bool:
        """Run semantic validation using LLM. Returns True if passed."""
        from src.llm.openrouter import ModelTier
        
        # Build context for validation
        context = self._build_validation_context(change)
        
        # Ask LLM to validate
        system_prompt = """You are a quality validator for a strategy simulation game. Your job is to check proposed state changes for:

1. CONTRADICTIONS: Does this conflict with existing state?
2. CONSISTENCY: Does this fit the established world, characters, and period?
3. QUALITY: Is this specific and meaningful, not generic AI slop?
4. CONSEQUENCES: What cascading effects should occur?

You must be STRICT about quality. Reject:
- Generic descriptions like "the advisor is upset" (should specify HOW they're upset)
- Vague consequences like "this may affect things" (should specify WHAT)
- Numbers without justification (why exactly 75 loyalty?)
- Contradictions with established character traits

Respond with a JSON object matching this schema:
{
    "is_consistent": boolean,
    "is_specific": boolean,
    "has_contradictions": boolean,
    "contradictions": ["list of specific contradictions found"],
    "quality_score": 0-100,
    "quality_issues": ["list of quality problems"],
    "cascading_effects": [{"path": "...", "value": {...}, "reason": "..."}],
    "reasoning": "explanation of your decision",
    "approved": boolean
}"""

        user_prompt = f"""VALIDATE THIS STATE CHANGE:

{context}

Check for contradictions, consistency, and quality. Be strict - reject slop."""

        try:
            response = self.llm.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                tier=ModelTier.ORCHESTRATOR,
                temperature=0.2,
                max_tokens=1500,
            )
            
            # Parse response
            result = self._parse_validation_response(response.content)
            
            # Create SemanticValidation object
            validation = SemanticValidation(
                is_consistent=result.get("is_consistent", False),
                is_specific=result.get("is_specific", False),
                has_contradictions=result.get("has_contradictions", False),
                contradictions=result.get("contradictions", []),
                quality_score=result.get("quality_score", 0),
                quality_issues=result.get("quality_issues", []),
                cascading_effects=result.get("cascading_effects", []),
                reasoning=result.get("reasoning", ""),
            )
            
            change.semantic_validation = validation
            
            # Determine pass/fail
            approved = result.get("approved", False)
            
            if not approved:
                # Add issues based on validation result
                if validation.has_contradictions:
                    for contradiction in validation.contradictions:
                        change.add_issue(
                            stage="semantic",
                            severity="error",
                            code="CONTRADICTION",
                            message=contradiction,
                        )
                
                for issue in validation.quality_issues:
                    change.add_issue(
                        stage="semantic",
                        severity="error",
                        code="QUALITY_ISSUE",
                        message=issue,
                    )
                
                change.status = ValidationStatus.REJECTED_SEMANTIC
                return False
            
            change.status = ValidationStatus.PASSED_SEMANTIC
            return True
            
        except Exception as e:
            change.add_issue(
                stage="semantic",
                severity="error",
                code="VALIDATION_ERROR",
                message=f"Semantic validation failed: {str(e)}",
            )
            change.status = ValidationStatus.REJECTED_SEMANTIC
            return False
    
    def _build_validation_context(self, change: StateChange) -> str:
        """Build context string for validation prompt."""
        lines = []
        
        # Current world state summary
        lines.append("CURRENT WORLD STATE:")
        lines.append(self.world_state.summary())
        lines.append("")
        
        # Relevant existing extensions
        prefix = change.path.split(".")[0]
        existing_paths = self.world_state.list_extensions(prefix)
        if existing_paths:
            lines.append(f"EXISTING {prefix.upper()} EXTENSIONS:")
            for path in existing_paths[:20]:
                value = self.world_state.get_extension(path)
                lines.append(f"  {path}: {json.dumps(value, default=str)[:100]}")
            lines.append("")
        
        # Active rules that might be relevant
        active_rules = self.world_state.get_active_rules()
        if active_rules:
            lines.append("ACTIVE RULES:")
            for rule in active_rules[:10]:
                lines.append(f"  • {rule.trigger} → {rule.effect}")
            lines.append("")
        
        # The proposed change
        lines.append("PROPOSED CHANGE:")
        lines.append(f"  Type: {change.change_type.value}")
        lines.append(f"  Path: {change.path}")
        lines.append(f"  New Value: {json.dumps(change.new_value, default=str)}")
        lines.append(f"  Reason: {change.reason}")
        lines.append(f"  Proposed by: {change.proposed_by}")
        
        if change.old_value is not None:
            lines.append(f"  Old Value: {json.dumps(change.old_value, default=str)}")
        
        return "\n".join(lines)
    
    def _parse_validation_response(self, content: str) -> dict[str, Any]:
        """Parse the LLM's validation response."""
        if not content:
            return {"approved": False, "reasoning": "No response from validator"}
        
        try:
            # Try to find JSON in the response
            import re
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
        
        # Fallback: assume rejection if we can't parse
        return {
            "approved": False,
            "reasoning": f"Could not parse validation response: {content[:200]}",
        }


class ValidationPipeline:
    """Complete validation pipeline for state changes."""
    
    def __init__(self, world_state: "WorldState", llm: Optional["OpenRouterClient"] = None):
        self.world_state = world_state
        self.structural = StructuralValidator(world_state)
        self.semantic = SemanticValidator(llm, world_state) if llm else None
        
        # Configuration
        self.require_semantic_validation = True
        self.auto_approve_low_risk = True
    
    def validate(self, change: StateChange, skip_semantic: bool = False) -> bool:
        """Run the full validation pipeline."""
        # Stage 1: Structural
        if not self.structural.validate(change):
            return False
        
        # Check if we can skip semantic validation
        if skip_semantic or not self.require_semantic_validation:
            change.status = ValidationStatus.APPROVED
            return True
        
        # Check for low-risk auto-approval
        if self.auto_approve_low_risk and self._is_low_risk(change):
            change.status = ValidationStatus.APPROVED
            return True
        
        # Stage 2: Semantic
        if self.semantic:
            if not self.semantic.validate(change):
                return False
        
        # All passed
        change.status = ValidationStatus.APPROVED
        return True
    
    def _is_low_risk(self, change: StateChange) -> bool:
        """Check if a change is low-risk and can skip semantic validation."""
        # Observations and rumors are low-risk
        if change.path.startswith("rumors.") or change.path.startswith("conditions."):
            return True
        
        # Appending to history is low-risk
        if change.path.startswith("history."):
            return True
        
        return False
    
    def apply_if_valid(self, change: StateChange) -> bool:
        """Validate and apply a change if it passes."""
        if not self.validate(change):
            return False
        
        return self.apply(change)
    
    def apply(self, change: StateChange) -> bool:
        """Apply an approved change to the world state."""
        if not change.is_approved():
            return False
        
        from datetime import datetime
        
        if change.change_type == ChangeType.SET_EXTENSION:
            # Store old value for rollback
            change.old_value = self.world_state.get_extension(change.path)
            
            # Apply the change with metadata
            metadata = {
                "change_id": change.id,
                "proposed_by": change.proposed_by,
                "reason": change.reason,
                "applied_at": datetime.now().isoformat(),
            }
            self.world_state.set_extension(change.path, change.new_value, metadata)
            
        elif change.change_type == ChangeType.DELETE_EXTENSION:
            change.old_value = self.world_state.get_extension(change.path)
            self.world_state.delete_extension(change.path)
            
        elif change.change_type == ChangeType.ADD_RULE:
            if isinstance(change.new_value, dict):
                self.world_state.add_rule(
                    trigger=change.new_value.get("trigger", ""),
                    effect=change.new_value.get("effect", ""),
                    reason=change.reason,
                    created_by=change.proposed_by,
                )
        
        change.applied_at = datetime.now()
        
        # Process cascading effects
        if change.semantic_validation and change.semantic_validation.cascading_effects:
            for effect in change.semantic_validation.cascading_effects:
                cascade = StateChange(
                    change_type=ChangeType.SET_EXTENSION,
                    path=effect.get("path", ""),
                    new_value=effect.get("value"),
                    reason=effect.get("reason", f"Cascaded from {change.id}"),
                    proposed_by="system",
                    triggered_by=change.id,
                )
                # Validate and apply cascading changes (skip semantic to avoid infinite loop)
                if self.validate(cascade, skip_semantic=True):
                    self.apply(cascade)
                    change.cascaded_changes.append(cascade.id)
        
        return True
