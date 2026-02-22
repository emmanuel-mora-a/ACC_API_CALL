# ACC API Calls

Python toolset for managing Autodesk Construction Cloud (ACC) projects and users via the Autodesk Platform Services (APS) APIs.

## What it does

| Script | Purpose |
|---|---|
| `src/acc_provisioner.py` | Bulk-import users into ACC projects from a CSV file (roles, products, company) |
| `src/acc_hub_projects.py` | List all hubs and projects, export project metadata to CSV |
| `src/acc_users.py` | Export all users across all projects in a hub to CSV |
| `src/auth.py` | OAuth2 token management with auto-refresh (2-legged client credentials) |

## Project structure

```
ACC_API_CALLS/
├── src/                        Python source code
│   ├── auth.py                     OAuth2 token management
│   ├── acc_provisioner.py          User provisioning (main script)
│   ├── acc_hub_projects.py         Hub & project listing / CSV export
│   └── acc_users.py                Project users export to CSV
├── ACC_roles/
│   └── role_id_acc.json            Role name → role ID mapping
├── ACC_Projects/                   Output: exported project CSVs
├── ACC_users/                      Output: exported user CSVs
├── DATA_user_import/               Input CSVs for provisioning
│   ├── FAKE_*.csv                      Test fixtures (fake emails)
│   └── (your real CSVs go here)
├── _Reports/                       Output: provisioning report CSVs
├── _Tests/                         Unit and integration tests
│   ├── test_helpers.py                 Pure logic tests (no API)
│   ├── test_parse_csv.py              CSV parsing tests (no API)
│   └── test_integration.py            Live API tests (read-only)
├── .env                            API credentials (not committed)
└── .gitignore
```

## Setup

### 1. Install dependencies

```bash
pip install requests python-dotenv pytest
```

### 2. Configure `.env`

Create a `.env` file in the project root with your APS credentials:

```env
# TST environment
APS_CLIENT_ID_TST=your_client_id
APS_CLIENT_SECRET_TST=your_client_secret
Swissgrid_TST=b.your-hub-id
APS_USER_ID_TST=your_autodesk_user_id

# AG (production) environment
APS_CLIENT_ID_AG=your_client_id
APS_CLIENT_SECRET_AG=your_client_secret
Swissgrid_AG=b.your-hub-id
```

- `APS_CLIENT_ID / SECRET` — OAuth2 app credentials from the APS Developer Portal
- `Swissgrid_TST / AG` — Hub ID (starts with `b.`)
- `APS_USER_ID_TST` — Your Autodesk user ID (required for the `x-user-id` header on the `users:import` endpoint)

### 3. Switch environments

Edit `ACC_ENV` in `src/auth.py`:

```python
ACC_ENV = "TST"   # or "AG" for production
```

All scripts automatically pick up the matching credentials.

## User provisioning

### CSV format

```csv
first_name,last_name,email,project_name,roles,company,access_level
Emmanuel,Mora,emmanuel.mora@swissgrid.ch,SAAA-ProvisionerAAA,Fachplaner;Lieferant_Bau,Swissgrid TST,Member
```

| Column | Description |
|---|---|
| `first_name`, `last_name` | User's name (informational, not sent to API) |
| `email` | User's email (auto-lowercased, trimmed) |
| `project_name` | ACC project name (case-insensitive match) |
| `roles` | Semicolon-separated role names; looked up in `ACC_roles/role_id_acc.json` |
| `company` | Company name; resolved to `companyId` from account-level companies |
| `access_level` | `Member` or `Administrator` — controls product access levels |

### Running the provisioner

```bash
# Dry-run (simulates everything, no actual imports)
python src\acc_provisioner.py DATA_user_import\FAKE_mock_import.csv --dry-run

# Production run (imports users for real)
python src\acc_provisioner.py DATA_user_import\your_file.csv

# Specify a different hub
python src\acc_provisioner.py DATA_user_import\your_file.csv Swissgrid_AG

# Different hub + dry-run
python src\acc_provisioner.py DATA_user_import\your_file.csv Swissgrid_AG --dry-run

# Show help
python src\acc_provisioner.py --help
```

### What the provisioner does (step by step)

