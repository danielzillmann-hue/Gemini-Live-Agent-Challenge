# Genesis — AI Game Master

A cinematic, multiplayer tabletop RPG powered by Gemini. Every scene illustrated. Every NPC voiced. Every choice matters.

**Live Demo:** https://genesis-frontend-241457909657.us-central1.run.app
**Backend API:** https://genesis-backend-241457909657.us-central1.run.app
**Presentation:** https://gamma.app/docs/mlkacf9hsg9s6p3

---

## What It Does

Genesis replaces the human Game Master with an AI that narrates stories, generates scene illustrations, voices NPCs, runs combat, and tracks a living world — all in real-time, for multiple players across different locations.

- **Narrated text** with **AI-generated scene images** (Gemini native interleaved output)
- **Real-time NPC voice conversations** via Gemini Live API
- **9 distinct NPC voices** via Cloud TTS Neural2
- **Real dice rolls** — d20 + ability modifiers vs difficulty class
- **Procedural ambient music** that shifts with mood
- **Multiplayer** with D&D-style action windows, WebRTC voice chat, text chat
- **Persistent world** — NPCs remember you, factions track reputation, choices create consequences
- **Character persistence** — save and continue across campaigns

## Competition Category

**Creative Storyteller** — Multimodal Storytelling with Interleaved Output

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| AI Brain | Gemini 2.5 Flash/Pro via Google ADK (6-agent orchestrator) |
| Live Voice | Gemini Live API (gemini-live-2.5-flash-native-audio) |
| Interleaved Output | Gemini native response_modalities=["TEXT", "IMAGE"] |
| Image Generation | Imagen 3 via Vertex AI |
| Video Generation | Veo 2 via Vertex AI |
| Text-to-Speech | Google Cloud TTS (9 Neural2 voice profiles) |
| Grounding | Google Search grounding |
| Backend | FastAPI + WebSocket on Cloud Run |
| Frontend | Next.js 15 + TypeScript + Tailwind CSS |
| Persistence | Cloud Firestore + Cloud Storage |
| CI/CD | Cloud Build (auto-deploy on push) |
| Voice Chat | WebRTC (peer-to-peer) |
| Infrastructure | Automated setup scripts |

### Google Cloud Services

Cloud Run, Vertex AI, Gemini Live API, Cloud Firestore, Cloud Storage, Cloud Build, Cloud Text-to-Speech, Artifact Registry

---

## Architecture

```
Players (Browsers) --- WebSocket + WebRTC + Gemini Live API
         |
    Cloud Run Backend
    |-- ADK Orchestrator (6 agents)
    |   |-- Narrator Agent
    |   |-- Rules Agent (combat/dice/XP)
    |   |-- Art Director Agent
    |   |-- World Keeper Agent (NPCs/lore/factions)
    |-- Action Window + Turn Manager
    |-- Tool Handlers (17 tools)
    |-- Live API Voice Service
    |-- Game Engine
         |
    |-- Gemini 2.5 + Live API
    |-- Imagen 3 + Veo 2
    |-- Cloud TTS Neural2
    |-- Cloud Firestore
    |-- Cloud Storage
```

---

## Features

### See, Hear, Speak

- **See** — Scene illustrations (Gemini interleaved + Imagen 3), battle maps, portraits, world maps with fullscreen viewer
- **Hear** — Cloud TTS narrator + 9 NPC voices, procedural ambient music
- **Speak** — Gemini Live API voice conversations with NPCs, camera dice detection

### Gameplay

- D&D-style combat with initiative, attack rolls, damage
- Real d20 dice rolls affecting every uncertain action
- Quest system with objectives and XP/gold rewards
- Character leveling (D&D 5e XP thresholds)
- AI-generated loot with rarity and lore
- Save/continue campaigns, persistent character roster
- Flash/Pro model toggle in-game

### Living World

- NPC memory with sentiment tracking (visible in journal)
- Faction reputation system (visible in world map panel)
- Consequence engine for ripple effects
- Lorebook with keyword triggering
- Weather effects on combat mechanics

### Multiplayer

- Join via session code or invite link from anywhere
- D&D-style action windows (12s collection, all players declare then AI narrates)
- Initiative-based combat turns
- WebRTC voice chat + text chat between players

### Production Quality

- 84+ automated tests (unit, integration, WebSocket, handler, turn system, E2E campaign)
- 12 focused modules, handler registry pattern, no god objects
- Thread-safe with asyncio.Lock, input validated with Pydantic
- CI/CD auto-deploy, infrastructure as code
- Graceful fallbacks: interleaved to Imagen to text-only, Cloud TTS to browser TTS, Firestore auto-restore

