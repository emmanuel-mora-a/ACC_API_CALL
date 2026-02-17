"""
Autodesk Construction Cloud (ACC) API Calls
Uses the Autodesk APS Data Management API to retrieve Hubs and Projects.
Exports project data to CSV.
"""

import csv
import os
from datetime import datetime

import requests
from auth import get_auth_headers, BASE_URL


def get_hubs():
    """Retrieve all hubs and display their IDs and names."""
    url = f"{BASE_URL}/project/v1/hubs"
    response = requests.get(url, headers=get_auth_headers())

    if response.status_code != 200:
        print(f"Error: {response.status_code} - {response.text}")
        return []

    data = response.json()
    hubs = data.get("data", [])

    if not hubs:
        print("No hubs found.")
        return []

    print("\n" + "=" * 70)
    print(f"  {'HUB NAME':<45} {'HUB ID'}")
    print("=" * 70)

    for hub in hubs:
        hub_id = hub.get("id", "N/A")
        hub_name = hub.get("attributes", {}).get("name", "N/A")
        print(f"  {hub_name:<45} {hub_id}")

    print("=" * 70)
    print(f"  Total Hubs: {len(hubs)}")
    print("=" * 70 + "\n")

    return hubs


def get_projects(hub_id):
    """Retrieve all projects for a given hub ID and display their details."""
    url = f"{BASE_URL}/project/v1/hubs/{hub_id}/projects"
    all_projects = []

    # Handle pagination
    while url:
        response = requests.get(url, headers=get_auth_headers())

        if response.status_code != 200:
            print(f"Error: {response.status_code} - {response.text}")
            return []

        data = response.json()
        projects = data.get("data", [])
        all_projects.extend(projects)

        # Check for next page
        url = data.get("links", {}).get("next", {}).get("href") if isinstance(
            data.get("links", {}).get("next"), dict
        ) else data.get("links", {}).get("next")

    if not all_projects:
        print(f"No projects found for hub: {hub_id}")
        return []

    print("\n" + "=" * 90)
    print(f"  {'PROJECT NAME':<50} {'PROJECT ID'}")
    print("=" * 90)

    for project in all_projects:
        project_id = project.get("id", "N/A")
        project_name = project.get("attributes", {}).get("name", "N/A")
        print(f"  {project_name:<50} {project_id}")

    print("=" * 90)
    print(f"  Total Projects: {len(all_projects)}")
    print("=" * 90 + "\n")

    return all_projects


def export_projects_to_csv(projects, hub_name="unknown"):
    """Export project data to a CSV file with rich metadata."""
    if not projects:
        print("No projects to export.")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_hub_name = hub_name.replace(" ", "_").replace("/", "-")
    filename = f"projects_{safe_hub_name}_{timestamp}.csv"

    csv_headers = [
        "Project Name",
        "Project ID",
        "Project Type",
        "Extension Type",
        "Extension Version",
        "Hub ID",
        "Root Folder ID",
        "Self Link",
        "Web View Link",
    ]

    rows = []
    for project in projects:
        attrs = project.get("attributes", {})
        ext = attrs.get("extension", {})
        relationships = project.get("relationships", {})
        links = project.get("links", {})

        # Extract root folder ID from relationships
        root_folder_data = relationships.get("rootFolder", {}).get("data", {})
        root_folder_id = root_folder_data.get("id", "N/A") if root_folder_data else "N/A"

        # Extract hub ID from relationships
        hub_data = relationships.get("hub", {}).get("data", {})
        hub_id = hub_data.get("id", "N/A") if hub_data else "N/A"

        rows.append([
            attrs.get("name", "N/A"),
            project.get("id", "N/A"),
            ext.get("data", {}).get("projectType", "N/A"),
            ext.get("type", "N/A"),
            ext.get("version", "N/A"),
            hub_id,
            root_folder_id,
            links.get("self", {}).get("href", "N/A") if isinstance(links.get("self"), dict) else links.get("self", "N/A"),
            links.get("webView", {}).get("href", "N/A") if isinstance(links.get("webView"), dict) else links.get("webView", "N/A"),
        ])

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(csv_headers)
        writer.writerows(rows)

    full_path = os.path.abspath(filename)
    print(f"  CSV exported: {full_path}")
    print(f"  Total rows:   {len(rows)}")

    return filename


if __name__ == "__main__":
    # Step 1: Get all Hubs
    print("\nFetching Hubs...")
    hubs = get_hubs()

    
    if hubs:
        # Step 2: Prompt user to select a Hub ID for project listing
        default_hub = os.getenv("Swissgrid_TST", "")
        hub_id_input = input(f"Enter a Hub ID from above to list its projects [{default_hub}]: ").strip() or default_hub

        if hub_id_input:
            # Find the hub name for the CSV filename
            hub_name = "unknown"
            for hub in hubs:
                if hub.get("id") == hub_id_input:
                    hub_name = hub.get("attributes", {}).get("name", "unknown")
                    break

            print(f"\nFetching Projects for Hub: {hub_name} ({hub_id_input})...")
            projects = get_projects(hub_id_input)

            if projects:
                print("\nExporting projects to CSV...")
                export_projects_to_csv(projects, hub_name)
        else:
            print("No Hub ID entered. Exiting.")
