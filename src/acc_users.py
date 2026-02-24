"""
Autodesk Construction Cloud (ACC) - Project Users Export
Iterates through all projects in a hub and fetches users with their
roles, email, company, and products. Exports to CSV.
"""

import csv
import os
import sys
import time
from datetime import datetime

import requests
import auth
from auth import get_auth_headers, BASE_URL
from acc_hub_projects import get_hubs, get_projects


# Max retries for 429 rate-limited requests
MAX_RETRIES = 5

# Request timeout: (connect_timeout, read_timeout) in seconds
REQUEST_TIMEOUT = (5, 30)


def _strip_project_id(project_id):
    """Safely strip the 'b.' prefix from a project ID for the Admin API."""
    if project_id.startswith("b."):
        return project_id[2:]
    return project_id


def get_project_users(project_id):
    """
    Fetch all users for a given project using the ACC Admin API.
    Handles pagination, rate limiting (with max retries), and network errors.
    Returns a list of user dicts.
    """
    clean_id = _strip_project_id(project_id)
    url = f"{BASE_URL}/construction/admin/v1/projects/{clean_id}/users"

    all_users = []
    offset = 0
    limit = 100
    retries = 0

    while True:
        params = {"offset": offset, "limit": limit}

        try:
            response = requests.get(
                url, headers=get_auth_headers(), params=params, timeout=REQUEST_TIMEOUT
            )
        except requests.RequestException as e:
            print(f"    Request failed: {e}")
            return all_users

        if response.status_code == 429:
            retries += 1
            if retries > MAX_RETRIES:
                print(f"    Max retries ({MAX_RETRIES}) exceeded on 429. Skipping.")
                return all_users
            retry_after = int(response.headers.get("Retry-After", 5))
            print(f"    Rate limited (attempt {retries}/{MAX_RETRIES}). Waiting {retry_after}s...")
            time.sleep(retry_after)
            continue

        # Reset retry counter on successful non-429 response
        retries = 0

        if response.status_code != 200:
            print(f"    Error fetching users: {response.status_code} - {response.text[:200]}")
            return all_users

        data = response.json()
        users = data if isinstance(data, list) else data.get("results", [])
        all_users.extend(users)

        # Check if there are more pages
        if isinstance(data, dict):
            pagination = data.get("pagination", {})
            total = pagination.get("totalResults", 0)
            if offset + limit >= total:
                break
        else:
            break

        offset += limit

    return all_users


def _deduplicated(items):
    """Return a list with duplicates removed, preserving order."""
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def extract_user_row(user, project_name):
    """
    Extract a single CSV row from a user object.
    Combines multiple roles with ';' and multiple products with ';'.
    Deduplicates roles and products.
    """
    first_name = user.get("firstName", user.get("first_name", "N/A"))
    last_name = user.get("lastName", user.get("last_name", "N/A"))
    email = user.get("email", "N/A")
    company = user.get("companyName", user.get("company_name", "N/A"))

    # Roles: collect from 'roles' array or fallback to single 'roleName'
    role_names = []
    roles_list = user.get("roles", [])
    if roles_list:
        for r in roles_list:
            if isinstance(r, dict):
                name = r.get("name", r.get("roleName", ""))
                if name:
                    role_names.append(name)
    else:
        single_role = user.get("roleName", user.get("role_name", ""))
        if single_role:
            role_names.append(single_role)

    # Also check industry_roles
    industry_roles = user.get("industryRoles", user.get("industry_roles", []))
    if industry_roles:
        for ir in industry_roles:
            if isinstance(ir, str):
                role_names.append(ir)
            elif isinstance(ir, dict):
                ir_name = ir.get("name", "")
                if ir_name:
                    role_names.append(ir_name)

    role_names = _deduplicated(role_names)
    roles_str = ";".join(role_names) if role_names else "N/A"

    # Products: collect active product keys (deduplicated)
    product_keys = []
    products_list = user.get("products", [])
    for p in products_list:
        if isinstance(p, dict):
            access = p.get("access", "")
            if access and access.lower() != "none":
                key = p.get("key", "")
                if key:
                    product_keys.append(key)
        elif isinstance(p, str):
            product_keys.append(p)

    product_keys = _deduplicated(product_keys)
    products_str = ";".join(product_keys) if product_keys else "N/A"

    # Access level: derived from the accessLevels object (boolean flags)
    access_levels_obj = user.get("accessLevels", {})
    access_parts = []
    if access_levels_obj.get("accountAdmin"):
        access_parts.append("Account Administrator")
    if access_levels_obj.get("projectAdmin"):
        access_parts.append("Project Administrator")
    if access_levels_obj.get("executive"):
        access_parts.append("Executive")
    if access_levels_obj.get("accountStandardsAdministrator"):
        access_parts.append("Account Standards Administrator")
    if not access_parts:
        access_parts.append("Project Member")
    access_level = ";".join(access_parts)

    return [first_name, last_name, email, project_name, roles_str, company, products_str, access_level]


