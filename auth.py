# Autodesk APS (formerly Forge) Authentication Configuration
# Automatically fetches and refreshes OAuth2 tokens using client credentials

import os
import time
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(override=True)

CLIENT_ID = os.getenv("APS_CLIENT_ID")
CLIENT_SECRET = os.getenv("APS_CLIENT_SECRET")

BASE_URL = "https://developer.api.autodesk.com"
TOKEN_URL = f"{BASE_URL}/authentication/v2/token"

# Token cache
_token_cache = {
    "access_token": None,
    "expires_at": 0  # Unix timestamp when the token expires
}


def _fetch_new_token():
    """Request a new 2-legged OAuth2 token using client credentials."""
    print("  [Auth] Requesting new access token...")

    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "scope": "data:read"
        },
        headers={
            "Content-Type": "application/x-www-form-urlencoded"
        }
    )

    if response.status_code != 200:
        raise Exception(f"Failed to get token: {response.status_code} - {response.text}")

    token_data = response.json()
    access_token = token_data["access_token"]
    expires_in = token_data.get("expires_in", 3600)  # default 1 hour

    # Cache the token with a 60-second safety buffer before actual expiry
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
        "Content-Type": "application/json"
    }
