# Secure deploy — reads the API token from a local file, never from chat history.
#
# WHY A FILE, NOT A PASTE:
#   Chat transcripts persist. A Cloudflare API token pasted into a conversation
#   lives there indefinitely. MASTER-PROMPT-V2 §24 requires secrets to be held
#   by exactly one service and never exposed to an agent. A local file that is
#   git-ignored and never echoed satisfies that; a chat paste does not.
#
# USAGE:
#   1. Save your token to:  C:\Users\howab\.cf-token        (no quotes, no spaces)
#   2. Save your account id to: C:\Users\howab\.cf-account-id  (32 hex chars)
#      (Cloudflare dashboard -> any account -> sidebar, or wrangler whoami)
#   3. Run:                 bash deploy.sh
#
# The token is read into the environment for the lifetime of this process only.
#
# NOTE (fixed 2026-10-21): the previous version of this script copied a
# widget.html that no longer exists and NEVER copied worker/index.js into
# dist/_worker.js. Deploying with it would have published the site WITHOUT the
# worker, which silently kills the /mcp endpoint. It is now explicit about
# every file that has to be in the deploy directory, and it refuses to deploy
# if the worker is missing.

set -e

TOKEN_FILE="$HOME/.cf-token"
ACCOUNT_FILE="$HOME/.cf-account-id"
PROJECT="uk-legal-changes"
HERE="$(cd "$(dirname "$0")" && pwd)"
DIST="$HERE/dist"

if [ ! -f "$TOKEN_FILE" ]; then
  echo "ERROR: no token file at $TOKEN_FILE"
  echo
  echo "Create the token first:"
  echo "  1. https://dash.cloudflare.com/profile/api-tokens"
  echo "  2. Create Token -> Custom Token -> Get started"
  echo "  3. Permissions: Account | Cloudflare Pages | Edit"
  echo "  4. Continue to summary -> Create Token -> copy it"
  echo "  5. Save it into $TOKEN_FILE"
  exit 1
fi

# Read without printing. Strip whitespace/newlines.
CLOUDFLARE_API_TOKEN="$(tr -d '[:space:]' < "$TOKEN_FILE")"
export CLOUDFLARE_API_TOKEN

if [ -z "$CLOUDFLARE_API_TOKEN" ]; then
  echo "ERROR: token file is empty."
  exit 1
fi

# The token is account-scoped, so wrangler cannot list accounts and needs the
# account id handed to it.
if [ -f "$ACCOUNT_FILE" ]; then
  CLOUDFLARE_ACCOUNT_ID="$(tr -d '[:space:]' < "$ACCOUNT_FILE")"
  export CLOUDFLARE_ACCOUNT_ID
  echo "==> Account id loaded from $ACCOUNT_FILE"
else
  echo "NOTE: no $ACCOUNT_FILE found. Falling back to CLOUDFLARE_ACCOUNT_ID in the environment."
fi

echo "==> Token loaded (${#CLOUDFLARE_API_TOKEN} chars, value not shown)"

echo "==> Assembling the deploy directory"
mkdir -p "$DIST"

# The site is rebuilt from the database only when that database is present.
# pipeline.db is git-ignored; when it is missing the committed dist/ is used
# and MUST NOT be silently replaced with an older build.
if [ -f "$HERE/pipeline.db" ]; then
  echo "    pipeline.db found - rebuilding the site from source"
  python "$HERE/build_site.py"
else
  echo "    pipeline.db NOT found - deploying the existing dist/ as-is"
fi

# The worker is what serves /mcp. If it is missing the site still deploys but
# the MCP endpoint is gone, so refuse to deploy without it.
if [ ! -f "$HERE/worker/index.js" ]; then
  echo "ERROR: worker/index.js is missing - refusing to deploy (it would kill /mcp)."
  exit 1
fi
cp "$HERE/worker/index.js" "$DIST/_worker.js"

# MCP server card (SEP-2127) for AI-catalog discovery.
if [ -f "$HERE/registry/server-card.json" ]; then
  mkdir -p "$DIST/.well-known/mcp-server-card"
  cp "$HERE/registry/server-card.json" "$DIST/.well-known/mcp-server-card/uk-legislation-changes"
  echo "    server card staged at .well-known/mcp-server-card/uk-legislation-changes"
fi

# 400x400 logo referenced by the card.
[ -f "$HERE/logo_400.png" ] && cp "$HERE/logo_400.png" "$DIST/logo_400.png"

# CORS + content type for the discovery endpoints.
cat > "$DIST/_headers" <<'HEADERS'
/.well-known/mcp-server-card
  Access-Control-Allow-Origin: *
  Access-Control-Allow-Methods: GET
  Access-Control-Allow-Headers: Content-Type
  Cache-Control: public, max-age=3600
  Content-Type: application/json

/.well-known/mcp-server-card/*
  Access-Control-Allow-Origin: *
  Access-Control-Allow-Methods: GET
  Access-Control-Allow-Headers: Content-Type
  Cache-Control: public, max-age=3600
  Content-Type: application/json
HEADERS

echo "==> Deploying to Cloudflare Pages (free tier)"
npx -y wrangler pages deploy "$DIST" \
    --project-name "$PROJECT" \
    --commit-dirty=true

echo
echo "==> Deployed. Verifying on the live URL..."
python "$HERE/verify_live.py" "https://${PROJECT}.pages.dev" || true
