"""Tool registry - defines and registers all advisor tools with strict schemas."""

from __future__ import annotations
from typing import Any, Callable, Optional
from pydantic import BaseModel, Field


class ToolParameter(BaseModel):
    """Definition of a tool parameter."""
    name: str
    type: str  # "string", "integer", "boolean", "object", "array"
    description: str
    required: bool = True
    enum: Optional[list[str]] = None
    default: Any = None
    properties: Optional[dict[str, Any]] = None  # For object types
    items: Optional[dict[str, Any]] = None  # For array types


class Tool(BaseModel):
    """A tool that advisors can call."""
    name: str
    description: str
    parameters: list[ToolParameter] = Field(default_factory=list)
    allowed_roles: list[str] = Field(default_factory=lambda: ["steward", "marshal", "chancellor"])
    requires_approval: bool = False
    
    def to_openai_schema(self) -> dict[str, Any]:
        """Convert to OpenAI function calling schema."""
        properties = {}
        required = []
        
        for param in self.parameters:
            prop: dict[str, Any] = {
                "type": param.type,
                "description": param.description,
            }
            if param.enum:
                prop["enum"] = param.enum
            if param.properties:
                prop["properties"] = param.properties
            if param.items:
                prop["items"] = param.items
            
            properties[param.name] = prop
            
            if param.required:
                required.append(param.name)
        
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                }
            }
        }