---

## Spin-Up Instructions

### Prerequisites

- Google Cloud account with billing enabled
- gcloud CLI installed and authenticated
- Node.js 22+ and Python 3.12+

### One-Command Cloud Deployment

```bash
git clone https://github.com/danielzillmann-hue/Gemini-Live-Agent-Challenge.git
cd Gemini-Live-Agent-Challenge

export PROJECT_ID=your-gcp-project-id
chmod +x infrastructure/setup.sh
./infrastructure/setup.sh
```

This script automatically:
1. Enables all required Google Cloud APIs
2. Creates Artifact Registry, Cloud Storage bucket, Firestore database
3. Builds and pushes Docker images
4. Deploys backend and frontend to Cloud Run
5. Sets up CI/CD trigger for automatic deployments

### Local Development

```bash
# Backend
cd backend
pip install -r requirements.txt
export GOOGLE_GENAI_USE_VERTEXAI=1
export GOOGLE_CLOUD_PROJECT=your-project-id
uvicorn main:app --reload --port 8080

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

### Running Tests

```bash
cd backend

# Unit tests (70 tests, ~1.5 seconds)
pytest -v

# E2E tests against live backend (13 tests, ~3 minutes)
GENESIS_URL=https://your-backend-url pytest tests/test_e2e_campaign.py -v -s

# Extended playthrough (5 turns, ~5 minutes)
GENESIS_URL=https://your-backend-url pytest tests/test_e2e_long_play.py -v -s
```

### Teardown

```bash
export PROJECT_ID=your-gcp-project-id
./infrastructure/teardown.sh
```

---

## Project Structure

```
Genesis/
├── backend/                    # Python FastAPI + Google ADK
│   ├── main.py                 # Routes, WebSocket, Live API, wiring
│   ├── agents/
│   │   ├── orchestrator.py     # ADK agent definitions + runner
│   │   ├── tools.py            # 17 tool functions
│   │   ├── prompts.py          # System instructions for all agents
│   │   └── tool_handlers.py    # Handler registry (one per tool)
│   ├── handlers/
│   │   ├── turns.py            # ActionWindow multiplayer system
│   │   └── actions.py          # Action processing pipeline
│   ├── game/
│   │   ├── engine.py           # Game state, combat, leveling, context
│   │   └── models.py           # Pydantic data models
│   ├── services/
│   │   ├── gemini_service.py   # Gemini API + interleaved + grounding
│   │   ├── live_api_service.py # Gemini Live API for NPC voice
│   │   ├── media_service.py    # Imagen 3 + Veo 2
│   │   ├── storage_service.py  # Cloud Storage
│   │   └── firestore_service.py # Firestore persistence
│   └── tests/                  # 84+ tests across 6 layers
├── frontend/                   # Next.js 15 + TypeScript
│   ├── app/                    # Pages (landing, game)
│   ├── components/             # 14 UI components
│   ├── hooks/                  # State management + WebSocket
│   └── lib/                    # Types, API client, utils
├── infrastructure/
│   ├── setup.sh                # One-command cloud provisioning
│   └── teardown.sh             # Clean removal
├── cloudbuild.yaml             # CI/CD pipeline
├── docker-compose.yml          # Local development
└── README.md
```

---

## Findings and Learnings

### What Worked

- **ADK multi-agent architecture** — specialized agents produce dramatically better output than a single prompt
- **Action windows for multiplayer** — batching player actions into one AI call solved concurrent-input chaos
- **Aggressive tool prompting** — making tools REQUIRED was key to getting dice rolls and images on every turn
- **NPC memory with sentiment** — simple event + sentiment tuples create surprisingly believable NPC behavior
- **Gemini Live API** — real-time voice conversations create genuine immersion that text alone cannot match

### Challenges

- **ADK intermediate tool calls** — consumed internally by ADK; had to intercept non-final events to capture dice rolls and XP
- **Gemini Live API model naming** — gemini-live-2.5-flash-native-audio (not gemini-2.5-flash-native-audio)
- **PCM audio sample rate** — Gemini Live outputs 24kHz; playing at 16kHz produced garbled audio
- **Cloud Run + WebSockets** — requires session-affinity, keep-alive pings, and 3600s timeout
- **Save/load gap** — had save button but no load UI; Firestore listing needed instead of in-memory

### What We'd Do Differently

- Vector database for NPC memory at scale
- Interactive dungeon maps with fog of war and token movement
- Spectator mode with audience voting on story choices
- Pre-generated audio greetings for common NPC interactions
