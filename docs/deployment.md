# Deployment: dev and prod environments

| | dev (review) | prod (live) |
|---|---|---|
| **Frontend** | `https://<owner>.github.io/private-rag-core/dev/` | `https://<owner>.github.io/private-rag-core/` |
| **Backend** | `rag-api-staging` (Azure Container Apps) | `rag-api` (Azure Container Apps) |
| **Built from** | `develop` | `main` |

Frontend is on **GitHub Pages**; backend is on **Azure Container Apps**.

## How the two frontend URLs work

GitHub Pages publishes exactly **one artifact per repository**, so both
environments are produced in a single workflow run: it checks out `main` and
`develop` separately, builds each with its own `BASE_PATH`
(`/private-rag-core` and `/private-rag-core/dev`), and publishes them together.

The consequence to understand: a push to `develop` *does* republish prod — but
it rebuilds prod **from `main`**, so live content only changes when `main`
changes. **Merging to `main` is the promotion step.** Nothing reaches prod
merely because dev moved.

The backend has no such constraint (two independent Container Apps), so there
production is strictly manual: `develop` auto-deploys to `rag-api-staging`,
and `rag-api` only moves via Actions → *Deploy backend to Azure* → Run
workflow → `target: production`.

---

## 1. GitHub repo variables

Settings → Secrets and variables → Actions → **Variables**. Include the
scheme, no trailing slash:

| Variable | Value |
|---|---|
| `DEV_API_BASE_URL` | `https://rag-api-staging.<...>.azurecontainerapps.io` |
| `PROD_API_BASE_URL` | `https://rag-api.<...>.azurecontainerapps.io` |

Get the backend FQDNs:

```bash
az login
for app in rag-api-staging rag-api; do
  az containerapp show -n $app -g rag-api-rg \
    --query properties.configuration.ingress.fqdn -o tsv
done
```

Pages must be set to **GitHub Actions** as its source (Settings → Pages →
Build and deployment → Source), not "Deploy from a branch".

## 2. Backend CORS — do this before testing sign-in

The browser calls the API from the Pages origin. Both environments share the
*same* origin (`https://<owner>.github.io`) because they differ only by path,
and CORS is origin-based — paths are not part of an origin. So each backend
allows that one origin:

```bash
az containerapp update -n rag-api-staging -g rag-api-rg \
  --set-env-vars CORS_ALLOWED_ORIGINS="https://<owner>.github.io,http://localhost:3000"

az containerapp update -n rag-api -g rag-api-rg \
  --set-env-vars CORS_ALLOWED_ORIGINS="https://<owner>.github.io"
```

Note this means CORS alone cannot keep the dev site off the prod API — the
separation comes from each build being compiled with its own
`NEXT_PUBLIC_API_BASE_URL`, not from the browser refusing the call.

`localhost:3000` stays on dev only, so local work talks to the dev backend.

## 3. OAuth — sign-in breaks the moment a redirect URL is wrong

Providers only redirect to **registered** URLs. Because dev and prod are
different *paths* on the same host, they need different callback URLs:

```
prod  https://<owner>.github.io/private-rag-core/auth/callback/
dev   https://<owner>.github.io/private-rag-core/dev/auth/callback/
```

A mismatch fails at the provider's consent screen with
`redirect_uri_mismatch`, before any of our code runs.

**GitHub** — one callback URL per OAuth App, which is why there are two apps
(<https://github.com/settings/developers>):

| App | Homepage | Authorization callback URL |
|---|---|---|
| prod | `https://<owner>.github.io/private-rag-core/` | `https://<owner>.github.io/private-rag-core/auth/callback/` |
| dev | `https://<owner>.github.io/private-rag-core/dev/` | `https://<owner>.github.io/private-rag-core/dev/auth/callback/` |

Local development also uses the **dev** app, and GitHub permits only one
callback per app — so swap in `http://localhost:3000/auth/callback/` while
working locally, or register a third app for it.

**Google** — one client takes several redirect URIs
(<https://console.cloud.google.com/apis/credentials> → OAuth client →
Authorised redirect URIs):

```
https://<owner>.github.io/private-rag-core/auth/callback/
https://<owner>.github.io/private-rag-core/dev/auth/callback/
http://localhost:3000/auth/callback/
```

Each backend needs the credentials matching its own frontend — dev uses the
dev GitHub app's pair, prod uses the prod app's: `GITHUB_CLIENT_ID`,
`GITHUB_CLIENT_SECRET`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`.

## 4. Remaining backend secrets

From the local `.env` (the reconciled source of truth):

```bash
az containerapp update -n rag-api-staging -g rag-api-rg --set-env-vars \
  JWT_SECRET_KEY="..." \
  ACS_PRIMARY_CONNECTION_STRING="..." \
  ACS_SENDER_ADDRESS="..." \
  AZURE_OPENAI_API_KEY="..." \
  AZURE_OPENAI_ENDPOINT="..." \
  AZURE_OPENAI_MODEL="gpt-5-mini"
```

Without the `AZURE_OPENAI_*` trio, `/health` reports `degraded` and the deploy
workflow's own smoke test fails the run.

Use a **different `JWT_SECRET_KEY` for prod than dev** — sharing it means a
token minted on dev is accepted by production.

## 5. Verify

```bash
curl -s https://<dev-api-fqdn>/health      # expect "status":"ok"
curl -s -o /dev/null -w "%{http_code}\n" https://<owner>.github.io/private-rag-core/
curl -s -o /dev/null -w "%{http_code}\n" https://<owner>.github.io/private-rag-core/dev/
```

Then sign in on the **dev** site with GitHub, Google, and email/OTP. Sign-in
is the most likely thing to be misconfigured, since it needs CORS, the
callback registrations, and the backend secrets to all agree.

## Notes

- **`EMBEDDING_BACKEND=onnx` is unvalidated.** INT8 gains depend on
  AVX512-VNNI (x86-only); the dev Mac is arm64, so it can only be benchmarked
  meaningfully on Container Apps. Try it on `rag-api-staging` first — it falls
  back to torch automatically if the ONNX artifact won't load.
- **Ingest**: `POST /ingest` is synchronous (~93s for 44 pages), inside the
  ~240s ingress timeout. Use `POST /ingest/async` + `GET /ingest/jobs/{id}`
  for larger documents.
- **OTP email lands in spam** from the `*.azurecomm.net` managed domain, which
  Microsoft documents as testing-only. Accepted deliberately to avoid buying a
  domain; the Phase 4 verify-email page carries "check your spam folder" copy.