class ToolRegistry:
    """Registry of all available tools."""
    
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._handlers: dict[str, Callable[..., Any]] = {}
        self._register_core_tools()
    
    def _register_core_tools(self) -> None:
        """Register the 8 core tools."""
        
        # 1. get_world_state
        self.register(Tool(
            name="get_world_state",
            description="Read the current world state. Use this to understand the current situation before making proposals.",
            parameters=[
                ToolParameter(
                    name="scope",
                    type="string",
                    description="What part of the world state to retrieve",
                    enum=["full", "resources", "settlements", "factions", "populations", "terrain", "infrastructure", "claims"],
                    default="full",
                    required=False,
                ),
            ],
            requires_approval=False,
        ))
        
        # 2. propose_claim
        self.register(Tool(
            name="propose_claim",
            description="Propose a new fact about the world that is not currently in the world state. Claims must be validated before becoming canon.",
            parameters=[
                ToolParameter(
                    name="claim_type",
                    type="string",
                    description="Type of claim being made",
                    enum=["entity_exists", "entity_property", "relationship", "ownership", "resource_level", "population_state", "historical_event", "current_condition", "custom"],
                ),
                ToolParameter(
                    name="description",
                    type="string",
                    description="Clear description of what is being claimed",
                ),
                ToolParameter(
                    name="evidence",
                    type="array",
                    description="Evidence supporting this claim",
                    items={"type": "object", "properties": {
                        "type": {"type": "string", "description": "Type of evidence: observation, report, survey, historical, logical"},
                        "description": {"type": "string", "description": "Description of the evidence"},
                        "confidence": {"type": "integer", "description": "Confidence level 0-100"},
                    }},
                    required=False,
                ),
                ToolParameter(
                    name="effects_on_confirm",
                    type="object",
                    description="What changes to world state if this claim is confirmed",
                    required=False,
                ),
            ],
            requires_approval=True,
        ))
        
        # 3. list_open_claims
        self.register(Tool(
            name="list_open_claims",
            description="List all pending claims awaiting resolution.",
            parameters=[
                ToolParameter(
                    name="status_filter",
                    type="string",
                    description="Filter by claim status",
                    enum=["all", "pending", "contested"],
                    default="pending",
                    required=False,
                ),
            ],
            requires_approval=False,
        ))
        
        # 4. resolve_claim
        self.register(Tool(
            name="resolve_claim",
            description="Resolve a pending claim. Only the Chancellor can use this tool, and only for non-controversial claims.",
            parameters=[
                ToolParameter(
                    name="claim_id",
                    type="string",
                    description="ID of the claim to resolve",
                ),
                ToolParameter(
                    name="verdict",
                    type="string",
                    description="Resolution verdict",
                    enum=["confirmed", "denied", "contested"],
                ),
                ToolParameter(
                    name="reasoning",
                    type="string",
                    description="Explanation for the verdict",
                ),
            ],
            allowed_roles=["chancellor", "orchestrator"],
            requires_approval=True,
        ))
        
        # 5. apply_action
        self.register(Tool(
            name="apply_action",
            description="Propose a structured action that modifies the world state.",
            parameters=[
                ToolParameter(
                    name="action_type",
                    type="string",
                    description="Type of action",
                    enum=[
                        "resource_transfer", "resource_production", "resource_consumption",
                        "levy_troops", "dismiss_troops", "relocate_population",
                        "build", "repair", "demolish",
                        "grant_right", "revoke_right", "issue_decree",
                        "negotiate", "reward_faction", "punish_faction",
                        "deploy_forces", "fortify", "patrol",
                        "survey", "investigate",
                        "custom"
                    ],
                ),
                ToolParameter(
                    name="description",
                    type="string",
                    description="Description of the action",
                ),
                ToolParameter(
                    name="target",
                    type="string",
                    description="Primary target of the action (settlement, faction, etc.)",
                    required=False,
                ),
                ToolParameter(
                    name="parameters",
                    type="object",
                    description="Action-specific parameters",
                    required=False,
                ),
                ToolParameter(
                    name="costs",
                    type="object",
                    description="Resource costs: {treasury, food, timber, iron, labor, time_days}",
                    properties={
                        "treasury": {"type": "integer"},
                        "food": {"type": "integer"},
                        "timber": {"type": "integer"},
                        "iron": {"type": "integer"},
                        "labor": {"type": "integer"},
                        "time_days": {"type": "integer"},
                    },
                    required=False,
                ),
                ToolParameter(
                    name="effects",
                    type="array",
                    description="Expected effects of this action",
                    items={"type": "object", "properties": {
                        "target_type": {"type": "string"},
                        "target_id": {"type": "string"},
                        "field": {"type": "string"},
                        "change": {"type": "string"},
                        "is_delta": {"type": "boolean"},
                    }},
                    required=False,
                ),
                ToolParameter(
                    name="risks",
                    type="array",
                    description="Known risks of this action",
                    items={"type": "string"},
                    required=False,
                ),
            ],
            requires_approval=True,
        ))
        
        # 6. advance_time
        self.register(Tool(
            name="advance_time",
            description="Advance the game time by a number of days. This triggers time-based effects.",
            parameters=[
                ToolParameter(
                    name="days",
                    type="integer",
                    description="Number of days to advance (1-30)",
                ),
            ],
            allowed_roles=["player"],  # Only player can advance time
            requires_approval=False,
        ))
        
        # 7. log_event
        self.register(Tool(
            name="log_event",
            description="Record an event or observation in the game log.",
            parameters=[
                ToolParameter(
                    name="description",
                    type="string",
                    description="Description of the event",
                ),
                ToolParameter(
                    name="event_type",
                    type="string",
                    description="Type of event",
                    enum=["incident", "discovery", "arrival", "departure", "conflict", "resolution", "custom"],
                    required=False,
                ),
                ToolParameter(
                    name="effects",
                    type="array",
                    description="Effects this event had",
                    items={"type": "object"},
                    required=False,
                ),
            ],
            requires_approval=False,
        ))
        
        # 8. survey_area
        self.register(Tool(
            name="survey_area",
            description="Conduct a survey of an area to discover information. This may reveal new facts that can be proposed as claims.",
            parameters=[
                ToolParameter(
                    name="area_name",
                    type="string",
                    description="Name or description of the area to survey",
                ),
                ToolParameter(
                    name="survey_type",
                    type="string",
                    description="Type of survey",
                    enum=["general", "resources", "military", "population", "legal"],
                    default="general",
                    required=False,
                ),
                ToolParameter(
                    name="depth",
                    type="string",
                    description="Depth of investigation",
                    enum=["cursory", "standard", "thorough"],
                    default="standard",
                    required=False,
                ),
            ],
            requires_approval=False,
        ))
    
    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool
    
    def set_handler(self, tool_name: str, handler: Callable[..., Any]) -> None:
        """Set the handler function for a tool."""
        if tool_name not in self._tools:
            raise ValueError(f"Unknown tool: {tool_name}")
        self._handlers[tool_name] = handler
    
    def get(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self._tools.get(name)
    
    def get_handler(self, name: str) -> Optional[Callable[..., Any]]:
        """Get a tool's handler function."""
        return self._handlers.get(name)
    
    def list_tools(self) -> list[Tool]:
        """List all registered tools."""
        return list(self._tools.values())
    
    def get_tools_for_role(self, role: str) -> list[Tool]:
        """Get tools available to a specific role."""
        return [t for t in self._tools.values() if role in t.allowed_roles]
    
    def get_openai_tools(self, role: Optional[str] = None) -> list[dict[str, Any]]:
        """Get tools in OpenAI function calling format."""
        tools = self.get_tools_for_role(role) if role else self.list_tools()
        return [t.to_openai_schema() for t in tools]
    
    def execute(self, tool_name: str, **kwargs: Any) -> Any:
        """Execute a tool by name."""
        handler = self._handlers.get(tool_name)
        if not handler:
            raise ValueError(f"No handler registered for tool: {tool_name}")
        return handler(**kwargs)
