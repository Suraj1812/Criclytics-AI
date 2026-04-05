# Criclytics AI

Criclytics AI is a production-ready cricket match intelligence platform that turns structured live match data into short, human-like insights without calling any external AI APIs. The system uses validated cricket logic, a signal engine, versioned prompts, and a seeded internal text generator to create deterministic, context-aware commentary.

## Full Folder Structure

```text
.
├── .env.example
├── README.md
├── docker-compose.yml
├── backend
│   ├── Dockerfile
│   ├── __init__.py
│   ├── main.py
│   ├── models
│   │   ├── __init__.py
│   │   └── schemas.py
│   ├── prompts
│   │   ├── __init__.py
│   │   ├── insight_v1.py
│   │   └── insight_v2.py
│   ├── requirements.txt
│   ├── routes
│   │   ├── __init__.py
│   │   ├── analyze.py
│   │   └── health.py
│   ├── services
│   │   ├── __init__.py
│   │   ├── analysis_service.py
│   │   ├── cache_service.py
│   │   ├── cricket_logic.py
│   │   ├── fallback_service.py
│   │   ├── predictor_engine.py
│   │   ├── prompt_engine.py
│   │   ├── rate_limiter.py
│   │   ├── scoring_engine.py
│   │   ├── signal_engine.py
│   │   ├── text_engine.py
│   │   └── trend_engine.py
│   └── utils
│       ├── __init__.py
│       ├── config.py
│       ├── errors.py
│       ├── logging.py
│       └── monitoring.py
└── frontend
    ├── app.js
    ├── index.html
    ├── logo.svg
    ├── robots.txt
    └── site.webmanifest
```

## Architecture

The application is split into clean, production-friendly layers:

- API layer: FastAPI routes expose `POST /analyze` and `GET /health`, validate payloads, add request tracing, and enforce rate limiting.
- Cricket Logic Engine: converts raw score inputs into derived metrics such as current run rate, balls remaining, wickets in hand, phase, and chase context.
- Signal Processing Layer: maps the derived metrics into normalized `pressure`, `momentum`, `stability`, `control`, `volatility`, wicket-risk, and acceleration signals.
- Predictor Engine: produces heuristic `win_probability`, `collapse_probability`, and a next-two-overs scoring projection with no external model calls.
- Trend Engine: tracks the recent request window per client to detect run-rate drift, wicket pressure, and momentum shifts over time.
- Scoring Engine: fuses signals, predictions, and trend context into a unified `match_intelligence_score` and final confidence score.
- Prompt Engine: injects structured context into versioned templates with tone controls for `neutral`, `excited`, and `analytical` output.
- Text Generation Engine: a fully internal, seeded, rule-based generator that uses weighted phrase banks and condition trees to synthesize two-line insights.
- Cache Layer: Redis caches repeated inputs and gracefully degrades to in-memory storage if Redis is unavailable.
- Rate Limiter: uses Redis when available and falls back to local memory for bounded protection in development.
- Monitoring + Logging: request-scoped logging plus event and metric hooks provide monitoring integration points.
- Unified Local Runtime: FastAPI serves the dashboard and API together, so the full product runs from one local command.

## How The Internal Engine Works

No external model is used. Insight generation follows this sequence:

1. Validate and normalize the request with Pydantic.
2. Compute cricket context from the live match state.
3. Derive normalized match signals from that context.
4. Generate predictive outputs and recent trend state.
5. Fuse everything into a unified match intelligence score.
6. Build a structured prompt envelope using the selected prompt version and tone.
7. Run the internal text engine:
   - seeded randomness for deterministic variation
   - weighted phrase selection
   - template mixing
   - signal-aware tactical phrasing
   - prediction-aware and trend-aware sentence fusion
8. If the text engine throws unexpectedly, return a simpler fallback insight.

This gives you AI-like variation and readability while remaining completely self-contained and non-hallucinatory.

## Backend API

### `POST /analyze`

Example request:

```json
{
  "runs": 118,
  "wickets": 3,
  "overs": "13.2",
  "required_rate": 8.9,
  "tone": "analytical",
  "seed": 7
}
```

Example response:

```json
{
  "insight": "From a control view, this middle stretch is tightening against the batting side; 118/3 after 13.2.\nThe next overs can unlock acceleration without forcing the equation. Win probability is leaning their way if this passage stays clean.",
  "source": "engine",
  "cached": false,
  "prompt_version": "insight-v2",
  "tone": "analytical",
  "confidence": 0.73,
  "win_probability": 0.64,
  "collapse_probability": 0.46,
  "match_intelligence_score": 0.59,
  "trend": {
    "trend": "stable",
    "momentum_shift": false
  },
  "signals": {
    "pressure": "medium",
    "momentum": "neutral",
    "stability": "stable",
    "control_score": 0.55,
    "volatility_score": 0.41,
    "confidence_score": 0.73
  },
  "metrics": {
    "current_run_rate": 8.85,
    "required_rate": 8.9,
    "wickets_in_hand": 7,
    "phase": "middle",
    "overs_completed": "13.2",
    "balls_remaining": 40,
    "chase_context": "tracking the asking rate"
  }
}
```

### `GET /health`

Returns cache status, active prompt version, environment, and text engine readiness.

## Setup Instructions

### Local Development

1. Start the full app with the launcher:

```bash
./run
```

The launcher automatically:

- creates `.env` from `.env.example` if missing
- creates `.venv` if missing
- installs dependencies only when `backend/requirements.txt` changes
- runs a backend smoke check before startup
- warns clearly if port `8000` is already in use
- starts the integrated FastAPI app that serves both UI and API

Redis is optional in local development. The default configuration uses the in-memory cache backend, so Docker is not required to get the product running end to end.

If you only want setup and validation without starting the server:

```bash
./run --check
```

If you want to change the port:

```bash
PORT=8010 ./run
```

### Optional Redis

If you want shared caching and Redis-backed rate limiting locally:

```bash
docker compose up -d redis
```

Then set `CACHE_BACKEND=redis` in `.env` and restart the app.

### Docker

To run the API and Redis together:

```bash
cp .env.example .env
docker compose up --build
```

The API runs at [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Production Notes

- Inputs are validated with cricket-specific overs notation rules.
- Response generation is deterministic for identical inputs and seeds.
- Prompt versions let you roll out new wording safely.
- The cache key includes prompt version and request content so output stays consistent.
- Redis is optional in local development because the app degrades gracefully.
- Rate limiting protects the expensive text synthesis path from abuse.

## Scaling Strategy

To scale the platform further:

- Move Redis to a managed cluster for shared caching and rate limiting across multiple API instances.
- Add a background ingestion pipeline for live match feeds and event-level state updates.
- Persist analyzed snapshots and insight histories to Postgres for timelines and replay features.
- Push metric hooks into Prometheus, OpenTelemetry, or DataDog.
- Add load tests around `/analyze` to tune cache hit rate and P95 latency.
- Introduce more signal dimensions such as wickets in last five balls, boundary drought, and recent over trend.
- Expand the text engine with more prompt versions, phrase banks, and match-format-specific logic for ODI and Test cricket.
