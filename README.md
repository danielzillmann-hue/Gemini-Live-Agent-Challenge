# Genesis — AI Game Master

A cinematic, multiplayer tabletop RPG powered by Gemini. Every scene illustrated. Every NPC voiced. Every choice matters.

**Live Demo:** https://genesis-frontend-241457909657.us-central1.run.app
**Backend API:** https://genesis-backend-241457909657.us-central1.run.app

---

## What It Does

Genesis replaces the human Game Master with an AI that narrates stories, generates scene illustrations, voices NPCs, runs combat, and tracks a living world — all in real-time, for multiple players across different locations.

Players create characters, join a shared session, and the AI weaves an interactive fantasy story with:
- **Narrated text** flowing naturally with **AI-generated scene images** (Gemini native interleaved output)
- **Distinct NPC voices** — each character sounds different (9 Cloud TTS voice profiles)
- **Procedural ambient music** that shifts with the mood (Web Audio API)
- **Real-time multiplayer** with action windows, voice chat (WebRTC), and text chat
- **Persistent world** — NPCs remember you, factions track reputation, choices have consequences

## Competition Category

**Creative Storyteller** — Multimodal Storytelling with Interleaved Output

Genesis uses Gemini's `response_modalities=["TEXT", "IMAGE"]` to generate narration and illustrations in a single API call. The AI thinks like a creative director — weaving text, images, audio, and video into one cohesive experience.

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| **AI Brain** | Gemini 2.5 Pro via Google ADK (6-agent orchestrator) |
| **Interleaved Output** | Gemini native `response_modalities=["TEXT", "IMAGE"]` |
| **Image Generation** | Imagen 3 via Vertex AI |
| **Video Generation** | Veo 2 via Vertex AI |
| **Text-to-Speech** | Google Cloud TTS (Studio voices) |
| **Backend** | FastAPI + WebSocket on Cloud Run |
| **Frontend** | Next.js 15 + TypeScript + Tailwind CSS |
| **State Persistence** | Cloud Firestore |
| **Media Storage** | Cloud Storage |
| **CI/CD** | Cloud Build (auto-deploy on push) |
| **Voice Chat** | WebRTC (peer-to-peer) |
| **Infrastructure** | Automated setup via shell scripts |

### Google Cloud Services Used
- **Cloud Run** — Backend + Frontend hosting
- **Vertex AI** — Gemini 2.5 Pro, Imagen 3, Veo 2
- **Cloud Firestore** — Game state persistence
- **Cloud Storage** — Generated media assets
- **Cloud Build** — CI/CD pipeline
- **Cloud Text-to-Speech** — NPC voice acting
- **Artifact Registry** — Docker image storage

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      PLAYERS (Browsers)                      │
│  Next.js Frontend │ WebSocket │ WebRTC Voice │ Cloud TTS     │
└──────────┬──────────────┬───────────┬───────────────────────┘
           │              │           │
           ▼              ▼           │ (peer-to-peer)
┌─────────────────────────────────────┐
│         Cloud Run — Backend         │
│                                     │
│  FastAPI + WebSocket Server         │
│  ┌───────────────────────────────┐  │
│  │     ADK Agent Orchestrator    │  │
│  │  ┌─────────┐ ┌─────────────┐ │  │
│  │  │Narrator │ │ Rules Agent │ │  │
│  │  │ Agent   │ │ (combat/    │ │  │
│  │  │         │ │  dice/XP)   │ │  │
│  │  ├─────────┤ ├─────────────┤ │  │
│  │  │Art Dir. │ │World Keeper │ │  │
│  │  │ Agent   │ │ (NPCs/lore/ │ │  │
│  │  │         │ │  factions)  │ │  │
│  │  └─────────┘ └─────────────┘ │  │
│  └───────────────────────────────┘  │
│                                     │
│  Action Window │ Turn Manager       │
│  Tool Handlers │ Game Engine        │
└──────┬──────┬──────┬──────┬────────┘
       │      │      │      │
       ▼      ▼      ▼      ▼
   Gemini  Imagen  Cloud   Cloud
   2.5 Pro   3     TTS   Firestore
   (Vertex) (Vertex)      Storage
