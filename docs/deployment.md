# Deployment: dev and prod environments

Two environments, both on Azure-issued hostnames. No custom domain.

| | Backend (Container Apps) | Frontend (Static Web Apps) |
|---|---|---|
| **dev** | `rag-api-staging` | `grounded-rag-dev` |
| **prod** | `rag-api` | `grounded-rag-prod` |

`develop` deploys to dev automatically. **Production is manual only** — promote
via Actions → Run workflow → `target: production` (backend) / `prod`
(frontend). Merging to `main` no longer ships anything on its own.

---

## 1. Create the two Static Web Apps

Free tier, `$0`. Run once, then note the hostname each command prints.

```bash
az login

az staticwebapp create \
  --name grounded-rag-dev \
  --resource-group rag-api-rg \
  --location centralindia \
  --sku Free

az staticwebapp create \
  --name grounded-rag-prod \
  --resource-group rag-api-rg \
  --location centralindia \
  --sku Free
```

Get the hostnames and deployment tokens:

```bash
for app in grounded-rag-dev grounded-rag-prod; do
  echo "== $app =="
  az staticwebapp show     --name $app -g rag-api-rg --query defaultHostname -o tsv
  az staticwebapp secrets list --name $app -g rag-api-rg --query properties.apiKey -o tsv
done
```

Azure generates the hostname (e.g. `calm-sand-0a1b2c3d.azurestaticapps.net`) —
you don't choose it, so everything below has to be filled in *after* this step.

## 2. GitHub repo configuration

**Secrets** (Settings → Secrets and variables → Actions → Secrets):

| Secret | Value |
|---|---|
| `AZURE_SWA_TOKEN_DEV` | deployment token for `grounded-rag-dev` |
| `AZURE_SWA_TOKEN_PROD` | deployment token for `grounded-rag-prod` |

**Variables** (same page → Variables tab). Include the scheme, no trailing slash:

| Variable | Value |
|---|---|
| `DEV_SITE_URL` | `https://<dev-swa-hostname>` |
| `PROD_SITE_URL` | `https://<prod-swa-hostname>` |
| `DEV_API_BASE_URL` | `https://rag-api-staging.<...>.azurecontainerapps.io` |
| `PROD_API_BASE_URL` | `https://rag-api.<...>.azurecontainerapps.io` |

Backend FQDNs:

```bash
for app in rag-api-staging rag-api; do
  az containerapp show -n $app -g rag-api-rg \
    --query properties.configuration.ingress.fqdn -o tsv
done
```

## 3. Backend CORS — do this before testing sign-in

The browser calls the API from the Static Web App origin, so each backend must
allow its own frontend. Missing this produces a CORS failure that looks
exactly like a broken API.

```bash
az containerapp update -n rag-api-staging -g rag-api-rg \
  --set-env-vars CORS_ALLOWED_ORIGINS="https://<dev-swa-hostname>,http://localhost:3000"

az containerapp update -n rag-api -g rag-api-rg \
  --set-env-vars CORS_ALLOWED_ORIGINS="https://<prod-swa-hostname>"
```

`localhost:3000` stays on dev only, so local work keeps talking to the dev API.

## 4. OAuth — sign-in breaks the moment the origin changes

OAuth providers only redirect to registered URLs. New frontend hostnames mean
every callback registration is now wrong, and the failure is at the provider's
consent screen (`redirect_uri_mismatch`), before any of our code runs.

**GitHub** — one callback URL per OAuth App, which is why there are two apps
(<https://github.com/settings/developers>):

| App | Homepage | Authorization callback URL |
|---|---|---|
| dev | `https://<dev-swa-hostname>` | `https://<dev-swa-hostname>/auth/callback/` |
| prod | `https://<prod-swa-hostname>` | `https://<prod-swa-hostname>/auth/callback/` |

Local development keeps using the **dev** app, so add
`http://localhost:3000/auth/callback/` there if you still need it — GitHub
allows only one, so pick per how you're working.

**Google** — one client, multiple redirect URIs
(<https://console.cloud.google.com/apis/credentials> → your OAuth client →
Authorised redirect URIs):

```
https://<dev-swa-hostname>/auth/callback/
https://<prod-swa-hostname>/auth/callback/
http://localhost:3000/auth/callback/
```

Then make sure each backend has the matching credentials as Container App
secrets — dev uses the dev GitHub app's pair, prod uses the prod app's:
`GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GOOGLE_CLIENT_ID`,
`GOOGLE_CLIENT_SECRET`.

## 5. Remaining backend secrets

From the local `.env`, which is the reconciled source of truth:

```bash
az containerapp update -n rag-api-staging -g rag-api-rg --set-env-vars \
  JWT_SECRET_KEY="..." \
  ACS_PRIMARY_CONNECTION_STRING="..." \
  ACS_SENDER_ADDRESS="..." \
  AZURE_OPENAI_API_KEY="..." \
  AZURE_OPENAI_ENDPOINT="..." \
  AZURE_OPENAI_MODEL="gpt-5-mini"
```

Without the `AZURE_OPENAI_*` trio, `/health` reports `degraded` and the
deploy workflow's own smoke test fails the run.

Use a **different** `JWT_SECRET_KEY` for prod than dev: sharing it means a
token minted on dev is accepted by production.

## 6. Verify

```bash
curl -s https://<dev-api-fqdn>/health          # expect "status":"ok"
curl -s -o /dev/null -w "%{http_code}\n" https://<dev-swa-hostname>   # expect 200
```

Then sign in on the dev site with GitHub, Google, and email/OTP. Sign-in is
the thing most likely to be misconfigured, because it depends on all three of
CORS, the callback registrations, and the backend secrets agreeing.

## Notes

- **`EMBEDDING_BACKEND=onnx` is unvalidated.** INT8 gains depend on
  AVX512-VNNI, which is x86-only — the dev Mac is arm64, so it can only be
  benchmarked meaningfully on Container Apps. Try it on dev first; it falls
  back to torch automatically if the ONNX artifact won't load.
- **Ingest**: `POST /ingest` is synchronous (~93s for 44 pages) and fits
  inside the ~240s ingress timeout. Use `POST /ingest/async` + `GET
  /ingest/jobs/{id}` for anything larger.
- **OTP email lands in spam** from the `*.azurecomm.net` managed domain, which
  Microsoft documents as testing-only. Accepted deliberately to avoid buying a
  domain; the Phase 4 verify-email page carries "check your spam folder" copy.
