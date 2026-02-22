"""
Unit tests for helper functions: _strip_id, deduplication, project map building.
No API calls — pure Python logic only.

Run:  python -m pytest _Tests/test_helpers.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from acc_provisioner import _strip_id


class TestStripId:
    def test_strips_b_prefix(self):
        assert _strip_id("b.abc-123") == "abc-123"

    def test_no_prefix_unchanged(self):
        assert _strip_id("abc-123") == "abc-123"

    def test_empty_string(self):
        assert _strip_id("") == ""

    def test_only_b_dot(self):
        assert _strip_id("b.") == ""

    def test_double_prefix_strips_once(self):
        assert _strip_id("b.b.nested") == "b.nested"


class TestDeduplication:
    """
    The provisioner uses a set of (email, project_name.lower()) to skip
    duplicate CSV rows. These tests verify the logic inline.
    """

    def test_same_email_same_project_is_duplicate(self):
        seen = set()
        key1 = ("user@example.com", "project a")
        key2 = ("user@example.com", "project a")
        seen.add(key1)
        assert key2 in seen

    def test_same_email_different_project_not_duplicate(self):
        seen = set()
        key1 = ("user@example.com", "project a")
        key2 = ("user@example.com", "project b")
        seen.add(key1)
        assert key2 not in seen

    def test_different_email_same_project_not_duplicate(self):
        seen = set()
        key1 = ("user1@example.com", "project a")
        key2 = ("user2@example.com", "project a")
        seen.add(key1)
        assert key2 not in seen

    def test_case_insensitive_project(self):
        seen = set()
        key1 = ("user@example.com", "project a")
        key2 = ("user@example.com", "Project A".lower())
        seen.add(key1)
        assert key2 in seen


class TestBuildProjectMap:
    """Test project map building with fake API response data."""

    def test_lowercase_keys(self):
        fake_projects = [
            {"id": "b.123", "attributes": {"name": "My Project"}},
            {"id": "b.456", "attributes": {"name": "UPPER CASE"}},
        ]
        project_map = {}
        for p in fake_projects:
            name = p.get("attributes", {}).get("name", "")
            pid = p.get("id", "")
            project_map[name.strip().lower()] = {"id": pid, "name": name}

        assert "my project" in project_map
        assert "upper case" in project_map
        assert "My Project" not in project_map

    def test_whitespace_stripped(self):
        fake_projects = [
            {"id": "b.789", "attributes": {"name": "  Spaced Name  "}},
        ]
        project_map = {}
        for p in fake_projects:
            name = p.get("attributes", {}).get("name", "")
            pid = p.get("id", "")
            project_map[name.strip().lower()] = {"id": pid, "name": name}

        assert "spaced name" in project_map

    def test_original_name_preserved(self):
        fake_projects = [
            {"id": "b.abc", "attributes": {"name": "Original Name"}},
        ]
        project_map = {}
        for p in fake_projects:
            name = p.get("attributes", {}).get("name", "")
            pid = p.get("id", "")
            project_map[name.strip().lower()] = {"id": pid, "name": name}

        assert project_map["original name"]["name"] == "Original Name"
        assert project_map["original name"]["id"] == "b.abc"
