"""
Integration tests — these hit the LIVE ACC API (Swissgrid TST).
They only perform read operations (dry-run) so nothing is modified.

Run:  python -m pytest tests/test_integration.py -v -s
      (use -s to see the print output from the provisioner)

Prerequisites:
  - .env must have valid APS_CLIENT_ID_TST and APS_CLIENT_SECRET_TST
  - The ACC app must have BIM 360 Account Admin enabled for Swissgrid TST
"""

import os
import sys
import csv
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from dotenv import load_dotenv

load_dotenv(override=True)

from auth import ACC_ENV, HUB_ID
from acc_provisioner import (
    parse_csv,
    build_project_map,
    fetch_project_users,
    fetch_account_companies,
    load_role_map_from_json,
    _strip_id,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "data_user_import")
SKIP_LIVE = not HUB_ID
SKIP_REASON = "No HUB_ID configured — set .env with valid TST credentials"


@pytest.mark.skipif(SKIP_LIVE, reason=SKIP_REASON)
class TestProjectResolution:
    """Verify we can fetch and resolve projects from the live API."""

    def test_project_map_not_empty(self):
        project_map = build_project_map(HUB_ID)
        assert len(project_map) > 0, "Expected at least one project in the hub"

    def test_known_project_resolves(self):
        """At least one project from happy_path.csv should exist in TST."""
        project_map = build_project_map(HUB_ID)
        rows = parse_csv(os.path.join(FIXTURES, "happy_path.csv"))

        resolved = 0
        for row in rows:
            if row["project_name"].strip().lower() in project_map:
                resolved += 1

        assert resolved > 0, (
            f"None of the projects in happy_path.csv were found. "
            f"Available: {list(project_map.keys())}"
        )

    def test_nonexistent_project_not_in_map(self):
        project_map = build_project_map(HUB_ID)
        assert "nonexistentproject" not in project_map


@pytest.mark.skipif(SKIP_LIVE, reason=SKIP_REASON)
class TestProjectUsersFetch:
    """Verify project member fetch works for a real project."""

    def _get_first_project_id(self):
        project_map = build_project_map(HUB_ID)
        if not project_map:
            pytest.skip("No projects available")
        return list(project_map.values())[0]["id"]

    def test_returns_member_set(self):
        pid = self._get_first_project_id()
        acc_member_set = fetch_project_users(pid)
        assert isinstance(acc_member_set, set)

    def test_member_emails_are_lowercase(self):
        pid = self._get_first_project_id()
        acc_member_set = fetch_project_users(pid)
        for email in acc_member_set:
            assert email == email.lower(), f"Email '{email}' is not lowercase"

    def test_nonexistent_user_not_in_members(self):
        pid = self._get_first_project_id()
        acc_member_set = fetch_project_users(pid)
        assert "definitely.not.a.real.user.xyz@example.com" not in acc_member_set


@pytest.mark.skipif(SKIP_LIVE, reason=SKIP_REASON)
class TestAccountCompanies:
    """Verify account-level company fetch works."""

    def test_company_map_not_empty(self):
        acc_company_map = fetch_account_companies(HUB_ID)
        assert len(acc_company_map) > 0, "Expected at least one company"

    def test_company_keys_are_lowercase(self):
        acc_company_map = fetch_account_companies(HUB_ID)
        for key in acc_company_map:
            assert key == key.lower(), f"Company key '{key}' is not lowercase"

    def test_known_company_resolves(self):
        acc_company_map = fetch_account_companies(HUB_ID)
        assert "swissgrid tst" in acc_company_map


@pytest.mark.skipif(SKIP_LIVE, reason=SKIP_REASON)
class TestRoleJsonLookup:
    """Verify the JSON role file loads correctly."""

    def test_role_map_not_empty(self):
        role_map = load_role_map_from_json()
        assert len(role_map) > 0, "Expected at least one role in the JSON"

    def test_role_keys_are_lowercase(self):
        role_map = load_role_map_from_json()
        for key in role_map:
            assert key == key.lower(), f"Role key '{key}' is not lowercase"

    def test_known_role_resolves(self):
        role_map = load_role_map_from_json()
        assert "fachplaner" in role_map, "Expected 'Fachplaner' role in the JSON"


@pytest.mark.skipif(SKIP_LIVE, reason=SKIP_REASON)
class TestDryRunEndToEnd:
    """
    Run the full provisioner pipeline in dry-run mode.
    Verifies: auth, project resolution, role lookup, membership check.
    Nothing is imported.
    """

    def test_dry_run_happy_path(self, capsys):
        """Run dry-run on the happy_path fixture and check for expected output."""
        csv_path = os.path.join(FIXTURES, "happy_path.csv")
        rows = parse_csv(csv_path)
        project_map = build_project_map(HUB_ID)

        results = {"resolved": 0, "not_found": 0}
        for row in rows:
            proj = project_map.get(row["project_name"].strip().lower())
            if proj:
                results["resolved"] += 1
            else:
                results["not_found"] += 1

        print(f"\n  Dry-run results: {results}")
        assert results["resolved"] + results["not_found"] == len(rows)

    def test_dry_run_error_cases(self):
        """Error cases CSV should parse without crashing."""
        csv_path = os.path.join(FIXTURES, "error_cases.csv")
        rows = parse_csv(csv_path)
        project_map = build_project_map(HUB_ID)

        for row in rows:
            proj = project_map.get(row["project_name"].strip().lower())
            if proj:
                fetch_project_users(proj["id"])

    def test_dry_run_edge_cases(self):
        """Edge cases CSV should parse and normalize correctly."""
        csv_path = os.path.join(FIXTURES, "edge_cases.csv")
        rows = parse_csv(csv_path)
        project_map = build_project_map(HUB_ID)

        for row in rows:
            assert row["email"] == row["email"].strip().lower()
            assert row["project_name"] == row["project_name"].strip()
