"""State tools - tools for reading and writing dynamic state extensions."""

from __future__ import annotations
from typing import TYPE_CHECKING, Any, Optional
import fnmatch

if TYPE_CHECKING:
    from src.models.world_state import WorldState
    from src.systems.validation import ValidationPipeline

from src.models.state_change import StateChange, ChangeType


class StateToolHandlers:
    """Handlers for state manipulation tools."""
    
    def __init__(
        self, 
        world_state: "WorldState", 
        validation: "ValidationPipeline",
        auto_apply: bool = True,
    ):
        self.world_state = world_state
        self.validation = validation
        self.auto_apply = auto_apply  # If True, apply changes immediately after validation
        self._pending_changes: list[StateChange] = []
    
    def extend_state(
        self,
        path: str,
        value: Any,
        reason: str,
        proposed_by: str,
        skip_semantic: bool = False,
    ) -> dict[str, Any]:
        """Set a value at an extension path.
        
        Example:
            extend_state(
                path="advisors.marshal.resentment.clockmaker_incident",
                value={"severity": "moderate", "reason": "Forced to threaten civilians"},
                reason="Marshal was ordered to coerce clockmakers against his principles",
                proposed_by="marshal"
            )
        """
        change = StateChange(
            change_type=ChangeType.SET_EXTENSION,
            path=path,
            new_value=value,
            reason=reason,
            proposed_by=proposed_by,
        )
        
        # Validate
        is_valid = self.validation.validate(change, skip_semantic=skip_semantic)
        
        if is_valid and self.auto_apply:
            self.validation.apply(change)
            return {
                "success": True,
                "message": f"State set at '{path}'",
                "change_id": change.id,
                "status": change.status.value,
                "cascaded": len(change.cascaded_changes),
            }
        elif is_valid:
            self._pending_changes.append(change)
            return {
                "success": True,
                "message": f"Change validated, pending application",
                "change_id": change.id,
                "status": change.status.value,
            }
        else:
            # Return validation errors
            issues = [{"severity": i.severity, "code": i.code, "message": i.message} 
                     for i in change.validation_issues]
            return {
                "success": False,
                "message": f"Validation failed for '{path}'",
                "change_id": change.id,
                "status": change.status.value,
                "issues": issues,
            }
    
    def query_state(
        self,
        path_pattern: str,
        include_metadata: bool = False,
    ) -> dict[str, Any]:
        """Query state at a path or pattern.
        
        Supports wildcards:
            query_state("advisors.marshal.*")  # All marshal extensions
            query_state("advisors.*.resentment.*")  # All advisor resentments
        """
        results = {}
        
        # Get all extension paths
        all_paths = self.world_state.list_extensions()
        
        # Handle wildcard patterns
        if "*" in path_pattern:
            # Convert to fnmatch pattern (dots to / for matching)
            fnmatch_pattern = path_pattern.replace(".", "/")
            
            for ext_path in all_paths:
                fnmatch_path = ext_path.replace(".", "/")
                if fnmatch.fnmatch(fnmatch_path, fnmatch_pattern):
                    value = self.world_state.get_extension(ext_path)
                    if not include_metadata and isinstance(value, dict):
                        # Strip metadata
                        value = {k: v for k, v in value.items() if not k.startswith("_")}
                    results[ext_path] = value
        else:
            # Direct path lookup
            value = self.world_state.get_extension(path_pattern)
            if value is not None:
                if not include_metadata and isinstance(value, dict):
                    value = {k: v for k, v in value.items() if not k.startswith("_")}
                results[path_pattern] = value
        
        return {
            "success": True,
            "path_pattern": path_pattern,
            "results": results,
            "count": len(results),
        }
    
    def delete_extension(
        self,
        path: str,
        reason: str,
        proposed_by: str,
    ) -> dict[str, Any]:
        """Delete a value at an extension path."""
        change = StateChange(
            change_type=ChangeType.DELETE_EXTENSION,
            path=path,
            new_value=None,
            reason=reason,
            proposed_by=proposed_by,
        )
        
        # Store old value
        change.old_value = self.world_state.get_extension(path)
        
        if change.old_value is None:
            return {
                "success": False,
                "message": f"Path '{path}' does not exist",
            }
        
        # Validate (structural only for deletes)
        is_valid = self.validation.validate(change, skip_semantic=True)
        
        if is_valid and self.auto_apply:
            self.validation.apply(change)
            return {
                "success": True,
                "message": f"Deleted state at '{path}'",
                "change_id": change.id,
                "old_value": change.old_value,
            }
        else:
            issues = [{"severity": i.severity, "code": i.code, "message": i.message} 
                     for i in change.validation_issues]
            return {
                "success": False,
                "message": f"Delete failed for '{path}'",
                "issues": issues,
            }
    
    def add_rule(
        self,
        trigger: str,
        effect: str,
        reason: str,
        proposed_by: str,
    ) -> dict[str, Any]:
        """Add a dynamic game rule.
        
        Example:
            add_rule(
                trigger="When advisor resentment severity is 'high'",
                effect="Advisor may refuse direct orders",
                reason="Accumulated grievances lead to insubordination",
                proposed_by="orchestrator"
            )
        """
        change = StateChange(
            change_type=ChangeType.ADD_RULE,
            path="rules.dynamic",
            new_value={
                "trigger": trigger,
                "effect": effect,
            },
            reason=reason,
            proposed_by=proposed_by,
        )
        
        # Validate (semantic validation for rules is important)
        is_valid = self.validation.validate(change, skip_semantic=False)
        
        if is_valid and self.auto_apply:
            rule = self.world_state.add_rule(
                trigger=trigger,
                effect=effect,
                reason=reason,
                created_by=proposed_by,
            )
            return {
                "success": True,
                "message": f"Rule added: {trigger} → {effect}",
                "rule_id": rule.id,
            }
        else:
            issues = [{"severity": i.severity, "code": i.code, "message": i.message} 
                     for i in change.validation_issues]
            return {
                "success": False,
                "message": "Rule validation failed",
                "issues": issues,
            }
    
    def list_rules(self, active_only: bool = True) -> dict[str, Any]:
        """List all dynamic rules."""
        if active_only:
            rules = self.world_state.get_active_rules()
        else:
            rules = self.world_state.dynamic_rules
        
        return {
            "success": True,
            "rules": [
                {
                    "id": r.id,
                    "trigger": r.trigger,
                    "effect": r.effect,
                    "reason": r.reason,
                    "created_by": r.created_by,
                    "active": r.active,
                }
                for r in rules
            ],
            "count": len(rules),
        }
    
    def get_pending_changes(self) -> list[StateChange]:
        """Get changes that passed validation but haven't been applied."""
        return self._pending_changes
    
    def apply_pending_change(self, change_id: str) -> bool:
        """Apply a specific pending change."""
        for i, change in enumerate(self._pending_changes):
            if change.id == change_id:
                if self.validation.apply(change):
                    self._pending_changes.pop(i)
                    return True
        return False


