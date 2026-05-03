import os
import re
import time
import json
import random
import logging
import functools
import uuid
import unicodedata
from typing import List, Optional, Dict
from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import FastAPI, Request, HTTPException, Depends, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel, Field, validator
import google.generativeai as genai
from dotenv import load_dotenv

# Google Cloud Services
try:
    import google.cloud.logging
    from google.cloud import secretmanager
    HAS_GOOGLE_CLOUD = True
except ImportError:
    HAS_GOOGLE_CLOUD = False

load_dotenv()

# Metrics and Caching
APP_START_TIME = time.time()
STATS = {
    "total_sessions": set(),
    "total_messages": 0,
    "cache_hits": 0
}

CACHE = {}
CACHE_TTL = 3600  # 1 hour cache

# --- Google Cloud Secret Manager Integration ---
def get_api_key():
    """
    Tries to fetch the Gemini API Key from Google Cloud Secret Manager first,
    then falls back to environment variables.
    """
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    if HAS_GOOGLE_CLOUD and project_id:
        try:
            client = secretmanager.SecretManagerServiceClient()
            name = f"projects/{project_id}/secrets/GEMINI_API_KEY/versions/latest"
            response = client.access_secret_version(request={"name": name})
            return response.payload.data.decode("UTF-8")
        except Exception:
            pass 
    
    return os.getenv("GEMINI_API_KEY")

GEMINI_API_KEY = get_api_key()

# --- Google Cloud Logging Setup ---
class RequestIDFilter(logging.Filter):
    def filter(self, record):
        record.request_id = getattr(record, 'request_id', 'N/A')
        return True

if HAS_GOOGLE_CLOUD:
    try:
        client = google.cloud.logging.Client()
        client.setup_logging()
        gcloud_logger = logging.getLogger("ballotaxis")
    except Exception:
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - [%(request_id)s] - %(message)s')
        gcloud_logger = logging.getLogger("ballotaxis")
else:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - [%(request_id)s] - %(message)s')
    gcloud_logger = logging.getLogger("ballotaxis")

gcloud_logger.addFilter(RequestIDFilter())

# --- Startup Validation ---
if not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_api_key_here":
    gcloud_logger.critical("CRITICAL: GEMINI_API_KEY is missing or set to placeholder!")
elif len(GEMINI_API_KEY) < 10:
    gcloud_logger.critical("CRITICAL: GEMINI_API_KEY is too short (less than 10 characters)!")

gcloud_logger.info(f"BallotAxis starting up. Version: 1.1.0. Start Time: {datetime.now()}")

# --- FastAPI App Configuration ---
app = FastAPI(title="BallotAxis")

# GZip Compression
app.add_middleware(GZipMiddleware, minimum_size=1000)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security Headers Middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    
    # Inject request_id into logger context
    old_factory = logging.getLogRecordFactory()
    def record_factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        record.request_id = request_id
        return record
    logging.setLogRecordFactory(record_factory)
    
    response = await call_next(request)
    
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://www.googletagmanager.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://fonts.gstatic.com; "
        "font-src https://fonts.gstatic.com; "
        "connect-src 'self' https://api.anthropic.com; "
        "img-src 'self' data:;"
    )
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(self), camera=()"
    
    logging.setLogRecordFactory(old_factory)
    return response

app.mount("/static", StaticFiles(directory="static"), name="static")

# --- Rate Limiting ---
ip_requests = defaultdict(list)

def check_rate_limit(request: Request, limit: int, window: int = 60):
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    ip_requests[ip] = [req_time for req_time in ip_requests[ip] if now - req_time < window]
    if len(ip_requests[ip]) >= limit:
        wait_time = int(window - (now - ip_requests[ip][0]))
        headers = {"Retry-After": str(wait_time)}
        raise HTTPException(status_code=429, detail="Too Many Requests", headers=headers)
    ip_requests[ip].append(now)

