# BallotAxis 🗳️🇮🇳
### From Awareness to Action.

**BallotAxis** is a premium, AI-powered civic education platform designed to empower Indian citizens with factual, non-partisan information about the electoral process. Built with **Google Gemini 1.5 Flash** and **FastAPI**, it bridges the gap between awareness and informed action.

---

## ✨ Key Features

- 🤖 **AI Election Assistant**: Real-time chat powered by Google Gemini with multi-language support (English & Hindi).
- 📅 **Interactive Election Timeline**: A visual journey through the 10 critical phases of an Indian election.
- 📋 **Voter Readiness Checklist**: A step-by-step guide to ensure you are ready to cast your vote.
- 🧠 **Civic Knowledge Quiz**: Test your understanding of Indian democracy with 30+ interactive questions.
- 🗳️ **EVM & VVPAT Simulator**: Educational modules explaining how Electronic Voting Machines work.
- 🕵️ **Myth Debunker**: Instant clarification on common election-related misconceptions.
- 📱 **Accessibility First**: Features high-contrast modes, font scaling, and a mobile-responsive glassmorphic UI.

---

## 🛠️ Tech Stack & Google Services Integration

BallotAxis is built using a modern, scalable stack with deep integration into the Google Cloud ecosystem:

- **Frontend**: Vanilla HTML5, CSS3 (Glassmorphism), JavaScript (ES6+)
- **Backend**: FastAPI (Python 3.10+)
- **AI Engine**: **Google Gemini 1.5 Flash** — Powers the intelligent, non-partisan chat responses and myth-busting logic.
- **Logging**: **Google Cloud Logging** — Structured logging for all chat requests, errors, and system events.
- **Security**: **Google Cloud Secret Manager** — Secure management of the Gemini API Key and other sensitive credentials.
- **Analytics**: **Google Analytics 4 (GA4)** — Comprehensive tracking of user behavior, feature engagement, and quiz performance.
- **Hosting**: **Google Cloud Run** — Serverless deployment for high availability and automatic scaling.
- **Typography**: **Google Fonts** — Inter and Poppins for a premium, readable aesthetic.

---

## 🚀 Getting Started

### Prerequisites
- Python 3.10 or higher
- A Google Gemini API Key (Get it from [Google AI Studio](https://aistudio.google.com/))

### Local Installation

1. **Clone the Repository**
   ```bash
   git clone https://github.com/your-username/BallotAxis.git
   cd BallotAxis
   ```

2. **Set Up Environment Variables**
   Create a `.env` file in the root directory:
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
   Visit `http://localhost:8080` in your browser.

---

## 🐳 Docker Deployment

To run BallotAxis using Docker:

1. **Build the Image**
   ```bash
   docker build -t ballotaxis .
   ```

2. **Run the Container**
   ```bash
   docker run -p 8080:8080 --env GEMINI_API_KEY=your_key_here ballotaxis
   ```

---

## ☁️ Deploying to Google Cloud Run

BallotAxis is optimized for deployment in the **asia-south1 (Mumbai)** region:

```bash
# Submit build to Container Registry
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/ballotaxis

# Deploy to Cloud Run
gcloud run deploy ballotaxis \
  --image gcr.io/YOUR_PROJECT_ID/ballotaxis \
  --platform managed \
  --region asia-south1 \
  --allow-unauthenticated \
  --set-env-vars GEMINI_API_KEY=your_key_here \
  --port 8080
```

---

## 🛡️ Non-Partisan Pledge
BallotAxis is strictly educational and non-partisan. It does not endorse any political party, candidate, or ideology. All AI responses are governed by a system prompt designed to ensure neutrality, factuality, and adherence to the Election Commission of India (ECI) guidelines.

---

## 📜 License
This project is for educational purposes. Please ensure compliance with Google Gemini's Terms of Service and ECI's data usage policies.

---

## 🤝 Contributing
Contributions are welcome! Whether it's fixing a bug, adding a feature, or improving the educational content, feel free to open a Pull Request.

---
*Made with ❤️ for Indian Democracy.*
