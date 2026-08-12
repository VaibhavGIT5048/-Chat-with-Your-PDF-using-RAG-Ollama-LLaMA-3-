#!/usr/bin/env bash
# Configure the rag-api (PRODUCTION) Container App from the local .env.
#
# Run from the repo root, on your Mac (not Cloud Shell — it needs .env):
#   az login
#   ./scripts/configure_production.sh
#
# This is the production counterpart of configure_staging.sh. Production was
# provisioned before Phase 1 and carries only the original eight environment
# variables, so it is missing every secret the auth, provider and parser work
# introduced. Deploying the current image onto it without running this first
# would crash-loop it — which is exactly what happened to staging.
#
# Safe to re-run: every operation is an upsert.
#
# THREE DIFFERENCES FROM STAGING, EACH DELIBERATE:
#   1. The PROD GitHub OAuth app credentials, not the dev pair. A GitHub OAuth
#      App allows exactly one callback URL, so the environments cannot share.
#   2. Its own JWT secret. Sharing staging's would mean a token minted on
#      staging is accepted by production.
#   3. A NEW Qdrant collection. The existing `chunks_collection` holds
#      1536-dimension vectors from text-embedding-3-small; the current code
#      emits 1024-dimension bge-m3 vectors. Writing into the old collection
#      would fail on dimension mismatch, so production moves to
#      chunks_collection_v2, which the app creates on first ingest with the
#      correct size and payload indexes.

set -euo pipefail

RG=rag-api-rg
APP=rag-api
ENVIRONMENT=rag-api-env
SHARE=rag-data                  # production's existing share
MOUNT=/home/appuser/app/data
COLLECTION=chunks_collection_v2

cd "$(dirname "$0")/.."
[ -f .env ] || { echo "ERROR: .env not found. Run from the repo root."; exit 1; }

# shellcheck disable=SC1091
set -a; source .env; set +a

need() {
  local name=$1
  if [ -z "${!name:-}" ]; then echo "ERROR: $name missing from .env"; exit 1; fi
}
for v in ACS_PRIMARY_CONNECTION_STRING ACS_SENDER_ADDRESS \
         GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET \
         GITHUB_CLIENT_ID_PROD GITHUB_CLIENT_SECRET_PROD \
         AZURE_OPENAI_API_KEY AZURE_OPENAI_ENDPOINT AZURE_OPENAI_MODEL \
         QDRANT_URL QDRANT_API_KEY; do
  need "$v"
done

PROD_JWT=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

echo "==> 1/4  Verify the production file share exists"
# Not created here: production's share already exists and holds live data.
# This only CONFIRMS it, because the staging incident was caused by a script
# that reported success when the share was in fact absent. Failing loudly on a
# missing share is the whole point.
STORAGE_ACCOUNT=$(az containerapp env storage show -n "$ENVIRONMENT" -g "$RG" \
  --storage-name "$SHARE" --query 'properties.azureFile.accountName' -o tsv 2>/dev/null || true)

if [ -z "${STORAGE_ACCOUNT:-}" ] || [ "$STORAGE_ACCOUNT" = "null" ]; then
  echo "ERROR: environment storage '$SHARE' is not registered on $ENVIRONMENT."
  echo "       Inspect with: az containerapp env storage list -n $ENVIRONMENT -g $RG -o table"
  exit 1
fi

SHARE_NAME=$(az containerapp env storage show -n "$ENVIRONMENT" -g "$RG" \
  --storage-name "$SHARE" --query 'properties.azureFile.shareName' -o tsv)

if ! az storage share-rm show --storage-account "$STORAGE_ACCOUNT" -g "$RG" \
     --name "$SHARE_NAME" --query name -o tsv >/dev/null 2>&1; then
  echo "ERROR: file share '$SHARE_NAME' does not exist in $STORAGE_ACCOUNT."
  echo "       Create it before deploying, or the container will fail to mount"
  echo "       with VolumeMountFailure and hold traffic while unhealthy."
  exit 1
