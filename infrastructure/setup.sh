#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Genesis RPG — Automated Cloud Infrastructure Setup
#
# This script provisions ALL Google Cloud resources needed to run Genesis.
# Run once to set up a new project, or re-run to verify/update infrastructure.
#
# Usage:
#   export PROJECT_ID=your-project-id
#   export REGION=us-central1
#   export GITHUB_OWNER=your-github-username
#   export GITHUB_REPO=your-repo-name
#   ./infrastructure/setup.sh
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID environment variable}"
REGION="${REGION:-us-central1}"
GITHUB_OWNER="${GITHUB_OWNER:-danielzillmann-hue}"
GITHUB_REPO="${GITHUB_REPO:-Gemini-Live-Agent-Challenge}"

BACKEND_SERVICE="genesis-backend"
FRONTEND_SERVICE="genesis-frontend"
ARTIFACT_REPO="genesis"
STORAGE_BUCKET="${PROJECT_ID}-media"
CONNECTION_NAME="genesis-github"
TRIGGER_NAME="genesis-deploy"
REPO_LINK_NAME="genesis-repo"

echo "════════════════════════════════════════════════════════════════"
echo "  Genesis RPG — Infrastructure Setup"
echo "  Project:  ${PROJECT_ID}"
echo "  Region:   ${REGION}"
echo "  GitHub:   ${GITHUB_OWNER}/${GITHUB_REPO}"
echo "════════════════════════════════════════════════════════════════"

# ── Step 1: Set project ───────────────────────────────────────────────────────

echo ""
echo "▸ Setting active project..."
gcloud config set project "${PROJECT_ID}"

# ── Step 2: Enable APIs ──────────────────────────────────────────────────────

echo ""
echo "▸ Enabling required APIs..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  firestore.googleapis.com \
  aiplatform.googleapis.com \
  texttospeech.googleapis.com \
  storage.googleapis.com \
  --project="${PROJECT_ID}"

echo "  ✓ APIs enabled"

# ── Step 3: Create Artifact Registry ─────────────────────────────────────────

echo ""
echo "▸ Creating Artifact Registry repository..."
if gcloud artifacts repositories describe "${ARTIFACT_REPO}" \
    --location="${REGION}" --project="${PROJECT_ID}" &>/dev/null; then
  echo "  ✓ Already exists"
else
  gcloud artifacts repositories create "${ARTIFACT_REPO}" \
    --repository-format=docker \
    --location="${REGION}" \
    --project="${PROJECT_ID}"
  echo "  ✓ Created"
fi

# ── Step 4: Create Cloud Storage bucket ──────────────────────────────────────

echo ""
echo "▸ Creating Cloud Storage bucket for media assets..."
if gcloud storage buckets describe "gs://${STORAGE_BUCKET}" &>/dev/null; then
  echo "  ✓ Already exists"
else
  gcloud storage buckets create "gs://${STORAGE_BUCKET}" \
    --project="${PROJECT_ID}" \
    --location="${REGION}" \
    --uniform-bucket-level-access
  echo "  ✓ Created"
fi

# Make bucket publicly readable
echo "  ▸ Setting public read access..."
gcloud storage buckets add-iam-policy-binding "gs://${STORAGE_BUCKET}" \
  --member=allUsers \
  --role=roles/storage.objectViewer \
  --quiet 2>/dev/null || true
echo "  ✓ Public access configured"

# ── Step 5: Create Firestore database ────────────────────────────────────────

echo ""
echo "▸ Creating Firestore database..."
if gcloud firestore databases list --project="${PROJECT_ID}" 2>/dev/null | grep -q "(default)"; then
  echo "  ✓ Already exists"
else
  gcloud firestore databases create \
    --location="${REGION}" \
    --project="${PROJECT_ID}"
  echo "  ✓ Created"
fi

# ── Step 6: Build and push Docker images ─────────────────────────────────────

echo ""
echo "▸ Building backend Docker image..."
gcloud builds submit \
  --tag "${REGION}-docker.pkg.dev/${PROJECT_ID}/${ARTIFACT_REPO}/backend:latest" \
  --project="${PROJECT_ID}" \
  backend/

echo "▸ Building frontend Docker image..."
# Get backend URL for frontend build args
BACKEND_URL="https://${BACKEND_SERVICE}-$(gcloud projects describe ${PROJECT_ID} --format='value(projectNumber)').${REGION}.run.app"

gcloud builds submit \
  --tag "${REGION}-docker.pkg.dev/${PROJECT_ID}/${ARTIFACT_REPO}/frontend:latest" \
  --project="${PROJECT_ID}" \
  frontend/ \
  --build-arg "NEXT_PUBLIC_API_URL=${BACKEND_URL}" \
  --build-arg "NEXT_PUBLIC_WS_URL=wss://$(echo ${BACKEND_URL} | sed 's|https://||')"

