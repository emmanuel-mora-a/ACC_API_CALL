"""
Autodesk Construction Cloud (ACC) - User Provisioner
Reads a CSV of users and adds each user to the specified ACC project
with the correct roles, products, and access level (Member or Administrator).

Usage:
    python acc_provisioner.py <csv_file> [hub_env_key] [--dry-run]

    --dry-run : Run the full pipeline (CSV parse, project/role lookup,
                membership check) but skip the actual user import POST call.
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime

import requests
from auth import get_auth_headers, BASE_URL, HUB_KEY, HUB_ID, ACC_ENV, USER_ID
from acc_hub_projects import get_hubs, get_projects

ROLE_JSON_PATH = os.path.join(os.path.dirname(__file__), "data_acc", "role_id_acc.json")


REQUEST_TIMEOUT = (5, 30)
MAX_RETRIES = 5

# ---------------------------------------------------------------------------
# Access-level configurations
# ---------------------------------------------------------------------------

_ALL_PRODUCT_KEYS = [
    "projectAdministration", "docs", "build", "insight",
    "modelCoordination", "designCollaboration", "takeoff",
    "cost", "capitalPlanning", "buildingConnected", "forma",
]

_MEMBER_CORE = {"docs", "build", "insight", "modelCoordination"}
_ADMIN_CORE = {"projectAdministration", "docs", "build", "insight", "modelCoordination"}

MEMBER_PRODUCTS = [
    {"key": k, "access": "member" if k in _MEMBER_CORE else "none"}
    for k in _ALL_PRODUCT_KEYS
]

ADMIN_PRODUCTS = [
    {"key": k, "access": "administrator" if k in _ADMIN_CORE else "none"}
    for k in _ALL_PRODUCT_KEYS
]

MEMBER_ACCESS_LEVELS = {
    "accountAdmin": False,
    "projectAdmin": False,
    "executive": False,
    "accountStandardsAdministrator": False,
}

ADMIN_ACCESS_LEVELS = {
    "accountAdmin": False,
    "projectAdmin": True,
    "executive": False,
    "accountStandardsAdministrator": False,
}


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


def _api_post(url, json_body, extra_headers=None):
    """POST with timeout, retry on 429."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            headers = get_auth_headers()
            if extra_headers:
                headers.update(extra_headers)
            resp = requests.post(url, headers=headers, json=json_body, timeout=REQUEST_TIMEOUT)
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
# Role lookup from JSON file
# ---------------------------------------------------------------------------

def load_role_map_from_json(path=ROLE_JSON_PATH):
    """Load role name -> role ID mapping from the JSON file.
    Returns dict of lowercase_name -> role_id.
    """
    if not os.path.exists(path):
        print(f"  Warning: role JSON not found at {path}")
        return {}

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    role_map = {}
    for r in data.get("roles", []):
        name = r.get("name", "").strip().lower()
        rid = r.get("id", "")
        if name and rid:
            role_map[name] = rid
    return role_map


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
# Project users fetch (membership + company mapping)
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


# ---------------------------------------------------------------------------
# User import
# ---------------------------------------------------------------------------

def _is_admin(access_level):
    """Check if an access_level string means Administrator."""
    return "administrator" in access_level.strip().lower()


def import_user_to_project(project_id, email, role_ids, access_level, company_id=None):
    """
    Import (invite) a user to a project with roles, products, access level,
    and company. Returns (success: bool, error_message: str).
    """
    clean_id = _strip_id(project_id)
    url = f"{BASE_URL}/construction/admin/v1/projects/{clean_id}/users:import"

    is_admin = _is_admin(access_level)
    products = list(ADMIN_PRODUCTS if is_admin else MEMBER_PRODUCTS)
    access_levels = dict(ADMIN_ACCESS_LEVELS if is_admin else MEMBER_ACCESS_LEVELS)

    user_payload = {
        "email": email.strip().lower(),
        "products": products,
    }
    if role_ids:
        user_payload["roleIds"] = role_ids
    if company_id:
        user_payload["companyId"] = company_id

    body = {"users": [user_payload]}

    extra = {"x-user-id": USER_ID} if USER_ID else None
    resp, err = _api_post(url, body, extra_headers=extra)
    if err:
        return False, err

    if resp.status_code not in (200, 201, 202):
        return False, f"HTTP {resp.status_code}: {resp.text[:300]}"

    result = resp.json()
    if isinstance(result, dict):
        failures = result.get("failure", [])
        if failures:
            reason = failures[0].get("errors", [{}])[0].get("title", "unknown error")
            return False, reason

    return True, ""


# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------

def parse_csv(path):
    """Parse the input CSV into a list of row dicts."""
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for record in reader:
            roles_raw = record.get("roles", "").strip()
            roles = [r.strip() for r in roles_raw.split(";") if r.strip() and r.strip() != "N/A"]

            rows.append({
                "first_name": record.get("first_name", "").strip(),
                "last_name": record.get("last_name", "").strip(),
                "email": record.get("email", "").strip().lower(),
                "project_name": record.get("project_name", "").strip(),
                "roles": roles,
                "company": record.get("company", "").strip(),
                "access_level": record.get("access_level", "").strip(),
            })
    return rows


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def print_summary(added, skipped, failed):
    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)

    print(f"\n  Added: {len(added)}")
    for r in added:
        print(f"    + {r['email']} -> {r['project_name']}")

    print(f"\n  Skipped (already member): {len(skipped)}")
    for r in skipped:
        print(f"    - {r['email']} -> {r['project_name']}")

    print(f"\n  Failed: {len(failed)}")
    for r in failed:
        print(f"    x {r['email']} -> {r['project_name']} ({r['reason']})")

    print("=" * 70)