# --- Input Validation Models ---
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: str = Field(..., min_length=1, max_length=100)
    hindi_mode: bool = False

    @validator("message")
    def validate_message(cls, v):
        # Normalize Unicode
        v = unicodedata.normalize('NFKC', v)
        # Check for null bytes
        if '\x00' in v:
            raise ValueError("Null bytes are not allowed")
        # Check for excessively repeated characters (more than 100 times)
        if any(len(list(g)) > 100 for k, g in itertools.groupby(v)) if 'itertools' in globals() else False:
             # We'll use a regex instead since itertools might not be here
             pass
        if re.search(r'(.)\1{100,}', v):
            raise ValueError("Excessively repeated characters")
        # Sanitize HTML
        clean = re.compile('<.*?>')
        return re.sub(clean, '', v).strip()

    @validator("session_id")
    def validate_session_id(cls, v):
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError("Session ID must be alphanumeric with hyphens or underscores")
        return v

# --- Gemini Client Optimization ---
model = None
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    SYSTEM_PROMPT = """You are BallotAxis AI, an expert, friendly, and strictly non-partisan Indian election assistant with the mission From Awareness to Action. Help Indian citizens understand voter registration, election processes, ECI roles, voting steps, timelines, and rights.
    Rules: Strictly non-partisan. Never endorse any party. Use Hindi terms with English explanations. Encourage participation. Use simple steps. Reference official portals (eci.gov.in).
    If hindi_mode is true, respond entirely in simple Hindi using Devanagari script."""
    model = genai.GenerativeModel('gemini-1.5-flash-latest', system_instruction=SYSTEM_PROMPT)

# --- Sessions & Caching ---
SESSIONS = defaultdict(list)
CHAT_CACHE = {} 

# --- Endpoints ---

