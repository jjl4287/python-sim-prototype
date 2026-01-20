"""Autonomous narrator - unified flow with LLM-based intent classification."""

from __future__ import annotations
from typing import TYPE_CHECKING, Optional, Any
from enum import Enum
import json
import re

if TYPE_CHECKING:
    from src.models.world_state import WorldState
    from src.models.orders import Order, OrderTracker, OrderEffect
    from src.models.advisors import AdvisorCouncil
    from src.advisors.base import DynamicAdvisor
    from src.llm.openrouter import OpenRouterClient


class Intent(str, Enum):
    """Types of player intent."""
    ORDER = "order"           # Commands to do something
    QUESTION = "question"     # Asking for information
    SUMMON = "summon"         # Wanting to talk to someone
    GENERAL = "general"       # Chat, acknowledgment, etc.
    CONFIRMATION = "confirmation"  # Yes/no response


# Keywords for irreversible actions
IRREVERSIBLE_KEYWORDS = [
    "execute", "kill", "murder", "assassinate", "slaughter", "massacre",
    "burn", "raze", "destroy", "annihilate",
    "betray", "break alliance", "declare war",
    "exile permanently", "banish",
    "torture", "enslave",
]


def is_irreversible(text: str) -> bool:
    """Check if an action is irreversible."""
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in IRREVERSIBLE_KEYWORDS)


