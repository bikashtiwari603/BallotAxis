import os
import re
import time
from collections import defaultdict
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import google.generativeai as genai
from dotenv import load_dotenv
import random
import json

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

app = FastAPI(title="BallotAxis")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# Rate Limiter
RATE_LIMIT = 20
RATE_LIMIT_WINDOW = 60
ip_requests = defaultdict(list)

# Sessions
SESSIONS = defaultdict(list)
MAX_MESSAGES = 20

def check_rate_limit(request: Request):
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    ip_requests[ip] = [req_time for req_time in ip_requests[ip] if now - req_time < RATE_LIMIT_WINDOW]
    if len(ip_requests[ip]) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Too Many Requests")
    ip_requests[ip].append(now)

def sanitize_input(text: str) -> str:
    clean = re.compile('<.*?>')
    return re.sub(clean, '', text).strip()

class ChatRequest(BaseModel):
    message: str
    session_id: str
    hindi_mode: bool = False

SYSTEM_PROMPT = """You are BallotAxis AI, an expert, friendly, and strictly non-partisan Indian election assistant with the mission From Awareness to Action. You help Indian citizens understand:

1. Voter Registration in India
- How to register on voters.eci.gov.in
- Form 6 (new registration), Form 7 (deletion), Form 8 (correction)
- EPIC (Electors Photo Identity Card / Voter ID) application process
- Voter registration eligibility (18+ Indian citizen)
- How to check name on Electoral Roll
- NRI voter registration Form 6A

2. How Indian Elections Work
- Lok Sabha elections 543 constituencies House of the People
- Rajya Sabha elections indirect election by MLAs Council of States
- Vidhan Sabha State Legislative Assembly elections
- Vidhan Parishad State Legislative Council where applicable
- Panchayat and Municipal elections
- By-elections and mid-term polls

3. Election Commission of India
- Role and powers of ECI
- Chief Election Commissioner appointment and tenure
- Model Code of Conduct MCC
- ECI helpline 1950

4. Voting Process in India
- How EVMs Electronic Voting Machines work
- VVPAT Voter Verifiable Paper Audit Trail explanation
- How to vote at a polling booth step by step
- Polling booth timing 7AM to 6PM
- Documents accepted at polling booth
- NOTA None of the Above option

5. Indian Election Timeline
- Announcement of schedule by ECI
- Filing of nominations
- Scrutiny of nominations
- Withdrawal of candidatures
- Campaign period and silence period 48 hours before polling
- Polling day
- Counting of votes
- Declaration of results
- Formation of government

6. Constituencies and Representation
- Difference between Lok Sabha and Vidhan Sabha constituencies
- Delimitation Commission
- Reserved constituencies SC and ST
- How to find your constituency

7. Political Parties in India
- National parties vs State parties recognition criteria
- Election symbols allocation
- Anti-defection law Tenth Schedule

8. Candidate Information
- Eligibility age 25 for Lok Sabha 30 for Rajya Sabha
- Nomination process and security deposit Rs 25000 Lok Sabha
- Affidavit disclosure requirements criminal record assets education
- Campaign expenditure limits

9. Voter Rights and Grievances
- Right to vote Article 326 of Indian Constitution
- cVIGIL app for MCC violations
- Voter helpline 1950
- Accessible voting for differently-abled PwD voters
- Senior citizen voting facilities

10. Recent Indian Elections
- Lok Sabha 2024 general election 7 phases results overview
- Key state assembly elections 2023 and 2024
- Current political landscape factually and neutrally

Rules:
- Always be strictly non-partisan and neutral
- Never endorse BJP INC AAP TMC or any other party or candidate
- Use Hindi terms with English explanation where helpful example Chunav Aayog means Election Commission
- Always encourage voter participation
- Break complex processes into clear numbered steps
- Reference official portals voters.eci.gov.in eci.gov.in nvsp.in affidavit.eci.gov.in
- Cite relevant Articles of Indian Constitution when applicable
- Use emojis naturally to keep responses friendly
- If hindi_mode is true respond entirely in simple Hindi using Devanagari script"""

@app.get("/", response_class=HTMLResponse)
async def serve_index(request: Request):
    check_rate_limit(request)
    try:
        with open("static/index.html", "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content=content, media_type="text/html")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat")
async def chat_endpoint(req: ChatRequest, request: Request):
    check_rate_limit(request)
    try:
        user_message = sanitize_input(req.message)
        session_id = sanitize_input(req.session_id)
        hindi_mode = req.hindi_mode

        if not GEMINI_API_KEY:
            raise HTTPException(status_code=500, detail="Gemini API Key not configured.")

        if session_id not in SESSIONS:
            SESSIONS[session_id] = []

        history = SESSIONS[session_id]

        model = genai.GenerativeModel('gemini-1.5-flash-latest', system_instruction=SYSTEM_PROMPT)

        gemini_history = []
        for msg in history:
            gemini_history.append({"role": "user" if msg["role"] == "user" else "model", "parts": [msg["content"]]})
        
        chat = model.start_chat(history=gemini_history)
        
        prompt = user_message
        if hindi_mode:
             prompt = f"[HINDI MODE: Respond entirely in simple Hindi using Devanagari script] {user_message}"

        response = chat.send_message(
            prompt,
            generation_config=genai.types.GenerationConfig(
                response_mime_type="application/json",
                response_schema={"type": "OBJECT", "properties": {"response": {"type": "STRING"}, "suggestions": {"type": "ARRAY", "items": {"type": "STRING"}}}, "required": ["response", "suggestions"]}
            )
        )
        
        try:
            resp_data = json.loads(response.text)
        except json.JSONDecodeError:
             resp_data = {"response": response.text, "suggestions": ["Tell me more", "What else should I know?"]}

        history.append({"role": "user", "content": user_message})
        history.append({"role": "model", "content": resp_data.get("response", "")})
        
        if len(history) > MAX_MESSAGES * 2:
            SESSIONS[session_id] = history[-(MAX_MESSAGES * 2):]

        return JSONResponse(content=resp_data)

    except Exception as e:
        print("Error in /chat:", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/timeline")
async def get_timeline(request: Request):
    check_rate_limit(request)
    try:
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
        return JSONResponse(content=data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/checklist")
async def get_checklist(request: Request):
    check_rate_limit(request)
    try:
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
        return JSONResponse(content=data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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

@app.get("/quiz/question")
async def get_quiz_question(request: Request, topic: str = "all"):
    check_rate_limit(request)
    try:
        if topic and topic.lower() != "all topics" and topic.lower() != "all":
            filtered_q = [q for q in QUESTIONS if q["topic"].lower() in topic.lower() or topic.lower() in q["topic"].lower()]
            if not filtered_q:
                mapping = {
                    "registration": "registration",
                    "voting process": "process",
                    "voter rights": "rights",
                    "history": "history",
                    "evm & tech": "evm"
                }
                mapped_topic = mapping.get(topic.lower(), "")
                if mapped_topic:
                     filtered_q = [q for q in QUESTIONS if q["topic"] == mapped_topic]
            
            if filtered_q:
                return JSONResponse(content=random.choice(filtered_q))
        return JSONResponse(content=random.choice(QUESTIONS))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/facts")
async def get_facts(request: Request):
    check_rate_limit(request)
    try:
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
        return JSONResponse(content=data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def get_health(request: Request):
    check_rate_limit(request)
    try:
        return JSONResponse(content={"status": "ok", "app": "BallotAxis", "tagline": "From Awareness to Action."})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
