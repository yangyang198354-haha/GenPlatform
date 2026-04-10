#!/usr/bin/env bash
# =============================================================================
# Post-deployment smoke test
# Verifies that core API endpoints are functional after Docker deploy.
#
# Usage:
#   BASE_URL=http://47.109.197.217 bash smoke_test.sh
#   BASE_URL=http://localhost      bash smoke_test.sh
#
# Exit codes:
#   0 — all checks passed
#   1 — one or more checks failed
# =============================================================================
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost}"
SMOKE_EMAIL="smoke_$(date +%s)@test.internal"
SMOKE_PASS="SmokeTest123!"
PASS=0
FAIL=0

# ── helpers ───────────────────────────────────────────────────────────────

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}  PASS${NC}  $1"; ((PASS++)) || true; }
fail() { echo -e "${RED}  FAIL${NC}  $1 — $2"; ((FAIL++)) || true; }
info() { echo -e "${YELLOW}  ----${NC}  $1"; }

check_http() {
    local label="$1" url="$2" method="${3:-GET}" data="${4:-}" expected="${5:-200}"
    local args=(-s -o /dev/null -w "%{http_code}" -X "$method" -H "Content-Type: application/json")
    [ -n "$data"      ] && args+=(-d "$data")
    [ -n "$AUTH_HDR"  ] && args+=(-H "Authorization: Bearer $AUTH_HDR")
    local code
    code=$(curl "${args[@]}" "${BASE_URL}${url}" 2>/dev/null || echo "000")
    if [ "$code" = "$expected" ] || \
       ([ "$expected" = "2xx" ] && [[ "$code" =~ ^2 ]]); then
        pass "$label (HTTP $code)"
    else
        fail "$label" "expected $expected, got $code"
    fi
}

# ── global state ──────────────────────────────────────────────────────────
AUTH_HDR=""

# =============================================================================
echo ""
echo "======================================================================"
echo "  Smoke Test — ${BASE_URL}"
echo "======================================================================"

# SM-001  Health / reachability
info "SM-001: API reachability"
check_http "Login endpoint reachable" "/api/v1/auth/login/" POST \
    '{"email":"nobody@x.com","password":"wrong"}' 400

# SM-002  User registration
info "SM-002: User registration"
REG_RESP=$(curl -s -X POST \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"smokeuser\",\"email\":\"${SMOKE_EMAIL}\",\"password\":\"${SMOKE_PASS}\"}" \
    "${BASE_URL}/api/v1/auth/register/")
REG_CODE=$(echo "$REG_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print('ok')" 2>/dev/null && \
           curl -s -o /dev/null -w "%{http_code}" -X POST \
           -H "Content-Type: application/json" \
           -d "{\"username\":\"smokeuser\",\"email\":\"${SMOKE_EMAIL}\",\"password\":\"${SMOKE_PASS}\"}" \
           "${BASE_URL}/api/v1/auth/register/" || echo "000")
# Re-run cleanly
REG_HTTP=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"smokeuser\",\"email\":\"${SMOKE_EMAIL}\",\"password\":\"${SMOKE_PASS}\"}" \
    "${BASE_URL}/api/v1/auth/register/")
if [ "$REG_HTTP" = "201" ]; then
    pass "SM-002: Register new user (HTTP 201)"
else
    fail "SM-002: Register new user" "HTTP $REG_HTTP"
fi

# SM-003  Login and obtain JWT
info "SM-003: JWT login"
LOGIN_RESP=$(curl -s -X POST \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"${SMOKE_EMAIL}\",\"password\":\"${SMOKE_PASS}\"}" \
    "${BASE_URL}/api/v1/auth/login/")
ACCESS_TOKEN=$(echo "$LOGIN_RESP" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(d.get('access',''))" 2>/dev/null || echo "")
if [ -n "$ACCESS_TOKEN" ]; then
    pass "SM-003: Login returns JWT"
    AUTH_HDR="$ACCESS_TOKEN"
else
    fail "SM-003: Login returns JWT" "no access token in response"
fi

# SM-004  Protected endpoints with valid token
info "SM-004: Auth-protected endpoints"
check_http "SM-004a: GET /auth/profile/ with token"   "/api/v1/auth/profile/"  GET "" 200
check_http "SM-004b: GET /contents/ with token"        "/api/v1/contents/"      GET "" 200
check_http "SM-004c: GET /settings/services/ with token" "/api/v1/settings/services/" GET "" 200
check_http "SM-004d: GET /publisher/accounts/ with token" "/api/v1/publisher/accounts/" GET "" 200
check_http "SM-004e: GET /knowledge/documents/ with token" "/api/v1/knowledge/documents/" GET "" 200

# SM-005  Create + confirm content
info "SM-005: Content create and confirm"
CREATE_RESP=$(curl -s -X POST \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $AUTH_HDR" \
    -d '{"title":"Smoke Test","body":"Smoke test body content.","platform_type":"general","style":"professional"}' \
    "${BASE_URL}/api/v1/contents/")
CONTENT_ID=$(echo "$CREATE_RESP" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(d.get('id',''))" 2>/dev/null || echo "")
if [ -n "$CONTENT_ID" ]; then
    pass "SM-005a: Create content → id=$CONTENT_ID"
    CONFIRM_HTTP=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
        -H "Authorization: Bearer $AUTH_HDR" \
        "${BASE_URL}/api/v1/contents/${CONTENT_ID}/confirm/")
    if [ "$CONFIRM_HTTP" = "200" ]; then
        pass "SM-005b: Confirm content (HTTP 200)"
    else
        fail "SM-005b: Confirm content" "HTTP $CONFIRM_HTTP"
    fi
else
    fail "SM-005a: Create content" "no id in response: $CREATE_RESP"
fi

# SM-006  Publisher account binding
info "SM-006: Publisher account bind"
BIND_HTTP=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $AUTH_HDR" \
    -d '{"display_name":"Smoke Weibo","credentials":{"token":"fake"},"auth_type":"api_key"}' \
    "${BASE_URL}/api/v1/publisher/accounts/weibo/bind/")
if [ "$BIND_HTTP" = "201" ]; then
    pass "SM-006: Bind platform account (HTTP 201)"
else
    fail "SM-006: Bind platform account" "HTTP $BIND_HTTP"
fi

# SM-007  LLM generate endpoint (no API key — must return 400, not 500)
info "SM-007: LLM generate endpoint error handling"
check_http "SM-007: LLM generate without config → 400" \
    "/api/v1/llm/generate/?prompt=test&platform=general&style=professional" \
    GET "" 400

# SM-008  Media library
info "SM-008: Media library"
check_http "SM-008: GET /media/ with token" "/api/v1/media/" GET "" 200

# SM-009  Video projects
info "SM-009: Video projects"
check_http "SM-009: GET /video/projects/ with token" "/api/v1/video/projects/" GET "" 200

# SM-010  Static assets (frontend)
info "SM-010: Frontend static assets"
FRONTEND_HTTP=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/")
if [[ "$FRONTEND_HTTP" =~ ^(200|301|302)$ ]]; then
    pass "SM-010: Frontend root returns $FRONTEND_HTTP"
else
    fail "SM-010: Frontend root" "HTTP $FRONTEND_HTTP"
fi

# =============================================================================
echo ""
echo "======================================================================"
printf "  Results: ${GREEN}%d passed${NC}  ${RED}%d failed${NC}\n" "$PASS" "$FAIL"
echo "======================================================================"
echo ""

[ "$FAIL" -eq 0 ]