echo "  ✓ Images built and pushed"

# ── Step 7: Deploy Cloud Run services ────────────────────────────────────────

echo ""
echo "▸ Deploying backend to Cloud Run..."
gcloud run deploy "${BACKEND_SERVICE}" \
  --image="${REGION}-docker.pkg.dev/${PROJECT_ID}/${ARTIFACT_REPO}/backend:latest" \
  --region="${REGION}" \
  --platform=managed \
  --allow-unauthenticated \
  --memory=2Gi \
  --cpu=2 \
  --timeout=300 \
  --session-affinity \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_REGION=${REGION},STORAGE_BUCKET=${STORAGE_BUCKET},CORS_ORIGINS=*,GOOGLE_GENAI_USE_VERTEXAI=1" \
  --project="${PROJECT_ID}"

BACKEND_URL=$(gcloud run services describe "${BACKEND_SERVICE}" \
  --region="${REGION}" --project="${PROJECT_ID}" \
  --format="value(status.url)")

echo "  ✓ Backend deployed: ${BACKEND_URL}"

echo ""
echo "▸ Deploying frontend to Cloud Run..."
gcloud run deploy "${FRONTEND_SERVICE}" \
  --image="${REGION}-docker.pkg.dev/${PROJECT_ID}/${ARTIFACT_REPO}/frontend:latest" \
  --region="${REGION}" \
  --platform=managed \
  --allow-unauthenticated \
  --memory=512Mi \
  --port=3000 \
  --project="${PROJECT_ID}"

FRONTEND_URL=$(gcloud run services describe "${FRONTEND_SERVICE}" \
  --region="${REGION}" --project="${PROJECT_ID}" \
  --format="value(status.url)")

echo "  ✓ Frontend deployed: ${FRONTEND_URL}"

# ── Step 8: Set up Cloud Build trigger ───────────────────────────────────────

echo ""
echo "▸ Setting up Cloud Build CI/CD trigger..."

# Create GitHub connection (requires manual OAuth step)
if gcloud builds connections describe "${CONNECTION_NAME}" \
    --region="${REGION}" --project="${PROJECT_ID}" &>/dev/null; then
  echo "  ✓ GitHub connection exists"
else
  echo "  ▸ Creating GitHub connection (requires browser OAuth)..."
  gcloud builds connections create github "${CONNECTION_NAME}" \
    --region="${REGION}" --project="${PROJECT_ID}"
  echo ""
  echo "  ⚠ MANUAL STEP: Complete GitHub OAuth in your browser."
  echo "    Follow the link above to authorize Cloud Build."
  echo "    Press Enter when done..."
  read -r
fi

# Link repository
if gcloud builds repositories describe "${REPO_LINK_NAME}" \
    --connection="${CONNECTION_NAME}" \
    --region="${REGION}" --project="${PROJECT_ID}" &>/dev/null; then
  echo "  ✓ Repository link exists"
else
  gcloud builds repositories create "${REPO_LINK_NAME}" \
    --remote-uri="https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}.git" \
    --connection="${CONNECTION_NAME}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}"
  echo "  ✓ Repository linked"
fi

# Create trigger
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)")
SERVICE_ACCOUNT="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

if gcloud builds triggers describe "${TRIGGER_NAME}" \
    --region="${REGION}" --project="${PROJECT_ID}" &>/dev/null; then
  echo "  ✓ Build trigger exists"
else
  gcloud builds triggers create github \
    --name="${TRIGGER_NAME}" \
    --repository="projects/${PROJECT_ID}/locations/${REGION}/connections/${CONNECTION_NAME}/repositories/${REPO_LINK_NAME}" \
    --branch-pattern="^main$" \
    --build-config="cloudbuild.yaml" \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --service-account="projects/${PROJECT_ID}/serviceAccounts/${SERVICE_ACCOUNT}"
  echo "  ✓ Build trigger created"
fi

# ── Done ─────────────────────────────────────────────────────────────────────

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  ✅ Infrastructure setup complete!"
echo ""
echo "  Frontend:  ${FRONTEND_URL}"
echo "  Backend:   ${BACKEND_URL}"
echo "  Storage:   gs://${STORAGE_BUCKET}"
echo "  CI/CD:     Push to main → auto-deploys both services"
echo ""
echo "  Next steps:"
echo "    1. Visit ${FRONTEND_URL} to play"
echo "    2. Push code changes → Cloud Build auto-deploys"
echo "    3. Run tests: cd backend && pytest -v"
echo "════════════════════════════════════════════════════════════════"
