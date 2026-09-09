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
#   2. Run:                 bash deploy.sh
#
# The token is read into the environment for the lifetime of this process only.

set -e

TOKEN_FILE="$HOME/.cf-token"
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

echo "==> Token loaded (${#CLOUDFLARE_API_TOKEN} chars, value not shown)"

echo "==> Building static site"
mkdir -p "$DIST"
cp "$HERE/widget.html" "$DIST/index.html"
[ -f "$HERE/widget_data.json" ] && cp "$HERE/widget_data.json" "$DIST/data.json"

echo "==> Deploying to Cloudflare Pages (free tier)"
npx -y wrangler pages deploy "$DIST" \
    --project-name "$PROJECT" \
    --commit-dirty=true

echo
echo "==> Deployed. Verifying OGL attribution on the live URL..."
python "$HERE/verify_live.py" "https://${PROJECT}.pages.dev" || true
