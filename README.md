# Delegative Strategy Game

A text-based strategy simulation where you govern through AI advisors who read game state, propose actions, and manage your realm.

## Concept

You are a ruler. You don't manage resources directly—you delegate to advisors who have expertise, biases, and blind spots. Give intent, not mechanics. Your advisors translate your will into structured actions.

**Key Features:**
- **Three Advisors**: Steward (economy), Marshal (security), Chancellor (law/factions)
- **Claim System**: AI can't invent facts freely—new world facts must be proposed and validated
- **Any Scenario**: Describe your setting ("rural England 1000s", "post-coup Africa 1970s") and the game bootstraps from there
- **Two-Tier AI**: Cheap models for daily work, smarter models for conflict resolution

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Copy environment template and add your API key
cp .env.example .env
# Edit .env with your OpenRouter API key

# Run the game
python -m src.main
```

## Commands

| Command | Description |
|---------|-------------|
| `ask <advisor> <question>` | Query a specific advisor |
| `order <text>` | Give high-level directive |
| `claims` | List pending claims |
| `approve <id>` | Confirm a claim |
| `deny <id>` | Reject a claim |
| `advance <days>` | Progress time |
| `status` | View world state |
| `save` / `load` | Persist/restore game |
| `quit` | Exit |

## Architecture

```
Player → REPL → Advisor Models (cheap/frequent)
                      ↓
              Tool Registry → World State
                      ↓
         Orchestrator Model (smart/rare)
              (on escalation only)
```

**State Mutation Rules:**
- Simple changes (queries, logs): Execute directly
- Structural changes (new entities, major shifts): Player approval
- Conflicts/contested claims: Escalate to orchestrator

## Configuration

Set in `.env`:
- `OPENROUTER_API_KEY`: Your OpenRouter API key
- `ADVISOR_MODEL`: Model for day-to-day advisor work (default: `moonshotai/kimi-k2-0905`)
- `ORCHESTRATOR_MODEL`: Model for validation/bootstrap (default: `google/gemini-3-flash-preview`)

## License

MIT