1. **Parses the CSV** — normalizes emails (lowercase, trimmed), splits roles by `;`, filters out `N/A`
2. **Loads role map** — reads `ACC_roles/role_id_acc.json` to map role names to UUIDs
3. **Fetches all projects** — builds a name → ID lookup from the hub
4. **Fetches account companies** — builds a company name → ID lookup at the hub level
5. **Pre-fetches project members** — gets existing member emails per project (for skip detection)
6. **Processes each row:**
   - Deduplicates rows by `(email, project_name)`
   - Resolves project, roles, and company (warns on mismatches)
   - Skips users already in the project
   - Calls `POST /users:import` with the user payload (or simulates in dry-run)
7. **Prints a summary** and saves a report CSV to `_Reports/`

### Access levels

| CSV value | Products with access | `projectAdmin` flag |
|---|---|---|
| `Member` | docs, build, insight, modelCoordination (as `member`) | `false` |
| `Administrator` | projectAdministration, docs, build, insight, modelCoordination (as `administrator`) | `true` |

All other products (`designCollaboration`, `takeoff`, `cost`, `capitalPlanning`, `buildingConnected`, `forma`) default to `none` for both levels.

### Role mapping

Roles are resolved from `ACC_roles/role_id_acc.json`. The CSV contains human-readable role names (e.g. `Fachplaner`), and the JSON maps them to the UUID required by the API:

```json
{
  "roles": [
    { "id": "d6a1859e-...", "name": "Fachplaner" },
    { "id": "992903d7-...", "name": "Lieferant_Bau" }
  ]
}
```

If a role name from the CSV is not found in the JSON, a warning is printed but the import proceeds with the resolved roles.

### Company resolution

Companies are fetched at the **account level** (`GET /accounts/{id}/companies`), not per-project. This means the lookup works even when importing the first user of a company into a project. If the company name is not found, a warning is printed and the import proceeds without a `companyId`.

### Idempotency

Running the same CSV twice is safe. On the second run, all previously imported users are detected as "already member" and skipped.

## Other scripts

### List hubs and projects

```bash
python src\acc_hub_projects.py
```

Displays all hubs, prompts for a hub ID, lists projects, and exports to `ACC_Projects/`.

### Export all users

```bash
python src\acc_users.py
```

Iterates through every project in a hub, fetches all users with their roles, products, company, and access level, and exports to `ACC_users/`.

## Testing

```bash
# Run all tests
python -m pytest _Tests/ -v

# Run only unit tests (no API calls)
python -m pytest _Tests/test_helpers.py _Tests/test_parse_csv.py -v

# Run integration tests (hits live API, read-only)
python -m pytest _Tests/test_integration.py -v -s
```

### Test files

| File | What it tests | Requires API? |
|---|---|---|
| `test_helpers.py` | `_strip_id`, deduplication logic, project map building | No |
| `test_parse_csv.py` | CSV parsing, normalization, edge cases | No |
| `test_integration.py` | Project resolution, member fetch, company fetch, role lookup, dry-run end-to-end | Yes (read-only) |

### Test fixtures (`DATA_user_import/FAKE_*.csv`)

| File | Purpose |
|---|---|
| `FAKE_happy_path.csv` | Clean data — verifies the app works with correct input |
| `FAKE_error_cases.csv` | Broken data — missing emails, bad projects, empty fields |
| `FAKE_edge_cases.csv` | Tricky data — whitespace, case, duplicates, `N/A` roles, mixed valid/invalid roles |
| `FAKE_mock_import.csv` | Full provisioning test — multiple projects, roles, companies (including a fake one), duplicates |
| `FAKE_one_user.csv` | Single-user quick test |

## API endpoints used

| Endpoint | Method | Used by |
|---|---|---|
| `/authentication/v2/token` | POST | `auth.py` — get OAuth2 token |
| `/project/v1/hubs` | GET | `acc_hub_projects.py` — list hubs |
| `/project/v1/hubs/{id}/projects` | GET | `acc_hub_projects.py` — list projects |
| `/construction/admin/v1/accounts/{id}/companies` | GET | `acc_provisioner.py` — fetch account companies |
| `/construction/admin/v1/projects/{id}/users` | GET | `acc_provisioner.py`, `acc_users.py` — fetch project members |
| `/construction/admin/v1/projects/{id}/users:import` | POST | `acc_provisioner.py` — import users |

All endpoints use a 2-legged OAuth2 token. The `users:import` endpoint additionally requires the `x-user-id` header for admin impersonation.

## Rate limiting and error handling

- HTTP 429 responses are retried up to 5 times with the `Retry-After` delay
- Request timeouts: 5s connect, 30s read
- Network exceptions are caught and reported without crashing
- HTTP 202 (Accepted) is treated as success (async import job)