class AutonomousNarrator:
    """
    Unified narrator - all input flows through here.
    Uses LLM for intent classification instead of brittle regex.
    """
    
    def __init__(
        self,
        llm: "OpenRouterClient",
        world_state: "WorldState",
        advisor_council: "AdvisorCouncil",
        advisors: dict[str, "DynamicAdvisor"],
        order_tracker: "OrderTracker",
    ):
        self.llm = llm
        self.world_state = world_state
        self.advisor_council = advisor_council
        self.advisors = advisors
        self.order_tracker = order_tracker
        
        # Session state
        self._session_events: list[dict] = []
        self._pending_escalation: Optional[dict] = None
        self._conversation_mode: Optional[str] = None
        
        # Build advisor lookup (name -> key, nickname -> key, etc.)
        self._advisor_lookup: dict[str, str] = {}
        for key, adv in advisors.items():
            self._advisor_lookup[key] = key
            self._advisor_lookup[adv.name.lower()] = key
            # First name
            first_name = adv.name.split()[0].lower()
            self._advisor_lookup[first_name] = key
            # Check for nickname in quotes
            if "'" in adv.name or '"' in adv.name:
                # Extract nickname like 'Mack' from "Sheriff Miller 'Mack' Mackenzie"
                nick_match = re.search(r"['\"](\w+)['\"]", adv.name)
                if nick_match:
                    self._advisor_lookup[nick_match.group(1).lower()] = key
    
    @property
    def in_conversation(self) -> bool:
        return self._conversation_mode is not None
    
    @property
    def current_advisor(self) -> Optional["DynamicAdvisor"]:
        if self._conversation_mode:
            return self.advisors.get(self._conversation_mode)
        return None
    
    def _find_advisor_in_text(self, text: str) -> Optional[str]:
        """Find any advisor reference in the text."""
        text_lower = text.lower()
        for name, key in self._advisor_lookup.items():
            if name in text_lower:
                return key
        return None
    
    def _classify_intent_via_llm(self, text: str) -> dict:
        """Use LLM to classify intent - more reliable than regex."""
        from src.llm.openrouter import ModelTier
        
        advisor_list = []
        for key, adv in self.advisors.items():
            advisor_list.append(f"- {key}: {adv.name} ({adv.title})")
        
        prompt = f"""Classify this player input for a strategy game.

PLAYER INPUT: "{text}"

AVAILABLE ADVISORS:
{chr(10).join(advisor_list)}

Respond with JSON only:
{{
    "intent": "ORDER" | "QUESTION" | "SUMMON" | "GENERAL",
    "advisor": "<advisor key or null>",
    "is_multi_order": true/false,
    "summary": "<brief description of what they want>"
}}

INTENT TYPES:
- ORDER: They want something DONE. Action, command, directive. "do X", "get X done", "handle X", "I want X", imperatives.
- QUESTION: They want INFORMATION. "what do you think", "tell me about", "how is", "ask X about".
- SUMMON: They want to TALK to someone. "get X in here", "bring X", "I need to speak with X".
- GENERAL: Acknowledgments, thanks, chit-chat, or unclear.

Be aggressive about classifying as ORDER - if they're giving ANY kind of directive or command, it's an ORDER.
"is_multi_order" is true if they're giving multiple separate orders in one message.

JSON only, no explanation:"""

        response = self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            tier=ModelTier.ADVISOR,
            temperature=0.1,
            max_tokens=150,
        )
        
        try:
            content = response.content or "{}"
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                return json.loads(json_match.group())
        except:
            pass
        
        return {"intent": "GENERAL", "advisor": None, "summary": text[:50]}
    
    def process(self, player_input: str) -> dict[str, Any]:
        """Process player input through unified flow."""
        from src.llm.openrouter import ModelTier
        
        # Handle pending escalation
        if self._pending_escalation:
            return self._handle_escalation_response(player_input)
        
        text_lower = player_input.lower().strip()
        
        # Quick check for leave command
        if self.in_conversation and text_lower in ("leave", "back", "exit", "bye", "goodbye", "done"):
            advisor_name = self.current_advisor.name if self.current_advisor else "advisor"
            self._conversation_mode = None
            return self._response(f"Left conversation with {advisor_name}.", left_conversation=True)
        
        # Quick check for simple confirmations
        if text_lower in ("yes", "y", "no", "n", "do it", "proceed", "confirm", "cancel", "stop", "ok", "okay", "alright", "thanks", "thank you"):
            if self._pending_escalation:
                return self._handle_escalation_response(player_input)
            # Just acknowledgment
            return self._handle_general(player_input)
        
        # Use LLM to classify intent
        classification = self._classify_intent_via_llm(player_input)
        intent = classification.get("intent", "GENERAL").upper()
        advisor_key = classification.get("advisor")
        summary = classification.get("summary", player_input[:50])
        
        # If in conversation, bias toward that advisor
        if self.in_conversation and not advisor_key:
            advisor_key = self._conversation_mode
        
        # Handle by intent
        if intent == "SUMMON":
            return self._handle_summon(advisor_key, player_input)
        
        elif intent == "QUESTION":
            return self._handle_question(player_input, advisor_key)
        
        elif intent == "ORDER":
            if is_irreversible(player_input):
                return self._escalate(player_input, advisor_key)
            return self._handle_order(player_input, advisor_key, summary)
        
        else:
            return self._handle_general(player_input)
    
    def _response(
        self,
        text: str,
        orders_created: list = None,
        needs_confirmation: bool = False,
        advisor_response: bool = False,
        advisor_name: str = None,
        entered_conversation: bool = False,
        left_conversation: bool = False,
    ) -> dict[str, Any]:
        """Build a standard response dict."""
        return {
            "response": text,
            "orders_created": orders_created or [],
            "needs_confirmation": needs_confirmation,
            "advisor_response": advisor_response,
            "advisor_name": advisor_name,
            "entered_conversation": entered_conversation,
            "left_conversation": left_conversation,
        }
    
    def _handle_summon(self, advisor_key: Optional[str], original_text: str) -> dict[str, Any]:
        """Handle summoning an advisor."""
        from src.llm.openrouter import ModelTier
        
        # Try to find advisor if not specified
        if not advisor_key:
            advisor_key = self._find_advisor_in_text(original_text)
        
        if not advisor_key or advisor_key not in self.advisors:
            return self._response("I'm not sure who you want to speak with.")
        
        advisor = self.advisors[advisor_key]
        self._conversation_mode = advisor_key
        
        # Generate atmospheric entrance
        messages = [
            {"role": "system", "content": f"You are a narrator. Briefly describe {advisor.name} ({advisor.title}) entering the room. 2-3 sentences max. Be atmospheric."},
            {"role": "user", "content": f"The ruler has summoned {advisor.name}. Describe them entering."},
        ]
        
        response = self.llm.chat(
            messages=messages,
            tier=ModelTier.ADVISOR,
            temperature=0.8,
            max_tokens=150,
        )
        
        entrance = response.content or f"{advisor.name} enters."
        
        return self._response(
            f"{entrance}\n\n[Now speaking with {advisor.name}]",
            entered_conversation=True,
            advisor_name=advisor.name,
        )
    
    def _handle_question(self, query: str, advisor_key: Optional[str]) -> dict[str, Any]:
        """Handle a question - get advisor's opinion/info."""
        if not advisor_key:
            advisor_key = self._find_advisor_in_text(query)
        if not advisor_key:
            # Default to chancellor for questions
            advisor_key = "chancellor"
        
        advisor = self.advisors.get(advisor_key)
        if not advisor:
            return self._handle_general(query)
        
        # Get advisor response
        result = advisor.process_query(query)
        response = result.get("response", "I have nothing to say on that.")
        
        return self._response(
            response,
            advisor_response=True,
            advisor_name=advisor.name,
        )
    
    def _handle_order(self, order_text: str, advisor_key: Optional[str], summary: str) -> dict[str, Any]:
        """Handle an order - create order with proper details."""
        from src.llm.openrouter import ModelTier
        from src.models.orders import Order, OrderEffect
        
        # Find advisor
        if not advisor_key:
            advisor_key = self._find_advisor_in_text(order_text)
        if not advisor_key:
            # Determine by domain
            advisor_key = self._get_advisor_for_domain(order_text)
        if not advisor_key:
            advisor_key = list(self.advisors.keys())[0]
        
        advisor = self.advisors.get(advisor_key)
        if not advisor:
            advisor = list(self.advisors.values())[0]
            advisor_key = list(self.advisors.keys())[0]
        
        # Generate order details via LLM
        settlements = [s.name for s in self.world_state.settlements]
        factions = [f.name for f in self.world_state.factions]
        
        order_prompt = f"""The ruler orders: "{order_text}"

{advisor.name} ({advisor.title}) must respond.

Generate JSON:
{{
    "order_name": "<concise name for this order, max 40 chars>",
    "duration_days": <1-14>,
    "acknowledgment": "<brief in-character acknowledgment from {advisor.name}, 1-2 sentences, include time estimate>",
    "effects": [
        {{"path": "resources.<field>", "delta": <number>}},
        {{"path": "settlements.<name>.population", "delta": <number>}},
        {{"path": "factions.<name>.disposition", "delta": <number>}}
    ]
}}

Available resources: treasury, food, timber, iron, labor
Settlements: {settlements}
Factions: {factions}

IMPORTANT:
- "acknowledgment" should be BRIEF. Just acknowledge and give time. Do NOT describe completion.
- "order_name" should be a proper name like "Deploy solar panels" not the raw player input
- Include realistic effects. Moving 100 workers = population change. Building = resource costs.

JSON only:"""

        response = self.llm.chat(
            messages=[{"role": "user", "content": order_prompt}],
            tier=ModelTier.ADVISOR,
            temperature=0.5,
            max_tokens=300,
        )
        
        # Parse response
        try:
            content = response.content or "{}"
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                order_data = json.loads(json_match.group())
            else:
                order_data = {}
        except:
            order_data = {}
        
        # Extract with fallbacks
        order_name = order_data.get("order_name", summary[:40])
        duration = order_data.get("duration_days", 3)
        acknowledgment = order_data.get("acknowledgment", f"Understood. {duration} days.")
        effects_data = order_data.get("effects", [])
        
        # Build effects
        effects = []
        for eff in effects_data:
            if isinstance(eff, dict) and "path" in eff:
                effects.append(OrderEffect(
                    path=eff["path"],
                    delta=eff.get("delta"),
                    set_value=eff.get("set_value"),
                ))
        
        # Create order
        order = Order(
            description=order_name,
            original_request=order_text,
            assigned_to=advisor_key,
            advisor_name=advisor.name,
            duration_days=max(1, min(30, duration)),
            effects=effects,
        )
        
        self.order_tracker.add(order)
        
        # Log
        self._session_events.append({
            "type": "order",
            "summary": order_name,
            "advisor": advisor.name,
        })
        
        return self._response(
            acknowledgment,
            orders_created=[order],
            advisor_response=True,
            advisor_name=advisor.name,
        )
    
    def _handle_general(self, query: str) -> dict[str, Any]:
        """Handle general queries through the narrator."""
        from src.llm.openrouter import ModelTier
        
        ctx = self.world_state.advisor_context
        
        messages = [
            {"role": "system", "content": f"""You are the narrator for a strategy game set in {ctx.historical_period}.

Current situation: {self.world_state.scenario_description}

Be brief and atmospheric. If they're just acknowledging something, respond briefly. 
If they seem confused, offer guidance on what they can do (give orders, ask questions, summon advisors)."""},
            {"role": "user", "content": query},
        ]
        
        response = self.llm.chat(
            messages=messages,
            tier=ModelTier.ADVISOR,
            temperature=0.7,
            max_tokens=200,
        )
        
        return self._response(response.content or "...")
    
    def _get_advisor_for_domain(self, text: str) -> Optional[str]:
        """Determine advisor by domain keywords."""
        text_lower = text.lower()
        
        # Economic -> steward
        if any(word in text_lower for word in [
            "gold", "treasury", "money", "food", "resource", "trade", "tax",
            "economy", "production", "harvest", "supplies", "craft", "build",
            "labor", "worker", "solar", "power", "water", "infrastructure",
        ]):
            return "steward"
        
        # Military -> marshal
        if any(word in text_lower for word in [
            "army", "soldier", "warrior", "attack", "defend", "patrol",
            "scout", "raid", "siege", "battle", "war", "military",
            "guard", "protect", "secure", "weapon", "fort", "troops",
            "sheriff", "police", "arrest", "suppress", "kill",
        ]):
            return "marshal"
        
        # Diplomatic -> chancellor
        if any(word in text_lower for word in [
            "treaty", "alliance", "diplomat", "negotiate", "faction",
            "law", "decree", "ethics", "tradition", "marriage",
            "court", "noble", "title", "claim", "dispute",
        ]):
            return "chancellor"
        
        return None
    
    def _escalate(self, action: str, advisor_key: Optional[str]) -> dict[str, Any]:
        """Escalate an irreversible action for confirmation."""
        from src.llm.openrouter import ModelTier
        
        messages = [
            {"role": "system", "content": "You are a narrator. The player is about to do something irreversible. Describe the consequences briefly (2-3 sentences) and ask for confirmation."},
            {"role": "user", "content": f"The ruler wants to: {action}"},
        ]
        
        response = self.llm.chat(
            messages=messages,
            tier=ModelTier.ADVISOR,
            temperature=0.5,
            max_tokens=150,
        )
        
        self._pending_escalation = {
            "action": action,
            "advisor_key": advisor_key,
        }
        
        return self._response(
            response.content + "\n\n[Proceed? yes/no]",
            needs_confirmation=True,
        )
    
    def _handle_escalation_response(self, response: str) -> dict[str, Any]:
        """Handle response to escalation."""
        pending = self._pending_escalation
        self._pending_escalation = None
        
        if response.lower().strip() in ("yes", "y", "do it", "proceed", "confirm"):
            return self._handle_order(pending["action"], pending.get("advisor_key"), pending["action"][:40])
        else:
            return self._response("The order is stayed.")
    
    def apply_order_effects(self, order: "Order") -> list[str]:
        """Apply order effects to world state."""
        applied = []
        
        for effect in order.effects:
            path_parts = effect.path.split(".")
            if len(path_parts) < 2:
                continue
            
            try:
                category = path_parts[0]
                
                if category == "resources" and len(path_parts) >= 2:
                    field = path_parts[1]
                    if hasattr(self.world_state.resources, field):
                        if effect.delta is not None:
                            current = getattr(self.world_state.resources, field)
                            new_val = max(0, current + effect.delta)
                            setattr(self.world_state.resources, field, new_val)
                            applied.append(f"{field}: {'+' if effect.delta >= 0 else ''}{effect.delta} (now {new_val})")
                
                elif category == "settlements" and len(path_parts) >= 3:
                    name = path_parts[1]
                    field = path_parts[2]
                    settlement = self.world_state.get_settlement(name)
                    if settlement and hasattr(settlement, field):
                        if effect.delta is not None:
                            current = getattr(settlement, field, 0)
                            new_val = max(0, current + effect.delta)
                            setattr(settlement, field, new_val)
                            applied.append(f"{name}.{field}: {'+' if effect.delta >= 0 else ''}{effect.delta} (now {new_val})")
                
                elif category == "factions" and len(path_parts) >= 3:
                    name = path_parts[1]
                    field = path_parts[2]
                    faction = self.world_state.get_faction(name)
                    if faction and hasattr(faction, field):
                        if effect.delta is not None:
                            current = getattr(faction, field, 0)
                            new_val = current + effect.delta
                            if field == "disposition":
                                new_val = max(0, min(100, new_val))
                            setattr(faction, field, new_val)
                            applied.append(f"{name}.{field}: {'+' if effect.delta >= 0 else ''}{effect.delta} (now {new_val})")
            
            except Exception as e:
                applied.append(f"(failed: {effect.path})")
        
        return applied
    
    def complete_order(self, order: "Order") -> str:
        """Complete an order: apply effects FIRST, then generate narrative."""
        from src.llm.openrouter import ModelTier
        
        # Apply effects
        effects_applied = self.apply_order_effects(order)
        effects_summary = "\n".join(f"- {e}" for e in effects_applied) if effects_applied else "No mechanical effects."
        
        # Generate completion narrative
        messages = [
            {"role": "system", "content": "You are a narrator. An order has completed. Describe the outcome in 2-3 sentences. Be specific about results."},
            {"role": "user", "content": f"""Order completed: {order.description}
Original request: {order.original_request or order.description}
Advisor: {order.advisor_name}
Duration: {order.duration_days} days

Effects applied:
{effects_summary}

Describe what happened."""},
        ]
        
        response = self.llm.chat(
            messages=messages,
            tier=ModelTier.ADVISOR,
            temperature=0.7,
            max_tokens=150,
        )
        
        outcome = response.content or "The task was completed."
        order.complete(outcome)
        
        self._session_events.append({
            "type": "order_complete",
            "summary": order.description,
            "effects": effects_applied,
        })
        
        return outcome