def get_state_tool_schemas() -> list[dict]:
    """Get OpenAI-format tool schemas for state tools."""
    return [
        {
            "type": "function",
            "function": {
                "name": "extend_state",
                "description": "Set or update a value in the dynamic state extensions. Use this to record new information about the world, relationships, conditions, or any other data the game should track. The path should use dot-notation (e.g., 'advisors.marshal.resentment.incident_name').",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Dot-notation path for the state (e.g., 'advisors.marshal.resentment.clockmaker_incident'). Valid prefixes: advisors, factions, settlements, terrain, plots, relationships, conditions, history, rules, secrets, rumors",
                        },
                        "value": {
                            "type": "object",
                            "description": "The value to store. Should be a dict with specific, meaningful data. Include 'severity', 'reason', 'effects', etc. as appropriate.",
                        },
                        "reason": {
                            "type": "string",
                            "description": "Detailed explanation of why this state is being set. Must be specific, not generic.",
                        },
                    },
                    "required": ["path", "value", "reason"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_state",
                "description": "Query the dynamic state extensions. Supports wildcards with * (e.g., 'advisors.*.resentment.*' to find all advisor resentments).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path_pattern": {
                            "type": "string",
                            "description": "Path or pattern to query (supports * wildcards)",
                        },
                    },
                    "required": ["path_pattern"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "delete_extension",
                "description": "Delete a value from the dynamic state extensions.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Dot-notation path to delete",
                        },
                        "reason": {
                            "type": "string",
                            "description": "Why this state is being deleted",
                        },
                    },
                    "required": ["path", "reason"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "add_rule",
                "description": "Create a new dynamic game rule. Rules define when->then relationships that affect gameplay.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "trigger": {
                            "type": "string",
                            "description": "When this rule activates (natural language condition, e.g., 'When advisor resentment severity reaches high')",
                        },
                        "effect": {
                            "type": "string",
                            "description": "What happens when triggered (natural language effect, e.g., 'Advisor may refuse direct orders')",
                        },
                        "reason": {
                            "type": "string",
                            "description": "Why this rule should exist in the game",
                        },
                    },
                    "required": ["trigger", "effect", "reason"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_rules",
                "description": "List all dynamic game rules that have been created.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "active_only": {
                            "type": "boolean",
                            "description": "Only show active rules (default: true)",
                        },
                    },
                    "required": [],
                },
            },
        },
    ]