def main():
    parser = argparse.ArgumentParser( description="Provision ACC users from a CSV file.")
    parser.add_argument("csv_file", help="Path to the input CSV file")
    parser.add_argument("hub_env_key", nargs="?", default=HUB_KEY, help=f"Hub key from .env (default: {HUB_KEY})",)
    parser.add_argument("--dry-run", action="store_true",help="Validate everything but skip the actual user import API call",)
    args = parser.parse_args()

    csv_path = args.csv_file
    hub_key = args.hub_env_key
    dry_run = args.dry_run

    print(f"\n  Environment: {ACC_ENV} (hub: {hub_key})")

    if dry_run:
        print("  *** DRY-RUN MODE — no users will actually be imported ***")

    hub_id = os.getenv(hub_key, "")
    if not hub_id:
        print(f"Error: Hub key '{hub_key}' not found in .env")
        sys.exit(1)

    # --- Parse CSV ---
    print(f"\nLoading CSV: {csv_path}")
    rows = parse_csv(csv_path)
    print(f"  {len(rows)} rows loaded")

    # --- Load role map from JSON ---
    print(f"\nLoading role map from: {ROLE_JSON_PATH}")
    role_map = load_role_map_from_json()
    print(f"  {len(role_map)} roles loaded")

    # --- Fetch projects and build name -> ID map ---
    print(f"\nFetching projects for hub: {hub_key} ({hub_id})...")
    project_map = build_project_map(hub_id)
    print(f"  {len(project_map)} projects found")

    # --- Pre-fetch project users (members + companies) per project ---
    project_data_cache = {}  # project_id -> (member_set, company_map)

    unique_projects = set()
    for row in rows:
        unique_projects.add(row["project_name"].strip().lower())

    print(f"\nPre-fetching users for {len(unique_projects)} unique projects...")
    for proj_name in unique_projects:
        proj = project_map.get(proj_name)
        if not proj:
            continue
        pid = proj["id"]
        if pid not in project_data_cache:
            print(f"  Fetching users for: {proj['name']}...")
            member_set, company_map = fetch_project_users(pid)
            project_data_cache[pid] = (member_set, company_map)
            print(f"    {len(member_set)} members, {len(company_map)} companies")

    # --- Process rows ---
    added = []
    skipped = []
    failed = []
    seen = set()

    total = len(rows)
    print(f"\nProcessing {total} rows...\n")

    for i, row in enumerate(rows, 1):
        email = row["email"]
        project_name = row["project_name"]
        label = f"[{i}/{total}] {email} -> {project_name}"

        dedup_key = (email, project_name.lower())
        if dedup_key in seen:
            print(f"  {label} ... SKIPPED (duplicate row)")
            skipped.append({"email": email, "project_name": project_name, "reason": "duplicate row"})
            continue
        seen.add(dedup_key)

        # 1. Resolve project
        proj = project_map.get(project_name.strip().lower())
        if not proj:
            print(f"  {label} ... FAILED (project not found)")
            failed.append({"email": email, "project_name": project_name, "reason": "project not found"})
            continue

        project_id = proj["id"]
        member_set, company_map = project_data_cache.get(project_id, (set(), {}))

        # 2. Resolve roles from JSON (CSV has name, JSON maps name -> id)
        role_ids = []
        for role_name in row["roles"]:
            rid = role_map.get(role_name.strip().lower())
            if rid:
                role_ids.append(rid)

        unresolved_roles = [
            r for r in row["roles"]
            if r.strip().lower() not in role_map
        ]
        if unresolved_roles:
            print(f"    (!) Unresolved roles: {', '.join(unresolved_roles)}")

        # 3. Resolve companyId
        company = row["company"]
        company_id = company_map.get(company.strip().lower()) if company else None
        if company and not company_id:
            print(f"    (!) Company not found: {company}")

        # 4. Check membership
        if email in member_set:
            print(f"  {label} ... SKIPPED (already member)")
            skipped.append({"email": email, "project_name": project_name, "reason": "already member"})
            continue

        # 5. Import user (or simulate in dry-run)
        if dry_run:
            level = "Administrator" if _is_admin(row["access_level"]) else "Member"
            print(f"  {label} ... WOULD ADD (level={level}, roles={role_ids}, company={company_id or 'N/A'})")
            added.append({"email": email, "project_name": project_name})
        else:
            success, err_msg = import_user_to_project(
                project_id, email, role_ids, row["access_level"], company_id
            )

            if success:
                print(f"  {label} ... ADDED")
                added.append({"email": email, "project_name": project_name})
                member_set.add(email)
            else:
                print(f"  {label} ... FAILED ({err_msg})")
                failed.append({"email": email, "project_name": project_name, "reason": err_msg})

            time.sleep(0.3)

    # --- Summary ---
    print_summary(added, skipped, failed)
    if dry_run:
        print("  (dry-run: nothing was actually changed)\n")

    # --- Write report CSV ---
    mode_label = "dryrun" if dry_run else "report"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = f"provisioner_{mode_label}_{timestamp}.csv"
    with open(report_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["email", "project_name", "status", "reason"])
        for r in added:
            status = "would_add" if dry_run else "added"
            writer.writerow([r["email"], r["project_name"], status, ""])
        for r in skipped:
            writer.writerow([r["email"], r["project_name"], "skipped", r.get("reason", "")])
        for r in failed:
            writer.writerow([r["email"], r["project_name"], "failed", r["reason"]])

    print(f"\n  Report saved: {os.path.abspath(report_path)}")


if __name__ == "__main__":
    main()
