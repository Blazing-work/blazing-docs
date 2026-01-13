# Branch Protection Setup

Configure these settings in **Settings > Branches > Add branch protection rule** for `main`:

## Required Settings

### Branch name pattern
```
main
```

### Protect matching branches

- [x] **Require a pull request before merging**
  - [x] Require approvals: `1`
  - [x] Dismiss stale pull request approvals when new commits are pushed
  - [x] Require approval of the most recent reviewable push

- [x] **Require status checks to pass before merging**
  - [x] Require branches to be up to date before merging
  - Required status checks:
    - `Lint`
    - `Validate Examples`
    - `Test Python 3.10`
    - `Test Python 3.11`
    - `Test Python 3.12`

- [x] **Require conversation resolution before merging**

- [ ] **Do not allow bypassing the above settings** (unchecked - see bypass list below)

### Allow bypass for

- [x] `BlazingWorkDev` (maintainer - can push directly to main)

### Optional (Recommended)

- [x] **Require signed commits** (if team uses GPG signing)
- [x] **Require linear history** (enforces squash or rebase merges)
- [ ] **Lock branch** (only for frozen releases)

## Quick Setup via GitHub CLI

```bash
# Set branch protection with BlazingWorkDev bypass
gh api repos/Blazing-work/blazing-examples/branches/main/protection -X PUT \
  -H "Accept: application/vnd.github+json" \
  --input - << 'EOF'
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["Lint", "Validate Examples", "Test Python 3.10", "Test Python 3.11", "Test Python 3.12"]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "required_approving_review_count": 1,
    "dismiss_stale_reviews": true,
    "bypass_pull_request_allowances": {
      "users": ["BlazingWorkDev"]
    }
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
EOF
```
