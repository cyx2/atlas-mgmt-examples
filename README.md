# MongoDB Atlas Management Tools

A collection of Python scripts for managing MongoDB Atlas organizations, projects, clusters, and users. These tools automate common administrative tasks, optimize resource usage, and maintain clean Atlas environments. These scripts serve as examples of API usage and need to be customized and hardened for production use. They are also not officially supported by MongoDB.

## Quick Start

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your Atlas API credentials
   ```

3. **Run any tool:**
   ```bash
   python <script_name>.py --help
   ```

## Scripts Overview

### Resource Management
| Script | Purpose | Key Features |
|--------|---------|-------------|
| `provision_projects_for_users.py` | Project & cluster automation | Bulk provisioning, user invites, M0 clusters, multiple actions |
| `delete_empty_projects_in_organization.py` | Resource optimization | Find and remove projects with no clusters, dry-run mode |
| `delete_all_clusters_in_organization.py` | Cluster management | Organization-wide cluster deletion with safety prompts |
| `pause_all_clusters_in_organization.py` | Cost management | Pause all clusters across organization for temporary shutdown |

### User & Access Management  
| Script | Purpose | Key Features |
|--------|---------|-------------|
| `invite_users_to_organization.py` | User management | Bulk user invitations with role assignments |
| `cleanup_aged_projects_and_clusters.py` | Legacy cleanup | Remove users from old projects (90+ days), cluster deletion (120+ days) |

## Detailed Script Information

### provision_projects_for_users.py
**Purpose:** Comprehensive project and cluster lifecycle management
- **Actions:** provision, delete-clusters, delete-projects, delete-all-clusters, delete-all-projects
- **Usage:** `python provision_projects_for_users.py --action <action> [--emails email1 email2 ...]`
- **Features:** Automated M0 cluster creation, user invitations, bulk operations

### cleanup_aged_projects_and_clusters.py  
**Purpose:** Automated cleanup of aged Atlas resources
- **Age Thresholds:** 90 days (users), 120 days (clusters)
- **Usage:** `python cleanup_aged_projects_and_clusters.py`
- **Operations:** User removal, cluster deletion, invitation cleanup

### delete_empty_projects_in_organization.py
**Purpose:** Identify and remove projects with no clusters
- **Usage:** `python delete_empty_projects_in_organization.py [--dry-run] [--auto-confirm]`
- **Safety:** Built-in dry-run mode for safe preview

### delete_all_clusters_in_organization.py
**Purpose:** Organization-wide cluster deletion
- **Usage:** `python delete_all_clusters_in_organization.py`
- **Safety:** Multiple confirmation prompts before destructive operations

### invite_users_to_organization.py
**Purpose:** Bulk user invitation management
- **Usage:** `python invite_users_to_organization.py`
- **Features:** Role-based invitations, batch processing

### pause_all_clusters_in_organization.py
**Purpose:** Pause all clusters across an organization
- **Usage:** `python pause_all_clusters_in_organization.py`
- **Features:** Organization-wide cluster pausing, cost management, temporary environment shutdown

## Prerequisites

- **Python 3.6+** 
- **Required packages:** `requests`, `python-dotenv`
- **Test dependencies:** `pytest`, `pytest-cov` (for running tests)
- **Valid Organization-level Atlas API credentials** with appropriate permissions

## Environment Setup

### 1. Configure Environment Variables
Copy `.env.example` to `.env` and configure with your Atlas credentials:

```bash
# MongoDB Atlas API Credentials
ATLAS_PUBLIC_KEY=your_atlas_public_key
ATLAS_PRIVATE_KEY=your_atlas_private_key  
ATLAS_ORG_ID=your_organization_id

# Optional Configuration
ATLAS_API_BASE_URL=https://cloud.mongodb.com/api/atlas/v2
LOG_LEVEL=INFO
LOG_DIR=logs
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

This will install both runtime dependencies (`requests`, `python-dotenv`) and test dependencies (`pytest`, `pytest-cov`).

## Testing

The project includes a comprehensive test suite using pytest. All scripts have corresponding test files in the `tests/` directory.

### Running Tests

```bash
# Run all tests
pytest

# Run tests with coverage report
pytest --cov=. --cov-report=html

# Run a specific test file
pytest tests/test_provision_projects_for_users.py

# Run tests in verbose mode
pytest -v
```

### Test Configuration

Test configuration is managed via `pytest.ini`:
- Test discovery: `tests/` directory
- Test pattern: `test_*.py` files
- Verbose output by default
- Shared fixtures available in `tests/conftest.py`

### Test Features

- **Mocked API calls** - Tests use mocked HTTP responses to avoid real API calls
- **Isolated test environment** - Each test runs in isolation with fresh module imports
- **Environment variable mocking** - Tests use mock credentials without requiring real `.env` files
- **Comprehensive coverage** - Tests cover all major scripts and their core functionality

## Logging & Reports

All scripts automatically generate detailed logs and reports in the `logs/` directory:

- **`*.log`** - Detailed operation logs with timestamps and status
- **`*.json`** - Structured reports with operation results and metadata
- **Real-time console output** - Progress updates and status information

## Common Usage Patterns

### Safe Operations (Recommended)
```bash
# Preview what would be deleted (no actual changes)
python delete_empty_projects_in_organization.py --dry-run

# Run with confirmation prompts
python delete_all_clusters_in_organization.py
```

### Bulk Operations
```bash
# Provision projects for multiple users
python provision_projects_for_users.py --action provision --emails user1@example.com user2@example.com

# Clean up aged resources automatically
python cleanup_aged_projects_and_clusters.py
```

## Safety & Best Practices

⚠️ **CRITICAL SAFETY WARNINGS** ⚠️

These tools perform **DESTRUCTIVE OPERATIONS** that cannot be undone:

### Before Running Any Script:
1. **Test in non-production environments first**
2. **Use `--dry-run` modes when available** 
3. **Review generated logs** before confirming operations
4. **Maintain backups** of critical Atlas configurations
5. **Verify credentials** point to the correct organization

### Safety Features Built-In:
- **Confirmation prompts** for destructive operations
- **Dry-run modes** for safe preview  
- **Detailed logging** for audit trails
- **Error handling** with graceful failures
- **API rate limiting** to prevent service disruption

### Recovery Considerations:
- **Projects:** Can be recreated but lose all configuration history
- **Clusters:** Cannot be recovered once deleted - data loss is permanent
- **Users:** Can be re-invited but lose project-specific permissions
- **API Keys:** May be affected by user removal

## Troubleshooting

### Common Issues:
- **Authentication errors:** Verify API keys and organization ID
- **Permission denied:** Ensure API keys have required Atlas permissions
- **Rate limiting:** Scripts include automatic retry logic
- **Network timeouts:** Check internet connection and Atlas API status

### Support:
- These scripts serve as examples of API usage and need to be customized and hardened for production use
- These scripts are not officially supported by MongoDB