fi
echo "    storage account: $STORAGE_ACCOUNT, share: $SHARE_NAME (confirmed present)"

echo "==> 2/4  Secrets"
az containerapp secret set -n "$APP" -g "$RG" --secrets \
  jwt-secret-key="$PROD_JWT" \
  acs-connection-string="$ACS_PRIMARY_CONNECTION_STRING" \
  github-client-secret="$GITHUB_CLIENT_SECRET_PROD" \
  google-client-secret="$GOOGLE_CLIENT_SECRET" \
  azure-openai-api-key="$AZURE_OPENAI_API_KEY" \
  --only-show-errors >/dev/null
echo "    5 secrets set"

echo "==> 3/4  Environment variables"
az containerapp update -n "$APP" -g "$RG" --set-env-vars \
  JWT_SECRET_KEY=secretref:jwt-secret-key \
  ACS_PRIMARY_CONNECTION_STRING=secretref:acs-connection-string \
  GITHUB_CLIENT_SECRET=secretref:github-client-secret \
  GOOGLE_CLIENT_SECRET=secretref:google-client-secret \
  AZURE_OPENAI_API_KEY=secretref:azure-openai-api-key \
  ACS_SENDER_ADDRESS="$ACS_SENDER_ADDRESS" \
  GITHUB_CLIENT_ID="$GITHUB_CLIENT_ID_PROD" \
  GOOGLE_CLIENT_ID="$GOOGLE_CLIENT_ID" \
  AZURE_OPENAI_ENDPOINT="$AZURE_OPENAI_ENDPOINT" \
  AZURE_OPENAI_MODEL="$AZURE_OPENAI_MODEL" \
  QDRANT_COLLECTION="$COLLECTION" \
  CHUNKING_STRATEGY="structure" \
  EMBEDDING_BACKEND="torch" \
  CORS_ALLOWED_ORIGINS="https://vaibhavgit5048.github.io" \
  --only-show-errors >/dev/null
echo "    env vars set (collection: $COLLECTION)"

echo "==> 4/4  Mount the volume with nobrl"
# Production's mount has NO mountOptions at all, which was survivable while it
# ran pre-Phase-1 code that never touched SQLite. The current code keeps its
# auth database on this share, and SQLite's fcntl byte-range locks cannot be
# honoured over SMB — every write fails SQLITE_BUSY and the app dies during
# startup. nobrl makes those locks no-ops, which is safe only because
# maxReplicas is 1 and there is therefore exactly one writer.
TMP=$(mktemp -d)
# JSON, not YAML: PyYAML isn't in the stdlib, and when it's missing the heredoc
# fails while the `az update` after it still "succeeds" against an unpatched
# file — the mount silently never lands. JSON is valid YAML to az.
az containerapp show -n "$APP" -g "$RG" -o json > "$TMP/app.json"
python3 - "$TMP/app.json" "$SHARE" "$MOUNT" <<'PY'
import sys, json
path, share, mount = sys.argv[1], sys.argv[2], sys.argv[3]
doc = json.load(open(path))
tpl = doc["properties"]["template"]
tpl["volumes"] = [{
    "name": "rag-data-volume",
    "storageName": share,
    "storageType": "AzureFile",
    "mountOptions": "uid=1000,gid=1000,dir_mode=0777,file_mode=0777,nobrl",
}]
for c in tpl["containers"]:
    c["volumeMounts"] = [{"volumeName": "rag-data-volume", "mountPath": mount}]
json.dump(doc, open(path, "w"), indent=2)
PY
az containerapp update -n "$APP" -g "$RG" --yaml "$TMP/app.json" --only-show-errors >/dev/null
rm -rf "$TMP"
echo "    volume mounted at $MOUNT with nobrl"

echo
echo "Done. Verify the mount actually carries nobrl before deploying:"
echo "  az containerapp show -n $APP -g $RG --query 'properties.template.volumes[0]'"
echo
echo "NOTE: production still runs the OLD image until the backend workflow is"
echo "      dispatched with target=production against main."