```

---

## Features

### Core Gameplay
- 🎭 **AI Game Master** — 6-agent ADK orchestrator (Narrator, Rules, Art Director, World Keeper)
- ⚔️ **D&D-Style Combat** — Initiative-based turns, attack rolls, damage, conditions
- 📜 **Quest System** — Create, progress, complete with XP/gold rewards
- 🎲 **Dice Mechanics** — d20 checks with advantage/disadvantage, critical hits
- 📈 **Character Progression** — D&D 5e XP thresholds, level-up with HP gains

### Multimodal Output
- 🖼️ **Native Interleaved** — Gemini generates text + images in one API call
- 🎨 **Scene Illustrations** — AI-generated art for every major scene transition
- 🗣️ **Multi-Voice NPC TTS** — 9 distinct Cloud TTS voices (gruff dwarf ≠ noble elf)
- 🎵 **Procedural Music** — Ambient soundscapes that shift with mood (Web Audio API)
- 🎬 **Video Cutscenes** — Veo 2 cinematics for dramatic moments

### Living World
- 🧠 **NPC Memory** — NPCs remember every interaction with sentiment tracking
- ⚖️ **Faction Reputation** — Political dynamics that affect quests and NPC behavior
- 🌊 **Consequence Engine** — Player choices ripple through the world
- 📚 **Lorebook** — Keyword-triggered world knowledge injection
- 🌦️ **Weather Effects** — Mechanical combat impacts (rain: -1 ranged, storm: -3)
- 🏆 **Achievements** — 10 auto-tracked milestones (First Blood, Veteran, etc.)

### Multiplayer
- 👥 **Remote Multiplayer** — Players join from different locations via session code
- 🎙️ **Voice Chat** — WebRTC peer-to-peer audio
- 💬 **Text Chat** — Party communication separate from game actions
- ⏱️ **Action Windows** — D&D-style: everyone declares, AI narrates together
- 🗡️ **Initiative Combat** — Strict turn order during combat

### Production Quality
- 💾 **Auto-Save** — Firestore persistence every 5 events
- 📖 **Session Recap** — "Previously on..." with interleaved text + image
- 🔒 **Input Validation** — Pydantic field constraints on all inputs
- 🔄 **CI/CD** — Cloud Build auto-deploys on push to main
- 🧪 **70 Tests** — Unit, integration, WebSocket, handler, and turn system tests

---

## Spin-Up Instructions

### Prerequisites
- Google Cloud account with billing enabled
- `gcloud` CLI installed and authenticated
- Node.js 22+ and Python 3.12+

### One-Command Cloud Deployment

```bash
# Clone the repository
git clone https://github.com/danielzillmann-hue/Gemini-Live-Agent-Challenge.git
cd Gemini-Live-Agent-Challenge

# Set your project ID
export PROJECT_ID=your-gcp-project-id

# Run the automated setup (provisions everything)
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
pip install -r requirements.txt
pytest -v  # 70 tests, ~1.5 seconds
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
│   ├── main.py                 # Routes, WebSocket, wiring (422 lines)
│   ├── agents/
│   │   ├── orchestrator.py     # ADK agent definitions + runner
│   │   ├── tools.py            # 17 tool functions
│   │   ├── prompts.py          # System instructions
│   │   └── tool_handlers.py    # Handler registry (one per tool)
│   ├── handlers/
│   │   ├── turns.py            # ActionWindow multiplayer system
│   │   └── actions.py          # Action processing pipeline
│   ├── game/
│   │   ├── engine.py           # Game state, combat, leveling
│   │   └── models.py           # Pydantic data models
│   ├── services/
│   │   ├── gemini_service.py   # Gemini API + interleaved output
│   │   ├── media_service.py    # Imagen 3 + Veo 2
│   │   ├── storage_service.py  # Cloud Storage
│   │   └── firestore_service.py # Firestore persistence
│   └── tests/                  # 70 tests across 5 layers
├── frontend/                   # Next.js 15 + TypeScript
│   ├── app/                    # Pages (landing, game)
│   ├── components/             # 12 UI components
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

## Findings & Learnings

### What Worked
- **ADK multi-agent architecture** — separating narration, rules, art, and world management into specialized agents produced dramatically better output than a single prompt
- **Action windows for multiplayer** — batching player actions into one AI call solved the concurrent-input chaos problem elegantly
- **Graceful fallback chains** — native interleaved → Imagen → text-only ensures the game never breaks even when individual services fail
- **NPC memory with sentiment** — simple `event + sentiment` tuples create surprisingly believable NPC behavior

### Challenges
- **ADK session management** — `InMemorySessionService` requires explicit session creation before `run_async` — not documented clearly
- **Vertex AI model names** — different from the Gemini API names (`imagen-3.0-generate-002` not `imagen-4`)
- **Cloud Run + WebSockets** — requires `--session-affinity` for multiplayer to work (same instance routing)
- **CORS with credentials** — `allow_credentials=True` is incompatible with `allow_origins=["*"]` in FastAPI

### What We'd Do Differently
- Use a vector database for NPC memory at scale (current list-based approach works but doesn't scale past ~100 memories per NPC)
- Implement true fog-of-war with interactive dungeon maps
- Add Gemini Live API for real-time voice conversation with NPCs