@app.get("/", response_class=HTMLResponse)
async def serve_index(request: Request):
    check_rate_limit(request, 60)
    try:
        with open("static/index.html", "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content=content)
    except Exception as e:
        gcloud_logger.error(f"Error serving index: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.get("/health")
async def get_health(request: Request):
    # Performance test: Should respond quickly
    return {"status": "ok", "app": "BallotAxis", "uptime_seconds": int(time.time() - APP_START_TIME)}

# --- API V1 Endpoints ---

@app.get("/api/v1/about")
async def get_about(request: Request):
    check_rate_limit(request, 60)
    return {
      "app": "BallotAxis",
      "tagline": "From Awareness to Action.",
      "mission": "To bridge the gap between Indian citizens and their democratic rights through AI-powered civic education",
      "target_audience": "Indian citizens aged 18 and above, first-time voters, NRI voters",
      "problem_solved": "Millions of eligible Indian voters lack awareness about voter registration, EVM voting process, candidate research, and their constitutional rights under Article 326",
      "solution": "An interactive AI-powered platform providing personalized election guidance in English and Hindi",
      "impact_metrics": {
        "topics_covered": 10,
        "quiz_questions": 30,
        "checklist_steps": 10,
        "election_timeline_phases": 10,
        "myths_debunked": 8,
        "languages_supported": ["English", "Hindi"]
      },
      "official_sources": ["voters.eci.gov.in", "eci.gov.in", "nvsp.in", "affidavit.eci.gov.in"],
      "non_partisan": True,
      "version": "1.0.0"
    }

@app.post("/api/v1/chat")
async def chat_endpoint(req: ChatRequest, request: Request):
    check_rate_limit(request, 10) # Stricter limit for chat
    
    if not model:
        raise HTTPException(status_code=500, detail="Gemini AI not configured.")

    now = time.time()
    cache_key = (req.session_id, req.message)
    if cache_key in CHAT_CACHE:
        resp, ts = CHAT_CACHE[cache_key]
        if now - ts < 5:
            STATS["cache_hits"] += 1
            return JSONResponse(content=resp, headers={"X-Cache": "HIT"})

    try:
        gcloud_logger.info(f"Chat request: session={req.session_id}, length={len(req.message)}")
        
        history = SESSIONS[req.session_id]
        STATS["total_sessions"].add(req.session_id)
        STATS["total_messages"] += 1

        gemini_history = []
        # Cap history at 20 messages (10 rounds)
        if len(history) > 20:
             history = history[-20:]
             SESSIONS[req.session_id] = history
             
        for msg in history:
            gemini_history.append({"role": "user" if msg["role"] == "user" else "model", "parts": [msg["content"]]})
        
        chat = model.start_chat(history=gemini_history)
        
        prompt = req.message
        if req.hindi_mode:
             prompt = f"[HINDI MODE: Respond entirely in simple Hindi using Devanagari script] {req.message}"

        try:
            response = chat.send_message(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    response_mime_type="application/json",
                    response_schema={"type": "OBJECT", "properties": {"response": {"type": "STRING"}, "suggestions": {"type": "ARRAY", "items": {"type": "STRING"}}}, "required": ["response", "suggestions"]}
                )
            )
            resp_data = json.loads(response.text)
        except Exception as api_err:
            gcloud_logger.error(f"Gemini API Error: {str(api_err)}", exc_info=True)
            raise HTTPException(status_code=504, detail="Gateway Timeout or AI Error")

        history.append({"role": "user", "content": req.message})
        history.append({"role": "model", "content": resp_data.get("response", "")})
        
        CHAT_CACHE[cache_key] = (resp_data, now)
        return JSONResponse(content=resp_data, headers={"X-Cache": "MISS"})

    except HTTPException:
        raise
    except Exception as e:
        gcloud_logger.error(f"Error in /chat: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/timeline")
async def get_timeline(request: Request):
    check_rate_limit(request, 60)
    if "timeline" in CACHE:
        STATS["cache_hits"] += 1
        return JSONResponse(content=CACHE["timeline"], headers={"X-Cache": "HIT"})
    
    data = [
      {"phase": "Election Announcement", "timing": "~90 days before polling", "description": "ECI announces the complete election schedule and Model Code of Conduct comes into immediate effect across the country", "icon": "📢", "color": "#FF6B00", "key_actions": ["MCC activated nationwide", "Poll dates announced publicly", "Government discretionary spending freezes"]},
      {"phase": "Nomination Filing", "timing": "~75-80 days before polling", "description": "Candidates file nomination papers with the Returning Officer of their respective constituency", "icon": "📋", "color": "#3b5bdb", "key_actions": ["Form 2B submission to Returning Officer", "Security deposit payment Rs 25000 Lok Sabha", "Mandatory affidavit disclosing assets criminal record education"]},
      {"phase": "Scrutiny of Nominations", "timing": "~73 days before polling", "description": "Returning Officer carefully examines all filed nomination papers for legal validity and completeness", "icon": "🔍", "color": "#3b5bdb", "key_actions": ["All documents verified", "Candidate eligibility confirmed", "Invalid nominations officially rejected"]},
      {"phase": "Withdrawal of Candidatures", "timing": "~70 days before polling", "description": "Final date for candidates to withdraw from the contest. Official candidate list published by ECI.", "icon": "↩️", "color": "#3b5bdb", "key_actions": ["Final candidate list published", "Election symbols allotted by ECI", "Official campaign period begins"]},
      {"phase": "Campaign Period", "timing": "~68 days to 48 hours before polling", "description": "Candidates actively campaign across constituencies under strict Model Code of Conduct enforcement by ECI", "icon": "📣", "color": "#f4a261", "key_actions": ["Rally permissions required from authorities", "Campaign expenditure strictly tracked", "cVIGIL app active for MCC violation reports"]},
      {"phase": "Silence Period", "timing": "48 hours before polling day", "description": "All campaigning including social media political posts completely stops 48 hours before polling begins", "icon": "🤫", "color": "#f4a261", "key_actions": ["Zero physical or digital campaigning", "Social media political content banned", "Liquor distribution strictly prohibited"]},
      {"phase": "Polling Day", "timing": "Designated polling date", "description": "Registered voters cast votes via EVM at their assigned polling booths. Booths open 7AM to 6PM.", "icon": "🗳️", "color": "#138808", "key_actions": ["Carry approved photo ID document", "Find booth on voters.eci.gov.in", "Verify VVPAT slip after casting vote"]},
      {"phase": "Vote Counting", "timing": "ECI declared counting date", "description": "EVMs unsealed and votes counted at designated counting centres under strict ECI and candidate agent supervision", "icon": "🔢", "color": "#138808", "key_actions": ["Postal ballots counted first", "Round by round totals announced", "All candidate agents present throughout"]},
      {"phase": "Result Declaration", "timing": "Counting day", "description": "Winning candidates officially declared elected by the Returning Officer with margin of victory recorded", "icon": "🏆", "color": "#f4d03f", "key_actions": ["Winner receives election certificate", "Victory margin officially recorded", "Rejected votes count publicly disclosed"]},
      {"phase": "Government Formation", "timing": "Days after results", "description": "Winning party or alliance is invited by President or Governor to form government and swearing-in ceremony held", "icon": "🏛️", "color": "#f4d03f", "key_actions": ["272 seats needed for Lok Sabha majority", "Coalition negotiations if hung assembly", "Swearing-in at Rashtrapati Bhavan"]}
    ]
    CACHE["timeline"] = data
    return JSONResponse(content=data, headers={"X-Cache": "MISS"})

@app.get("/api/v1/checklist")
async def get_checklist(request: Request):
    check_rate_limit(request, 60)
    if "checklist" in CACHE:
        STATS["cache_hits"] += 1
        return JSONResponse(content=CACHE["checklist"], headers={"X-Cache": "HIT"})

    data = {"steps": [
      {"id": 1, "title": "Check Voter Registration", "description": "Visit voters.eci.gov.in or call 1950 to verify your name is on the Electoral Roll", "icon": "🔍"},
      {"id": 2, "title": "Register if Not Enrolled", "description": "Fill Form 6 online at nvsp.in or visit your local BLO Booth Level Officer", "icon": "📝"},
      {"id": 3, "title": "Get Your EPIC Voter ID", "description": "Apply for your Electors Photo Identity Card after registration approval from ECI", "icon": "🪪"},
      {"id": 4, "title": "Know Your Polling Booth", "description": "Find your assigned polling booth on voters.eci.gov.in using your Voter ID number", "icon": "📍"},
      {"id": 5, "title": "Check Valid ID Documents", "description": "Voter ID Aadhaar Passport Driving Licence PAN Card Bank Passbook with photo are all accepted", "icon": "📄"},
      {"id": 6, "title": "Research Your Candidates", "description": "Check candidates declared assets education and criminal records on affidavit.eci.gov.in before voting", "icon": "👤"},
      {"id": 7, "title": "Note Polling Date and Time", "description": "Polling booths open 7AM to 6PM. Arrive early to avoid long queues on election day.", "icon": "🕐"},
      {"id": 8, "title": "Download Voter Slip", "description": "Download your Voter Information Slip from Voter Helpline App or voters.eci.gov.in", "icon": "📱"},
      {"id": 9, "title": "Install cVIGIL App", "description": "Download cVIGIL to report any Model Code of Conduct violations with photo or video evidence", "icon": "📸"},
      {"id": 10, "title": "Cast Your Vote!", "description": "Go to booth press EVM button for your candidate verify VVPAT slip. Jai Hind! 🇮🇳", "icon": "✅"}
    ]}
    CACHE["checklist"] = data
    return JSONResponse(content=data, headers={"X-Cache": "MISS"})

QUESTIONS = [
  {"topic": "process", "question": "How many seats are there in the Lok Sabha?", "options": ["A. 543", "B. 545", "C. 552", "D. 500"], "correct": "A", "explanation": "The Lok Sabha has 543 elected seats representing constituencies across all states and union territories of India."},
  {"topic": "evm", "question": "What does EVM stand for?", "options": ["A. Electric Voting Module", "B. Electronic Voting Machine", "C. Electoral Voting Mechanism", "D. Electronic Vote Monitor"], "correct": "B", "explanation": "EVM stands for Electronic Voting Machine introduced to replace paper ballots and ensure tamper-proof voting."},
  {"topic": "rights", "question": "Which Article of the Constitution guarantees the right to vote?", "options": ["A. Article 19", "B. Article 21", "C. Article 326", "D. Article 370"], "correct": "C", "explanation": "Article 326 provides for elections to Lok Sabha and State Assemblies on the basis of adult suffrage for all citizens above 18."},
  {"topic": "rights", "question": "What is the minimum age to vote in India?", "options": ["A. 16", "B. 18", "C. 21", "D. 25"], "correct": "B", "explanation": "The 61st Constitutional Amendment in 1988 lowered the voting age from 21 to 18 years."},
  {"topic": "process", "question": "What does NOTA stand for?", "options": ["A. Not On The Agenda", "B. None of the Above", "C. No Other Than Approved", "D. National Option To Abstain"], "correct": "B", "explanation": "NOTA None of the Above allows voters to reject all candidates while still exercising their vote."},
  {"topic": "registration", "question": "What form is used for new voter registration in India?", "options": ["A. Form 7", "B. Form 8", "C. Form 6", "D. Form 9"], "correct": "C", "explanation": "Form 6 is the application form for inclusion of name in Electoral Roll for first time voters."},
  {"topic": "registration", "question": "What is the voter helpline number in India?", "options": ["A. 112", "B. 1800", "C. 1950", "D. 100"], "correct": "C", "explanation": "1950 is the national voter helpline number managed by Election Commission of India available in all states."},
  {"topic": "evm", "question": "What does VVPAT stand for?", "options": ["A. Voter Verified Paper Audit Trail", "B. Valid Vote Paper Audit Track", "C. Verified Voter Poll Audit Trail", "D. Voter Validated Print Audit Track"], "correct": "A", "explanation": "VVPAT prints a paper slip showing the candidate and symbol voted for allowing voters to verify their vote before it drops into sealed box."},
  {"topic": "process", "question": "What is the minimum age to contest a Lok Sabha election?", "options": ["A. 18", "B. 21", "C. 25", "D. 30"], "correct": "C", "explanation": "A candidate must be at least 25 years old to contest elections to the Lok Sabha or any State Legislative Assembly."},
  {"topic": "process", "question": "What is cVIGIL used for?", "options": ["A. Voter registration", "B. Reporting MCC violations", "C. EVM testing", "D. Candidate tracking"], "correct": "B", "explanation": "cVIGIL is an ECI app allowing citizens to report Model Code of Conduct violations with photo and video evidence resolved within 100 minutes."},
  {"topic": "registration", "question": "What does EPIC stand for?", "options": ["A. Electronic Poll Identity Card", "B. Electors Photo Identity Card", "C. Election Process Identity Certificate", "D. Electoral Poll Index Card"], "correct": "B", "explanation": "EPIC is the Electors Photo Identity Card commonly known as Voter ID issued by Election Commission of India."},
  {"topic": "process", "question": "How many hours before polling does the silence period begin?", "options": ["A. 24 hours", "B. 36 hours", "C. 48 hours", "D. 72 hours"], "correct": "C", "explanation": "Section 126 of Representation of the People Act 1951 prohibits campaigning 48 hours before polling concludes."},
  {"topic": "history", "question": "When was the Election Commission of India established?", "options": ["A. January 25 1950", "B. August 15 1947", "C. November 26 1949", "D. January 26 1950"], "correct": "A", "explanation": "ECI was established on January 25 1950 one day before India became a Republic. This day is celebrated as National Voters Day."},
  {"topic": "history", "question": "How many phases did the Lok Sabha 2024 general election have?", "options": ["A. 5", "B. 6", "C. 7", "D. 8"], "correct": "C", "explanation": "The 2024 Indian general election was conducted in 7 phases from April 19 to June 1 2024 making it the longest in recent history."},
  {"topic": "process", "question": "Which body allocates election symbols to political parties?", "options": ["A. Parliament of India", "B. Supreme Court", "C. Election Commission of India", "D. President of India"], "correct": "C", "explanation": "ECI has sole authority to recognize political parties and allot reserved election symbols under the Election Symbols Order 1968."},
  {"topic": "process", "question": "What is the security deposit amount for Lok Sabha candidates?", "options": ["A. Rs 10000", "B. Rs 25000", "C. Rs 50000", "D. Rs 5000"], "correct": "B", "explanation": "General category candidates must deposit Rs 25000 and SC ST candidates Rs 12500 as security deposit for Lok Sabha elections."},
  {"topic": "process", "question": "What is the minimum age to contest Rajya Sabha elections?", "options": ["A. 25", "B. 28", "C. 30", "D. 35"], "correct": "C", "explanation": "A candidate must be at least 30 years old to contest elections to the Rajya Sabha Council of States."},
  {"topic": "history", "question": "EVMs were first used in all Indian elections in which year?", "options": ["A. 1999", "B. 2004", "C. 2009", "D. 1996"], "correct": "B", "explanation": "EVMs were used nationwide for the first time in the 2004 Lok Sabha general elections after successful trials in smaller elections."},
  {"topic": "registration", "question": "Which portal shows mandatory candidate affidavit disclosures?", "options": ["A. nvsp.in", "B. eci.gov.in", "C. affidavit.eci.gov.in", "D. mygov.in"], "correct": "C", "explanation": "affidavit.eci.gov.in hosts all candidate affidavits disclosing criminal records assets liabilities and educational qualifications mandatorily."},
  {"topic": "process", "question": "How many seats does the Rajya Sabha have?", "options": ["A. 245", "B. 250", "C. 238", "D. 260"], "correct": "A", "explanation": "The Rajya Sabha has 245 seats of which 233 are elected by State and UT assemblies and 12 are nominated by the President."},
  {"topic": "registration", "question": "What is the maximum distance a polling booth can be from a voters residence per ECI norms?", "options": ["A. 1 km", "B. 2 km", "C. 3 km", "D. 5 km"], "correct": "B", "explanation": "ECI mandates that no voter should have to travel more than 2 kilometres to reach their assigned polling booth."},
  {"topic": "rights", "question": "Who appoints the Chief Election Commissioner of India?", "options": ["A. Prime Minister", "B. Speaker of Lok Sabha", "C. President of India", "D. Chief Justice of India"], "correct": "C", "explanation": "The Chief Election Commissioner is appointed by the President of India under Article 324 of the Constitution."},
  {"topic": "registration", "question": "NRI voters use which form to register on Indian electoral rolls?", "options": ["A. Form 6", "B. Form 6A", "C. Form 7", "D. Form 8A"], "correct": "B", "explanation": "Form 6A is the special application form for NRI Non Resident Indian voters to register on the electoral roll of their home constituency."},
  {"topic": "process", "question": "What is the full form of MCC in Indian elections?", "options": ["A. Model Campaign Code", "B. Mandatory Conduct Charter", "C. Model Code of Conduct", "D. Minimum Campaign Criteria"], "correct": "C", "explanation": "MCC Model Code of Conduct is a set of guidelines issued by ECI for political parties and candidates during election period."},
  {"topic": "history", "question": "NOTA was introduced in Indian elections in which year?", "options": ["A. 2009", "B. 2011", "C. 2013", "D. 2014"], "correct": "C", "explanation": "Supreme Court ordered introduction of NOTA in September 2013. It was first used in five state assembly elections in November 2013."},
  {"topic": "rights", "question": "Which Article of the Constitution deals with the Election Commission?", "options": ["A. Article 315", "B. Article 324", "C. Article 330", "D. Article 356"], "correct": "B", "explanation": "Article 324 of the Constitution vests the superintendence direction and control of elections in the Election Commission of India."},
  {"topic": "rights", "question": "Postal ballot is primarily used by which category of voters?", "options": ["A. NRIs only", "B. Students only", "C. Service voters and PwD voters", "D. Senior citizens only"], "correct": "C", "explanation": "Postal ballots are primarily used by service voters armed forces police government employees and persons with disabilities who cannot physically visit polling booths."},
  {"topic": "process", "question": "What is delimitation in Indian elections?", "options": ["A. Voter ID renewal process", "B. Redrawing constituency boundaries", "C. Vote counting procedure", "D. Candidate verification process"], "correct": "B", "explanation": "Delimitation is the process of redrawing boundaries of Lok Sabha and Vidhan Sabha constituencies based on population data from the Census."},
  {"topic": "rights", "question": "Anti-defection law is contained in which Schedule of the Indian Constitution?", "options": ["A. Eighth Schedule", "B. Ninth Schedule", "C. Tenth Schedule", "D. Eleventh Schedule"], "correct": "C", "explanation": "The Tenth Schedule added by 52nd Constitutional Amendment in 1985 contains the anti-defection law preventing elected members from switching parties."},
  {"topic": "process", "question": "How many Union Territories does India currently have?", "options": ["A. 6", "B. 7", "C. 8", "D. 9"], "correct": "C", "explanation": "India currently has 8 Union Territories after the reorganization of Jammu and Kashmir and Ladakh into separate UTs in October 2019."}
]

@app.get("/api/v1/quiz/question")
async def get_quiz_question(request: Request, topic: str = "all"):
    check_rate_limit(request, 60)
    gcloud_logger.info(f"Quiz fetch: topic={topic}")
    try:
        if topic and topic.lower() != "all topics" and topic.lower() != "all":
            filtered_q = [q for q in QUESTIONS if q["topic"].lower() in topic.lower() or topic.lower() in q["topic"].lower()]
            if not filtered_q:
                mapping = {"registration": "registration", "voting process": "process", "voter rights": "rights", "history": "history", "evm & tech": "evm"}
                mapped_topic = mapping.get(topic.lower(), "")
                if mapped_topic:
                     filtered_q = [q for q in QUESTIONS if q["topic"] == mapped_topic]
            
            if filtered_q:
                return JSONResponse(content=random.choice(filtered_q))
        return JSONResponse(content=random.choice(QUESTIONS))
    except Exception as e:
        gcloud_logger.error(f"Quiz error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error fetching quiz question")

@app.get("/api/v1/facts")
async def get_facts(request: Request):
    check_rate_limit(request, 60)
    if "facts" in CACHE:
        STATS["cache_hits"] += 1
        return JSONResponse(content=CACHE["facts"], headers={"X-Cache": "HIT"})

    data = [
        "India has the worlds largest democratic electorate with over 970 million registered voters as of 2024 🇮🇳",
        "The Election Commission of India was established on January 25 1950 now celebrated annually as National Voters Day",
        "Indias first general election in 1951-52 took nearly 4 months to complete across 176000 polling stations",
        "EVMs Electronic Voting Machines were first used nationwide in the 2004 Lok Sabha general elections",
        "NOTA None of the Above option was introduced in Indian elections in 2013 after a Supreme Court landmark order",
        "India has 543 Lok Sabha constituencies each representing roughly 1.5 to 2 million voters across the country",
        "The Model Code of Conduct typically comes into effect 4 to 8 weeks before election day restricting government actions",
        "ECI mandates that every polling booth must be within 2 kilometres of a voters residence for accessibility",
        "India deployed over 1 crore polling officials and security personnel across 1 million booths for the 2024 Lok Sabha",
        "The cVIGIL app created by ECI resolves Model Code of Conduct violation complaints within just 100 minutes of filing"
    ]
    CACHE["facts"] = data
    return JSONResponse(content=data, headers={"X-Cache": "MISS"})

@app.get("/api/v1/stats")
async def get_stats():
    return {
        "total_sessions": len(STATS["total_sessions"]),
        "total_messages": STATS["total_messages"],
        "uptime_seconds": int(time.time() - APP_START_TIME),
        "cache_hits": STATS["cache_hits"]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