def fetch_all_users_for_hub(hub_id, hubs, project_name_filter=None):
    """Fetch users for every project in a hub (or one filtered project). Returns list of CSV rows."""
    # Find hub name
    hub_name = "unknown"
    for hub in hubs:
        if hub.get("id") == hub_id:
            hub_name = hub.get("attributes", {}).get("name", "unknown")
            break

    print(f"\nFetching projects for Hub: {hub_name} ({hub_id})...")
    projects = get_projects(hub_id)

    if not projects:
        print("No projects found.")
        return [], hub_name

    if project_name_filter:
        wanted = project_name_filter.strip().lower()
        filtered_projects = [
            p for p in projects
            if p.get("attributes", {}).get("name", "").strip().lower() == wanted
        ]
        if not filtered_projects:
            print(f"\nProject not found in hub '{hub_name}': {project_name_filter}")
            return [], hub_name
        projects = filtered_projects

    all_rows = []
    total_projects = len(projects)

    print(f"\nFetching users for {total_projects} projects...\n")

    for i, project in enumerate(projects, 1):
        project_id = project.get("id", "")
        project_name = project.get("attributes", {}).get("name", "N/A")
        print(f"  [{i}/{total_projects}] {project_name}...", end=" ")

        users = get_project_users(project_id)
        print(f"{len(users)} users")

        for user in users:
            row = extract_user_row(user, project_name)
            all_rows.append(row)

        # Small delay to avoid rate limiting
        if i < total_projects:
            time.sleep(0.3)

    return all_rows, hub_name


def export_users_to_csv(rows, hub_name="unknown"):
    """Export user data to a CSV file."""
    if not rows:
        print("No user data to export.")
        return None

    _project_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    output_dir = os.path.join(_project_root, "ACC_users")
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_hub_name = hub_name.replace(" ", "_").replace("/", "-")
    filename = os.path.join(output_dir, f"users_{safe_hub_name}_{timestamp}.csv")

    csv_headers = [
        "first_name",
        "last_name",
        "email",
        "project_name",
        "roles",
        "company",
        "products",
        "access_level",
    ]

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(csv_headers)
        writer.writerows(rows)

    full_path = os.path.abspath(filename)
    print(f"\n  CSV exported: {full_path}")
    print(f"  Total rows:   {len(rows)}")

    return filename


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Export all ACC project users to CSV.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and display counts, but do not write the output CSV",
    )
    parser.add_argument(
        "--project-name",
        default=None,
        help="Fetch users only from this exact project name",
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help="Environment (TST/AG) or hub key (e.g. Swissgrid_TST)",
    )
    args, extras = parser.parse_known_args()
    if extras:
        if args.target is None and len(extras) == 1:
            args.target = extras[0]
        else:
            parser.error(f"unrecognized arguments: {' '.join(extras)}")

    # Backward-compatible target resolution:
    # - TST / AG                        -> selects env and corresponding Swissgrid_<ENV> hub key
    # - Swissgrid_TST / Swissgrid_AG    -> uses that explicit hub key and infers env from suffix
    target = (args.target or "").strip()
    if not target:
        env = auth.ACC_ENV
        hub_key = auth.HUB_KEY
    elif target.upper() in {"TST", "AG"}:
        env = target.upper()
        hub_key = f"Swissgrid_{env}"
    elif target in {"Swissgrid_TST", "Swissgrid_AG"}:
        hub_key = target
        env = target.split("_")[-1].upper()
    else:
        print("Error: target must be TST, AG, Swissgrid_TST, or Swissgrid_AG")
        sys.exit(1)

    auth.set_acc_env(env)
    hub_id = os.getenv(hub_key, "")
    if not hub_id:
        print(f"Error: Hub key '{hub_key}' not found in .env")
        sys.exit(1)

    # Usage:
    #   python src\acc_users.py                                      -> uses current auth env default hub
    #   python src\acc_users.py TST                                  -> TST hub
    #   python src\acc_users.py AG                                   -> AG hub
    #   python src\acc_users.py --dry-run TST                        -> TST dry-run (no CSV write)
    #   python src\acc_users.py --dry-run AG                         -> AG dry-run (no CSV write)
    #   python src\acc_users.py TST --project-name "SAAA-ProvisionerAAA"             -> one project
    #   python src\acc_users.py --dry-run AG --project-name "TR1040_N00000680"       -> one project dry-run

    print(f"\nEnvironment: {auth.ACC_ENV} (hub: {hub_key})")
    if args.dry_run:
        print("  *** DRY-RUN MODE — no CSV will be written ***")
    print(f"\nFetching Hubs...")
    hubs = get_hubs()

    if hubs:
        rows, hub_name = fetch_all_users_for_hub(hub_id, hubs, project_name_filter=args.project_name)

        if rows:
            if args.dry_run:
                print(f"\nDry-run complete. Would export {len(rows)} rows for hub '{hub_name}'.")
            else:
                print("\nExporting users to CSV...")
                export_users_to_csv(rows, hub_name)
        else:
            print("\nNo users found across any projects.")
