#happy_path.csv — The "everything is correct" baseline. Used by unit and integration tests to verify the app works when input is clean.

Row	Tests
Emmanuel → SAAA, Member	Normal user with one role
Christoph → SAAA, Member	Second user, same project, different role
Emmanuel → SCCC, Administrator	Same user in a different project with admin access



error_cases.csv — Intentionally broken data. Verifies the app doesn't crash on bad input.

Row	Tests
fake.user → NonExistentProject	Project doesn't exist → should fail gracefully
Empty email → SAAA	Missing email field → should parse as ""
no.roles → SAAA, no roles	Empty roles column → should parse as []
missing → SAAA, no access_level	Empty access_level → should parse as "" (defaults to Member)

edge_cases.csv — Tricky but valid data. Tests normalization and special handling.

Row  Tests
Emmanuel.Mora@Swissgrid.CH	Extra whitespace + uppercase email → should trim and lowercase
Same email again, clean	Duplicate of row 1 after normalization → dedup check
Fachplaner;Lieferant_Gebäudetechnik;FakeRole	Multiple roles with semicolons, one fake → splits correctly, warns about FakeRole
Roles = N/A	N/A value → should be filtered out, resulting in empty roles list


mock_import.csv — Designed for dry-run and live provisioning testing. Uses @example.com emails that don't exist in ACC.

Row	Tests
test.user1 → SAAA, Member	Normal member import with role
test.user2 → SAAA, Member	Different role in same project
test.admin1 → SAAA, Administrator	Admin access level (full products + projectAdmin flag)
test.user3 → SCCC, Member	Different project
test.admin2 → SCCC, Administrator	Admin in different project
test.multi → SAAA, two roles	Multiple roles separated by semicolon
test.norole → SAAA, no role	No role assigned → import without roleIds
test.badproject → NonExistent	Project not found → should log failure
test.user1 duplicate	Exact duplicate of row 1 → should be skipped