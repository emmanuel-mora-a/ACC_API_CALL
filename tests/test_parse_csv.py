"""
Unit tests for CSV parsing and data normalization.
No API calls — pure Python logic only.

Run:  python -m pytest tests/test_parse_csv.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from acc_provisioner import parse_csv

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


class TestParseHappyPath:
    def test_row_count(self):
        rows = parse_csv(os.path.join(FIXTURES, "happy_path.csv"))
        assert len(rows) == 3

    def test_email_lowercase(self):
        rows = parse_csv(os.path.join(FIXTURES, "happy_path.csv"))
        for row in rows:
            assert row["email"] == row["email"].lower()

    def test_fields_present(self):
        rows = parse_csv(os.path.join(FIXTURES, "happy_path.csv"))
        expected_keys = {"first_name", "last_name", "email", "project_name", "roles", "company", "access_level"}
        for row in rows:
            assert set(row.keys()) == expected_keys

    def test_roles_parsed_as_list(self):
        rows = parse_csv(os.path.join(FIXTURES, "happy_path.csv"))
        for row in rows:
            assert isinstance(row["roles"], list)

    def test_access_level_values(self):
        rows = parse_csv(os.path.join(FIXTURES, "happy_path.csv"))
        assert rows[0]["access_level"] == "Project Member"
        assert rows[2]["access_level"] == "Project Administrator"


class TestParseEdgeCases:
    def test_email_trimmed_and_lowered(self):
        """Whitespace around email should be stripped, case lowered."""
        rows = parse_csv(os.path.join(FIXTURES, "edge_cases.csv"))
        assert rows[0]["email"] == "emmanuel.mora@swissgrid.ch"

    def test_project_name_trimmed(self):
        """Whitespace around project_name should be stripped."""
        rows = parse_csv(os.path.join(FIXTURES, "edge_cases.csv"))
        assert rows[0]["project_name"] == "SAAA-ProvisionerAAA"

    def test_duplicate_rows_both_parsed(self):
        """parse_csv does not deduplicate — that's the orchestrator's job."""
        rows = parse_csv(os.path.join(FIXTURES, "edge_cases.csv"))
        emails = [r["email"] for r in rows]
        assert emails.count("emmanuel.mora@swissgrid.ch") == 2

    def test_multiple_roles_split(self):
        """Semicolon-separated roles should be split into a list."""
        rows = parse_csv(os.path.join(FIXTURES, "edge_cases.csv"))
        multi_role_row = rows[2]
        assert len(multi_role_row["roles"]) == 3
        assert "Fachplaner" in multi_role_row["roles"]
        assert "Lieferant_Gebäudetechnik" in multi_role_row["roles"]
        assert "FakeRole" in multi_role_row["roles"]

    def test_na_roles_filtered(self):
        """Roles with value 'N/A' should be excluded."""
        rows = parse_csv(os.path.join(FIXTURES, "edge_cases.csv"))
        na_row = rows[3]
        assert na_row["roles"] == []


class TestParseErrorCases:
    def test_nonexistent_project_still_parses(self):
        """Bad project names are parsed — resolution happens later."""
        rows = parse_csv(os.path.join(FIXTURES, "error_cases.csv"))
        assert rows[0]["project_name"] == "NonExistentProject"

    def test_empty_email_parsed_as_empty(self):
        rows = parse_csv(os.path.join(FIXTURES, "error_cases.csv"))
        assert rows[1]["email"] == ""

    def test_empty_roles_parsed_as_empty_list(self):
        rows = parse_csv(os.path.join(FIXTURES, "error_cases.csv"))
        assert rows[2]["roles"] == []

    def test_missing_access_level_is_empty_string(self):
        rows = parse_csv(os.path.join(FIXTURES, "error_cases.csv"))
        assert rows[3]["access_level"] == ""
