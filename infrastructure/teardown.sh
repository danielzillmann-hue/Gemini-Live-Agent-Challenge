#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Genesis RPG — Teardown Script
#
# Removes ALL Genesis infrastructure from Google Cloud.
# Use with caution — this is destructive and irreversible.
#
# Usage:
#   export PROJECT_ID=your-project-id
#   ./infrastructure/teardown.sh
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID environment variable}"
REGION="${REGION:-us-central1}"

echo "⚠️  This will DELETE all Genesis infrastructure from ${PROJECT_ID}"
echo "    Press Enter to continue, Ctrl+C to abort..."
read -r

echo "▸ Deleting Cloud Run services..."
gcloud run services delete genesis-backend --region="${REGION}" --project="${PROJECT_ID}" --quiet 2>/dev/null || true
gcloud run services delete genesis-frontend --region="${REGION}" --project="${PROJECT_ID}" --quiet 2>/dev/null || true

echo "▸ Deleting Cloud Build trigger..."
gcloud builds triggers delete genesis-deploy --region="${REGION}" --project="${PROJECT_ID}" --quiet 2>/dev/null || true

echo "▸ Deleting Artifact Registry..."
gcloud artifacts repositories delete genesis --location="${REGION}" --project="${PROJECT_ID}" --quiet 2>/dev/null || true

echo "▸ Deleting Cloud Storage bucket..."
gcloud storage rm -r "gs://${PROJECT_ID}-media" 2>/dev/null || true

echo ""
echo "✅ Teardown complete. Firestore database preserved (delete manually if needed)."
