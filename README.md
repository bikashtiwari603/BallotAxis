# BallotAxis 🗳️🇮🇳
### From Awareness to Action.

**BallotAxis** is a premium, AI-powered civic education platform designed to empower Indian citizens with factual, non-partisan information about the electoral process. Built with **Google Gemini 1.5 Flash** and **FastAPI**, it bridges the gap between awareness and informed action by solving the critical lack of civic awareness among eligible voters.

---

## ✨ Key Features

- 🤖 **AI Election Assistant**: Real-time chat powered by Google Gemini with multi-language support (English & Hindi).
- 📅 **Interactive Election Timeline**: A visual journey through the critical phases of an Indian election.
- 📋 **Voter Readiness Checklist**: A step-by-step guide to ensure you are ready to cast your vote.
- 🧠 **Civic Knowledge Quiz**: Test your understanding of Indian democracy with 30+ interactive questions.
- 🗳️ **EVM & VVPAT Simulator**: Educational modules explaining how Electronic Voting Machines work.
- 📱 **Accessibility (WCAG AA)**: Fully compliant with ARIA standards, keyboard navigation, and high-contrast modes.
- 🛡️ **Hardened Security**: Robust CSP, rate limiting, and encrypted credential management.

---

## 🎯 Problem We Solve
Millions of eligible Indian voters lack critical awareness about voter registration, the EVM voting process, and candidate research. This gap in civic education leads to lower participation and misinformation. BallotAxis provides personalized, non-partisan guidance to help every citizen move *From Awareness to Action*.

---

## 🛠️ Tech Stack & Google Services Integration

BallotAxis is built with deep integration into the Google Cloud ecosystem:

- **AI Engine**: **Google Gemini 1.5 Flash** — Powers intelligent chat and myth-busting logic.
- **Logging**: **Google Cloud Logging** — Structured logging with `X-Request-ID` traceability.
- **Security**: **Google Cloud Secret Manager** — Secure management of the Gemini API Key.
- **Analytics**: **Google Analytics 4 (GA4)** — Comprehensive tracking of feature engagement.
- **Hosting**: **Google Cloud Run** — Serverless deployment with automatic scaling.

---

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- Google Gemini API Key

### Local Installation

1. **Clone the Repository**
   ```bash
   git clone https://github.com/bikashtiwari603/BallotAxis.git
   cd BallotAxis
   ```

2. **Set Up Environment Variables**
   Create a `.env` file:
   ```bash
   GEMINI_API_KEY=your_gemini_api_key_here
   ```

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the Application**
   ```bash
   uvicorn main:app --reload --port 8080
   ```

---

## 🧪 Testing
The project includes a comprehensive test suite (100% coverage goal) covering edge cases, performance benchmarks, and security validations.

```bash
pytest test_main.py -v
```

---

## 🛡️ Security & Compliance
- **WCAG 2.1 AA**: Accessibility compliant.
- **Strict CSP**: Protection against XSS and data injection.
- **Rate Limiting**: Per-endpoint protection against DoS and API abuse.
- **X-Request-ID**: End-to-end request traceability.

---

## 📜 License
For educational purposes only. Not affiliated with the Election Commission of India.

---
*Made with ❤️ for Indian Democracy.*
