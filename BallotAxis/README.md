# BallotAxis 🗳️🇮🇳
### From Awareness to Action.

India's AI-powered election education platform built with Google Gemini.

## Vertical
Civic Education — Indian Elections

## Architecture
User Browser
|
v
[static/index.html] ←── FastAPI serves at GET /
|
v
FastAPI Backend (main.py)
|
├── POST /chat ──────→ Google Gemini API
├── GET /timeline
├── GET /checklist
├── GET /quiz/question
├── GET /facts
└── GET /health
## Features
- AI Chat powered by Google Gemini with Hindi support
- Interactive Election Timeline
- 10-step Voter Readiness Checklist
- 30-question Civic Knowledge Quiz
- EVM Educational Simulator
- Election Myth Debunker
- Official Resource Directory

## Setup Local
1. Clone repository
2. Create .env file with GEMINI_API_KEY=your_key
3. pip install -r requirements.txt
4. uvicorn main:app --reload --port 8080
5. Open http://localhost:8080

## Get Gemini API Key
Visit https://aistudio.google.com and create a free API key

## Deploy to Cloud Run (Mumbai Region)
gcloud builds submit --tag gcr.io/PROJECT_ID/ballotaxis
gcloud run deploy ballotaxis --image gcr.io/PROJECT_ID/ballotaxis --platform managed --region asia-south1 --allow-unauthenticated --set-env-vars GEMINI_API_KEY=your_key_here --port 8080

## Non-Partisan Pledge
BallotAxis does not endorse any political party or candidate. All information is factual educational and neutral.

## Assumptions
- Users have basic smartphone or computer access
- Gemini API key is provided as environment variable
- App targets Indian citizens aged 18 and above
- English is primary language with Hindi as secondary option
