#!/usr/bin/env bash
# Configure the rag-api-staging Container App from the local .env.
#
# Run from the repo root, on your Mac (not Cloud Shell — it needs .env):
#   az login
#   ./scripts/configure_staging.sh
#
# Secrets are read from .env and pushed as Container App *secrets* with
# secretRef indirection, matching how qdrant-api-key is already handled — so
# they never appear in `az containerapp show` output, in shell history, or in
# a chat window.
#
# Safe to re-run: every operation is an upsert.

set -euo pipefail

RG=rag-api-rg
APP=rag-api-staging
ENVIRONMENT=rag-api-env
SHARE=rag-data-staging          # staging's OWN share — see note below
MOUNT=/home/appuser/app/data

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
         GITHUB_CLIENT_ID_DEV GITHUB_CLIENT_SECRET_DEV \
         AZURE_OPENAI_API_KEY AZURE_OPENAI_ENDPOINT AZURE_OPENAI_MODEL \
         QDRANT_URL QDRANT_API_KEY; do
  need "$v"
done

# A staging-specific JWT secret. Sharing prod's would mean a token minted on
# staging is accepted by production. Generated here rather than reused.
STAGING_JWT=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

echo "==> 1/4  Storage for staging's SQLite auth DB"
# Without a mounted volume, data/rag.db lives on ephemeral container storage
# and every account, document and chat history is wiped on each scale-to-zero.
# Staging gets its OWN share; pointing it at prod's rag-data-storage would put
# both environments on one auth database.
STORAGE_ACCOUNT=$(az containerapp env storage list -n "$ENVIRONMENT" -g "$RG" \
  --query "[?name=='rag-data-storage'].properties.azureFile.accountName | [0]" -o tsv)

if [ -z "$STORAGE_ACCOUNT" ] || [ "$STORAGE_ACCOUNT" = "null" ]; then
  echo "    Could not resolve the storage account from the prod mount."
  echo "    Inspect with: az containerapp env storage list -n $ENVIRONMENT -g $RG -o table"
  exit 1
fi
echo "    storage account: $STORAGE_ACCOUNT"

STORAGE_KEY=$(az storage account keys list -n "$STORAGE_ACCOUNT" -g "$RG" --query "[0].value" -o tsv)

# Do NOT swallow stderr here. A failure that prints "(share already exists)"
# regardless of cause once hid a share that was never created at all, and the
# revision then crash-looped on VolumeMountFailure with no clue why.
if ! az storage share-rm show \
    --storage-account "$STORAGE_ACCOUNT" -g "$RG" --name "$SHARE" >/dev/null 2>&1; then
  az storage share-rm create \
    --storage-account "$STORAGE_ACCOUNT" -g "$RG" --name "$SHARE" --quota 5 \
    --only-show-errors >/dev/null
  echo "    share '$SHARE' created"
else
  echo "    share '$SHARE' already exists"
fi

az containerapp env storage set -n "$ENVIRONMENT" -g "$RG" \
  --storage-name "$SHARE" \
  --azure-file-account-name "$STORAGE_ACCOUNT" \
  --azure-file-account-key "$STORAGE_KEY" \
  --azure-file-share-name "$SHARE" \
  --access-mode ReadWrite \
  --only-show-errors >/dev/null
echo "    environment storage '$SHARE' registered"

echo "==> 2/4  Secrets"
az containerapp secret set -n "$APP" -g "$RG" --secrets \
  jwt-secret-key="$STAGING_JWT" \
  acs-connection-string="$ACS_PRIMARY_CONNECTION_STRING" \
  github-client-secret="$GITHUB_CLIENT_SECRET_DEV" \
  google-client-secret="$GOOGLE_CLIENT_SECRET" \
  azure-openai-api-key="$AZURE_OPENAI_API_KEY" \
  --only-show-errors >/dev/null
echo "    5 secrets set"

echo "==> 3/4  Environment variables"
# Non-secret values inline; secret values by reference.
az containerapp update -n "$APP" -g "$RG" --set-env-vars \
  JWT_SECRET_KEY=secretref:jwt-secret-key \
  ACS_PRIMARY_CONNECTION_STRING=secretref:acs-connection-string \
  GITHUB_CLIENT_SECRET=secretref:github-client-secret \
  GOOGLE_CLIENT_SECRET=secretref:google-client-secret \
  AZURE_OPENAI_API_KEY=secretref:azure-openai-api-key \
  ACS_SENDER_ADDRESS="$ACS_SENDER_ADDRESS" \
  GITHUB_CLIENT_ID="$GITHUB_CLIENT_ID_DEV" \
  GOOGLE_CLIENT_ID="$GOOGLE_CLIENT_ID" \
  AZURE_OPENAI_ENDPOINT="$AZURE_OPENAI_ENDPOINT" \
  AZURE_OPENAI_MODEL="$AZURE_OPENAI_MODEL" \
  QDRANT_COLLECTION="chunks_collection_v2_staging" \
  CHUNKING_STRATEGY="structure" \
  EMBEDDING_BACKEND="torch" \
  CORS_ALLOWED_ORIGINS="https://vaibhavgit5048.github.io,http://localhost:3000" \
  --only-show-errors >/dev/null
echo "    env vars set"

echo "==> 4/4  Mount the volume"
# `az containerapp update` has no --volume flag, so the mount has to go
# through a YAML patch of the existing template.
TMP=$(mktemp -d)
az containerapp show -n "$APP" -g "$RG" -o yaml > "$TMP/app.yaml"
python3 - "$TMP/app.yaml" "$SHARE" "$MOUNT" <<'PY'
import sys, yaml
path, share, mount = sys.argv[1], sys.argv[2], sys.argv[3]
doc = yaml.safe_load(open(path))
tpl = doc["properties"]["template"]
tpl["volumes"] = [{"name": "rag-data-volume", "storageName": share, "storageType": "AzureFile"}]
for c in tpl["containers"]:
    c["volumeMounts"] = [{"volumeName": "rag-data-volume", "mountPath": mount}]
yaml.safe_dump(doc, open(path, "w"), sort_keys=False)
PY
az containerapp update -n "$APP" -g "$RG" --yaml "$TMP/app.yaml" --only-show-errors >/dev/null
rm -rf "$TMP"
echo "    volume mounted at $MOUNT"

echo
echo "Done. Verify:"
echo "  az containerapp show -n $APP -g $RG --query 'properties.template.volumes'"
echo "  curl -s https://\$(az containerapp show -n $APP -g $RG --query properties.configuration.ingress.fqdn -o tsv)/health"
echo
echo "NOTE: /health will still show the OLD image until you push to develop."
