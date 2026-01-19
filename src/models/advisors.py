"""Advisor profile schemas - dynamically generated advisor personalities."""

from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
import uuid


class AdvisorRole(str, Enum):
    """The functional role an advisor fills."""
    STEWARD = "steward"      # Economy, resources, trade
    MARSHAL = "marshal"      # Military, security, defense
    CHANCELLOR = "chancellor"  # Law, diplomacy, factions


class AdvisorProfile(BaseModel):
    """A dynamically generated advisor with unique personality and stakes."""
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    
    # Identity
    role: AdvisorRole
    name: str
    title: str
    background: str  # Their history and how they came to this position
    
    # Appearance/Voice (for immersion)
    description: str  # Physical description, mannerisms
    speech_style: str  # How they talk - formal, blunt, poetic, etc.
    
    # Personal stakes - what makes them a CHARACTER not a function
    personal_goals: list[str] = Field(default_factory=list)  # What THEY want
    fears: list[str] = Field(default_factory=list)  # What they're afraid of
    secrets: list[str] = Field(default_factory=list)  # Hidden knowledge or shame
    
    # Cognitive profile - how they think
    biases: list[str] = Field(default_factory=list)  # Specific to their history
    blind_spots: list[str] = Field(default_factory=list)  # What they miss
    strengths: list[str] = Field(default_factory=list)  # What they're good at
    
    # Relationships
    faction_sympathies: dict[str, int] = Field(default_factory=dict)  # faction_id -> -100 to 100
    advisor_relationships: dict[str, str] = Field(default_factory=dict)  # advisor_role -> description
    
    # Dynamic state
    loyalty: int = Field(default=70, ge=0, le=100)  # Loyalty to the ruler
    stress: int = Field(default=20, ge=0, le=100)  # Current stress level
    reputation: int = Field(default=50, ge=0, le=100)  # Standing with the people
    
    # For tracking change over time
    recent_successes: list[str] = Field(default_factory=list)
    recent_failures: list[str] = Field(default_factory=list)
    grievances: list[str] = Field(default_factory=list)  # Against the ruler
    
    model_config = {"extra": "allow"}
    
    def get_system_prompt_fragment(self) -> str:
        """Generate the personality portion of the system prompt."""
        
        biases_str = "\n".join(f"- {b}" for b in self.biases) if self.biases else "- None specified"
        blind_spots_str = "\n".join(f"- {b}" for b in self.blind_spots) if self.blind_spots else "- None specified"
        strengths_str = "\n".join(f"- {s}" for s in self.strengths) if self.strengths else "- Competent in your domain"
        goals_str = "\n".join(f"- {g}" for g in self.personal_goals) if self.personal_goals else "- Serve faithfully"
        fears_str = "\n".join(f"- {f}" for f in self.fears) if self.fears else "- Standard concerns"
        
        # Faction relationships
        faction_lines = []
        for faction, sympathy in self.faction_sympathies.items():
            if sympathy > 50:
                faction_lines.append(f"- You are sympathetic to {faction}")
            elif sympathy < -50:
                faction_lines.append(f"- You distrust {faction}")
            elif sympathy < 0:
                faction_lines.append(f"- You are wary of {faction}")
        faction_str = "\n".join(faction_lines) if faction_lines else "- No strong faction alignments"
        
        # Advisor relationships  
        relationship_lines = []
        for other_role, desc in self.advisor_relationships.items():
            relationship_lines.append(f"- {other_role.title()}: {desc}")
        relationship_str = "\n".join(relationship_lines) if relationship_lines else "- Professional relationships with fellow advisors"
        
        # Current state affects behavior
        state_notes = []
        if self.loyalty < 40:
            state_notes.append("You are growing disloyal and may consider your own interests over the ruler's.")
        if self.stress > 70:
            state_notes.append("You are under great stress and may react emotionally or make hasty judgments.")
        if self.grievances:
            state_notes.append(f"You hold grievances: {'; '.join(self.grievances)}")
        state_str = "\n".join(state_notes) if state_notes else ""
        
        prompt = f"""
YOUR IDENTITY:
You are {self.name}, {self.title}.
{self.background}

APPEARANCE & MANNER:
{self.description}

HOW YOU SPEAK:
{self.speech_style}

YOUR PERSONAL GOALS (what you actually want):
{goals_str}

YOUR FEARS:
{fears_str}

YOUR BIASES (shaped by your history):
{biases_str}

YOUR BLIND SPOTS (what you tend to miss):
{blind_spots_str}

YOUR STRENGTHS:
{strengths_str}

FACTION RELATIONSHIPS:
{faction_str}

RELATIONSHIPS WITH OTHER ADVISORS:
{relationship_str}
"""
        
        if state_str:
            prompt += f"\nCURRENT STATE:\n{state_str}\n"
        
        if self.secrets:
            prompt += f"\nSECRETS (things you know but may not share freely):\n"
            for secret in self.secrets:
                prompt += f"- {secret}\n"
        
        return prompt
    
    def adjust_loyalty(self, delta: int, reason: str) -> None:
        """Adjust loyalty and track grievances."""
        old_loyalty = self.loyalty
        self.loyalty = max(0, min(100, self.loyalty + delta))
        
        if delta < -10:
            self.grievances.append(reason)
    
    def record_success(self, description: str) -> None:
        """Record a success, improving reputation."""
        self.recent_successes.append(description)
        self.reputation = min(100, self.reputation + 5)
        self.stress = max(0, self.stress - 10)
    
    def record_failure(self, description: str) -> None:
        """Record a failure, damaging reputation."""
        self.recent_failures.append(description)
        self.reputation = max(0, self.reputation - 5)
        self.stress = min(100, self.stress + 15)
    
    def summary(self) -> str:
        """Brief summary of this advisor."""
        return f"{self.name}, {self.title} (Loyalty: {self.loyalty}, Stress: {self.stress})"


class AdvisorCouncil(BaseModel):
    """The complete set of advisors for a scenario."""
    
    steward: AdvisorProfile
    marshal: AdvisorProfile
    chancellor: AdvisorProfile
    
    # Overall council dynamics
    council_tension: int = Field(default=20, ge=0, le=100)  # Internal conflict level
    recent_disputes: list[str] = Field(default_factory=list)
    
    def get_advisor(self, role: str) -> AdvisorProfile:
        """Get advisor by role name."""
        role_lower = role.lower()
        if role_lower == "steward":
            return self.steward
        elif role_lower == "marshal":
            return self.marshal
        elif role_lower == "chancellor":
            return self.chancellor
        raise ValueError(f"Unknown advisor role: {role}")
    
    def all_advisors(self) -> list[AdvisorProfile]:
        """Get all advisors."""
        return [self.steward, self.marshal, self.chancellor]
    
    def summary(self) -> str:
        """Summary of the council."""
        lines = ["=== Your Council ==="]
        for advisor in self.all_advisors():
            lines.append(f"  {advisor.summary()}")
        if self.council_tension > 50:
            lines.append(f"\n  [Tension among advisors is high]")
        return "\n".join(lines)
