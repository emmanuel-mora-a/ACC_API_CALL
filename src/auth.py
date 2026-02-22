# Autodesk APS (formerly Forge) Authentication Configuration
# Automatically fetches and refreshes OAuth2 tokens using client credentials.
#
# Environment selection:
#   ACC_ENV = "TST"  (default)  ->  uses APS_CLIENT_ID_TST / APS_CLIENT_SECRET_TST / Swissgrid_TST
#   ACC_ENV = "AG"              ->  uses APS_CLIENT_ID_AG  / APS_CLIENT_SECRET_AG  / Swissgrid_AG

import os
import time
import requests
from dotenv import load_dotenv

_PROJECT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"), override=True)

# --- Environment selection (change this one value to switch) ---
ACC_ENV = "TST"

CLIENT_ID = os.getenv(f"APS_CLIENT_ID_{ACC_ENV}")
CLIENT_SECRET = os.getenv(f"APS_CLIENT_SECRET_{ACC_ENV}")
USER_ID = os.getenv(f"APS_USER_ID_{ACC_ENV}", "")
HUB_KEY = f"Swissgrid_{ACC_ENV}"
HUB_ID = os.getenv(HUB_KEY, "")

BASE_URL = "https://developer.api.autodesk.com"
TOKEN_URL = f"{BASE_URL}/authentication/v2/token"

_token_cache = {
    "access_token": None,
    "expires_at": 0,
}


def _fetch_new_token():
    """Request a new 2-legged OAuth2 token using client credentials."""
    print(f"  [Auth] Requesting new access token (env={ACC_ENV})...")

    if not CLIENT_ID or not CLIENT_SECRET:
        raise Exception(
            f"Missing credentials: APS_CLIENT_ID_{ACC_ENV} or APS_CLIENT_SECRET_{ACC_ENV} not set in .env"
        )

    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "scope": "data:read account:read account:write",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    if response.status_code != 200:
        raise Exception(f"Failed to get token: {response.status_code} - {response.text}")

    token_data = response.json()
    access_token = token_data["access_token"]
    expires_in = token_data.get("expires_in", 3600)

    _token_cache["access_token"] = access_token
    _token_cache["expires_at"] = time.time() + expires_in - 60

    print(f"  [Auth] Token acquired (expires in {expires_in // 60} minutes)")
    return access_token


def get_access_token():
    """Return a valid access token, refreshing automatically if expired."""
    if _token_cache["access_token"] and time.time() < _token_cache["expires_at"]:
        return _token_cache["access_token"]
    return _fetch_new_token()


def get_auth_headers():
    """Return the authorization headers for API calls."""
    return {
        "Authorization": f"Bearer {get_access_token()}",
        "Content-Type": "application/json",
    }
