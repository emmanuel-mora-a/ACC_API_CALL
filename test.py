"""
Autodesk Construction Cloud (ACC) - User Provisioner
Reads a CSV of users and adds each user to the specified ACC project
with the correct roles, products (docs + build), and access level.

Usage:
    python acc_provisioner.py <csv_file> [hub_env_key] [--dry-run]

    --dry-run : Run the full pipeline (CSV parse, project/role lookup,
                membership check) but skip the actual user import POST call.
"""

import argparse
import csv
import os
import sys
import time
from datetime import datetime

import requests
from auth import get_auth_headers, BASE_URL, HUB_KEY, HUB_ID, ACC_ENV
from acc_hub_projects import get_hubs, get_projects


REQUEST_TIMEOUT = (5, 30)
MAX_RETRIES = 5

DEFAULT_PRODUCTS = [
    {"key": "docs", "access": "member"},
    {"key": "build", "access": "member"},
]


# ---------------------------------------------------------------------------
# ACC API helpers
# ---------------------------------------------------------------------------

def _strip_id(project_id):
    return project_id[2:] if project_id.startswith("b.") else project_id


def _api_get(url, params=None):
    """GET with timeout, retry on 429."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=get_auth_headers(), params=params, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as e:
            return None, str(e)

        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", 5))
            if attempt < MAX_RETRIES:
                time.sleep(wait)
                continue
            return None, "rate limited after max retries"

        return resp, None

    return None, "exhausted retries"


def _api_post(url, json_body):
    """POST with timeout, retry on 429."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.post(url, headers=get_auth_headers(), json=json_body, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as e:
            return None, str(e)

        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", 5))
            if attempt < MAX_RETRIES:
                time.sleep(wait)
                continue
            return None, "rate limited after max retries"

        return resp, None

    return None, "exhausted retries"


# ---------------------------------------------------------------------------
# Project resolution
# ---------------------------------------------------------------------------

def build_project_map(hub_id):
    """Fetch all projects and return a dict of lowercase_name -> {id, name}."""
    projects = get_projects(hub_id)
    project_map = {}
    for p in projects:
        name = p.get("attributes", {}).get("name", "")
        pid = p.get("id", "")
        project_map[name.strip().lower()] = {"id": pid, "name": name}
    return project_map


# ---------------------------------------------------------------------------
# Project users fetch (roles + membership in one pass)
# ---------------------------------------------------------------------------

def fetch_project_users(project_id):
    """
    Fetch all users for a project. Returns:
      - member_set:   set of lowercase emails already in the project
      - company_map:  dict of lowercase_company_name -> companyId
    """
    clean_id = _strip_id(project_id)
    url = f"{BASE_URL}/construction/admin/v1/projects/{clean_id}/users"

    member_set = set()
    company_map = {}
    offset = 0
    limit = 100

    while True:
        resp, err = _api_get(url, params={"offset": offset, "limit": limit})
        if err or resp.status_code != 200:
            break

        data = resp.json()
        users = data if isinstance(data, list) else data.get("results", [])

        for u in users:
            email = u.get("email", "").strip().lower()
            if email:
                member_set.add(email)

            comp_name = u.get("companyName", "")
            comp_id = u.get("companyId", "")
            if comp_name and comp_id:
                company_map[comp_name.strip().lower()] = comp_id

        if isinstance(data, dict):
            total = data.get("pagination", {}).get("totalResults", 0)
            if offset + limit >= total:
                break
        else:
            break

        offset += limit

    return member_set, company_map


if __name__ == "__main__":
    print(f"Environment: {ACC_ENV}, Hub: {HUB_KEY} ({HUB_ID})\n")

    project_map = build_project_map(HUB_ID)
    if not project_map:
        print("No projects found.")
        sys.exit(1)

    target = project_map.get("saaa-provisioneraaa")
    if not target:
        print("Project SAAA-ProvisionerAAA not found!")
        sys.exit(1)

    print(f"\nTesting fetch_project_users on: {target['name']} ({target['id']})\n")

    acc_member_set = fetch_project_users(target["id"])
    print("Members:", acc_member_set)