# BallotAxis Cloud Run Deployment Script 🚀

# 1. Login (Uncomment if not logged in)
# gcloud auth login

# 2. Configuration (REPLACE THESE)
$PROJECT_ID = "election-495208"
$GEMINI_API_KEY = "YOUR_GEMINI_API_KEY_HERE"
$REGION = "asia-south1" # Mumbai

Write-Host "Starting deployment for project: $PROJECT_ID..." -ForegroundColor Cyan

# 3. Set Project
gcloud config set project $PROJECT_ID

# 4. Enable APIs
Write-Host "Enabling necessary APIs..." -ForegroundColor Yellow
gcloud services enable run.googleapis.com containerregistry.googleapis.com cloudbuild.googleapis.com

# 5. Build and Push
Write-Host "Building and pushing Docker image to Google Container Registry..." -ForegroundColor Yellow
gcloud builds submit --tag gcr.io/$PROJECT_ID/ballotaxis

# 6. Deploy
Write-Host "Deploying to Cloud Run..." -ForegroundColor Green
gcloud run deploy ballotaxis `
  --image gcr.io/$PROJECT_ID/ballotaxis `
  --platform managed `
  --region $REGION `
  --allow-unauthenticated `
  --set-env-vars GEMINI_API_KEY=$GEMINI_API_KEY `
  --port 8080

Write-Host "Deployment Complete! 🗳️🇮🇳" -ForegroundColor Green
