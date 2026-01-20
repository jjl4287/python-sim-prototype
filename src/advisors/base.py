"""Base advisor class - uses dynamic profiles for personality."""

from __future__ import annotations
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.llm.openrouter import OpenRouterClient
    from src.tools.registry import ToolRegistry
    from src.tools.handlers import ToolHandlers
    from src.tools.state_tools import StateToolHandlers
    from src.models.world_state import WorldState
    from src.models.advisors import AdvisorProfile


class DynamicAdvisor:
    """An advisor whose personality comes from a dynamically generated profile."""
    
    # Tool access by role - now includes state tools for dynamic world building
    ROLE_TOOLS = {
        "steward": [
            "get_world_state",
            "propose_claim",
            "list_open_claims",
            "apply_action",
            "log_event",
            "survey_area",
            # State tools - for dynamic world building
            "extend_state",
            "query_state",
        ],
        "marshal": [
            "get_world_state",
            "propose_claim",
            "list_open_claims",
            "apply_action",
            "log_event",
            "survey_area",
            # State tools
            "extend_state",
            "query_state",
        ],
        "chancellor": [
            "get_world_state",
            "propose_claim",
            "list_open_claims",
            "resolve_claim",
            "apply_action",
            "log_event",
            "survey_area",
            # State tools - chancellor can also add rules
            "extend_state",
            "query_state",
            "add_rule",
        ],
    }
    
    # Domain descriptions by role
    ROLE_DOMAINS = {
        "steward": "economy, resources, trade, production, and material sustenance",
        "marshal": "defense, warriors, security, military logistics, and protection",
        "chancellor": "law, custom, diplomacy, faction relations, and dispute resolution",
    }
    
    def __init__(
        self,
        profile: "AdvisorProfile",
        llm_client: "OpenRouterClient",
        tool_registry: "ToolRegistry",
        tool_handlers: "ToolHandlers",
        world_state: "WorldState",
        state_tools: "StateToolHandlers" = None,
    ):
        self.profile = profile
        self.llm = llm_client
        self.tools = tool_registry
        self.handlers = tool_handlers
        self.world_state = world_state
        self.state_tools = state_tools  # For dynamic state extensions
        self._conversation_history: list[dict[str, Any]] = []
    
    @property
    def name(self) -> str:
        return self.profile.name
    
    @property
    def title(self) -> str:
        return self.profile.title
    
    @property
    def role(self) -> str:
        return self.profile.role.value
    
    @property
    def domain(self) -> str:
        return self.ROLE_DOMAINS.get(self.role, "general matters")
    
    @property
    def allowed_tools(self) -> list[str]:
        return self.ROLE_TOOLS.get(self.role, [])
    
    @property
    def system_prompt(self) -> str:
        """Build the full system prompt from the dynamic profile."""
        ctx = self.world_state.advisor_context
        ruler_title = getattr(ctx, 'ruler_title', 'Ruler')
        
        base_prompt = f"""You are {self.profile.name}, {self.profile.title}, advisor on {self.domain}.

{self.profile.get_system_prompt_fragment()}

SETTING:
Historical period: {ctx.historical_period}
Technology level: {ctx.technology_level}
Cultural norms: {', '.join(ctx.cultural_norms) if ctx.cultural_norms else 'Standard customs'}
Taboos: {', '.join(ctx.taboos) if ctx.taboos else 'None specified'}

HOW TO BEHAVE:
- Speak as {self.profile.name} would - use your defined speech style
- Your biases should color your advice (you may not even realize you have them)
- Your personal goals may influence your recommendations
- Reference your relationships with factions when relevant
- You may express reservations about other advisors based on your relationships with them
- Address the ruler as "{ruler_title}"

CRITICAL TOOL USAGE:
1. When you survey an area not in the world state, IMMEDIATELY propose a claim for its existence
2. Never state facts not in the world state - propose them as claims first
3. After proposing a claim, explain what you'd recommend once it's confirmed
4. Be specific with names, quantities, and locations

DYNAMIC STATE (extend_state, query_state):
- Use extend_state to record NEW information that the game should track
- Record your emotional reactions, resentments, suspicions, and observations
- Track relationships, ongoing plots, rumors, and conditions
- Path format: "category.entity.type.name" (e.g., "advisors.marshal.resentment.clockmaker_incident")
- Values must be SPECIFIC with severity, reason, effects - not generic slop
- If the {ruler_title} forces you to act against your nature, record your reaction!
- Query existing state before setting to avoid contradictions

CONSTRAINTS:
- Only propose actions within your domain ({self.domain})
- For matters outside your domain, defer to the appropriate advisor
- Significant changes require the {ruler_title}'s approval
- State changes go through validation - be specific to pass quality checks
"""
        return base_prompt
    
    def get_available_tools(self) -> list[dict[str, Any]]:
        """Get OpenAI-format tool schemas for this advisor."""
        # Get core tools from registry
        all_tools = self.tools.get_openai_tools(self.role)
        tools = [t for t in all_tools if t["function"]["name"] in self.allowed_tools]
        
        # Add state tools if available
        if self.state_tools:
            from src.tools.state_tools import get_state_tool_schemas
            state_schemas = get_state_tool_schemas()
            # Filter to only tools this role can use
            state_tool_names = {"extend_state", "query_state", "delete_extension", "add_rule", "list_rules"}
            allowed_state_tools = state_tool_names & set(self.allowed_tools)
            for schema in state_schemas:
                if schema["function"]["name"] in allowed_state_tools:
                    tools.append(schema)
        
        return tools
    
    # Sliding window size for conversation history
    CONTEXT_WINDOW_SIZE = 6
    
    def _build_context_message(self) -> str:
        """Build a context message with current world state summary."""
        # Get list of known locations for fuzzy matching hints
        locations = []
        for t in self.world_state.terrain:
            locations.append(t.name)
        for s in self.world_state.settlements:
            locations.append(s.name)
        
        location_list = ", ".join(locations) if locations else "None recorded"
        
        return f"""CURRENT WORLD STATE (ALWAYS TRUST THIS OVER MEMORY):
{self.world_state.summary()}

KNOWN LOCATIONS: {location_list}

Note: If the player mentions a location similar to but not exactly matching a known location, ask for clarification. For example, if they say "Whispering Plains" but "The Whispering Pines" exists, ask "Did you mean The Whispering Pines?"
"""
    
    def _get_messages(self, user_query: str) -> list[dict[str, Any]]:
        """Build the message list for the LLM with sliding window context."""
        # Always start with system prompt
        messages = [
            {"role": "system", "content": self.system_prompt},
        ]
        
        # Add sliding window of conversation history
        history_window = self._conversation_history[-self.CONTEXT_WINDOW_SIZE:]
        for msg in history_window:
            messages.append(msg)
        
        # ALWAYS add fresh world state right before the new query
        # This ensures advisor sees current state even if things changed
        messages.append({
            "role": "user", 
            "content": f"[UPDATED WORLD STATE]\n{self._build_context_message()}\n\n[QUERY]\n{user_query}"
        })
        
        return messages
    
    def process_query(self, query: str) -> dict[str, Any]:
        """Process a query from the player and return a response."""
        from src.llm.openrouter import ModelTier
        
        messages = self._get_messages(query)
        tools = self.get_available_tools()
        
        # Call LLM
        response = self.llm.chat(
            messages=messages,
            tier=ModelTier.ADVISOR,
            tools=tools if tools else None,
            temperature=0.7,
        )
        
        # Process tool calls if any
        tool_results = []
        follow_up_needed = False
        
        if response.has_tool_calls:
            for tool_call in response.tool_calls:
                result = self._execute_tool(tool_call.name, tool_call.arguments)
                tool_results.append({
                    "tool": tool_call.name,
                    "arguments": tool_call.arguments,
                    "result": result,
                })
                
                # Check if survey failed - advisor should propose a claim
                if tool_call.name == "survey_area" and not result.get("found", True):
                    follow_up_needed = True
        
        # If survey failed, prompt for follow-up with claim proposal
        if follow_up_needed and response.content:
            follow_up_messages = messages + [
                {"role": "assistant", "content": response.content},
                {"role": "user", "content": "The survey found areas not in our records. As you would in character, propose what you believe exists there based on common knowledge, rumors, or reasonable assumption."}
            ]
            
            follow_up_response = self.llm.chat(
                messages=follow_up_messages,
                tier=ModelTier.ADVISOR,
                tools=tools if tools else None,
                temperature=0.7,
            )
            
            if follow_up_response.has_tool_calls:
                for tool_call in follow_up_response.tool_calls:
                    result = self._execute_tool(tool_call.name, tool_call.arguments)
                    tool_results.append({
                        "tool": tool_call.name,
                        "arguments": tool_call.arguments,
                        "result": result,
                    })
            
            if follow_up_response.content:
                response.content = (response.content or "") + "\n\n" + follow_up_response.content
        
        # Build response
        result = {
            "advisor": self.name,
            "title": self.title,
            "role": self.role,
            "response": response.content,
            "tool_calls": tool_results,
            "model": response.model,
        }
        
        # Update conversation history
        self._conversation_history.append({"role": "user", "content": query})
        if response.content:
            self._conversation_history.append({"role": "assistant", "content": response.content})
        
        return result
    
    def _execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool call."""
        arguments["proposed_by"] = self.role
        
        try:
            # Core tools
            if tool_name == "get_world_state":
                return self.handlers.get_world_state(
                    scope=arguments.get("scope", "full")
                )
            elif tool_name == "propose_claim":
                return self.handlers.propose_claim(
                    claim_type=arguments.get("claim_type"),
                    description=arguments.get("description"),
                    proposed_by=self.role,
                    evidence=arguments.get("evidence"),
                    effects_on_confirm=arguments.get("effects_on_confirm"),
                )
            elif tool_name == "list_open_claims":
                return self.handlers.list_open_claims(
                    status_filter=arguments.get("status_filter", "pending")
                )
            elif tool_name == "resolve_claim":
                return self.handlers.resolve_claim(
                    claim_id=arguments.get("claim_id"),
                    verdict=arguments.get("verdict"),
                    reasoning=arguments.get("reasoning"),
                    resolved_by=self.role,
                )
            elif tool_name == "apply_action":
                return self.handlers.apply_action(
                    action_type=arguments.get("action_type"),
                    description=arguments.get("description"),
                    proposed_by=self.role,
                    target=arguments.get("target"),
                    parameters=arguments.get("parameters"),
                    costs=arguments.get("costs"),
                    effects=arguments.get("effects"),
                    risks=arguments.get("risks"),
                )
            elif tool_name == "log_event":
                return self.handlers.log_event(
                    description=arguments.get("description"),
                    actor=self.role,
                    event_type=arguments.get("event_type", "custom"),
                    effects=arguments.get("effects"),
                )
            elif tool_name == "survey_area":
                return self.handlers.survey_area(
                    area_name=arguments.get("area_name"),
                    survey_type=arguments.get("survey_type", "general"),
                    depth=arguments.get("depth", "standard"),
                )
            
            # State extension tools
            elif tool_name == "extend_state" and self.state_tools:
                return self.state_tools.extend_state(
                    path=arguments.get("path"),
                    value=arguments.get("value"),
                    reason=arguments.get("reason"),
                    proposed_by=self.role,
                )
            elif tool_name == "query_state" and self.state_tools:
                return self.state_tools.query_state(
                    path_pattern=arguments.get("path_pattern"),
                )
            elif tool_name == "delete_extension" and self.state_tools:
                return self.state_tools.delete_extension(
                    path=arguments.get("path"),
                    reason=arguments.get("reason"),
                    proposed_by=self.role,
                )
            elif tool_name == "add_rule" and self.state_tools:
                return self.state_tools.add_rule(
                    trigger=arguments.get("trigger"),
                    effect=arguments.get("effect"),
                    reason=arguments.get("reason"),
                    proposed_by=self.role,
                )
            elif tool_name == "list_rules" and self.state_tools:
                return self.state_tools.list_rules(
                    active_only=arguments.get("active_only", True),
                )
            
            else:
                return {"error": f"Unknown tool: {tool_name}"}
        except Exception as e:
            return {"error": str(e)}
    
    def reset_conversation(self) -> None:
        """Clear conversation history."""
        self._conversation_history.clear()
    
    def get_intro(self) -> str:
        """Get a brief introduction for this advisor."""
        return f"{self.name}, {self.title}"
    
    def get_full_description(self) -> str:
        """Get full description including background and personality."""
        p = self.profile
        lines = [
            f"=== {p.name}, {p.title} ===",
            f"",
            f"{p.description}",
            f"",
            f"Background: {p.background}",
            f"",
            f"Speech: {p.speech_style}",
        ]
        
        if p.personal_goals:
            lines.append(f"\nPersonal Goals:")
            for goal in p.personal_goals:
                lines.append(f"  • {goal}")
        
        if p.faction_sympathies:
            lines.append(f"\nFaction Relationships:")
            for faction, level in p.faction_sympathies.items():
                if level > 30:
                    lines.append(f"  • Sympathetic to {faction}")
                elif level < -30:
                    lines.append(f"  • Hostile to {faction}")
        
        lines.append(f"\nLoyalty: {p.loyalty}  |  Stress: {p.stress}  |  Reputation: {p.reputation}")
        
        return "\n".join(lines)


# Keep old class names as aliases for backwards compatibility during transition
BaseAdvisor = DynamicAdvisor
