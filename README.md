# Los Altos Permit Inspection Checker

This is a small command-line app that fetches the Los Altos permit inspection
scheduling page and scans the response for available inspection dates. It
compares those dates to your currently scheduled inspection date and reports
whether an earlier date is available.

## Usage (direct URL)

```bash
python check_inspection.py \
  --url "https://<los-altos-inspection-url>" \
  --current-date "2024-12-10"
```

You can also set the URL via environment variable:

```bash
export LOS_ALTOS_INSPECTION_URL="https://<los-altos-inspection-url>"
python check_inspection.py --current-date "2024-12-10"
```

## Usage (login flow)

The script can log in and open a specific permit from the dashboard. Provide the
permit ID and credentials via flags or environment variables.

```bash
export LOS_ALTOS_USERNAME="your-username"
export LOS_ALTOS_PASSWORD="your-password"
python check_inspection.py \
  --permit-id "BLD25-01440" \
  --current-date "2024-12-10"
```

Optional overrides if the login or dashboard URL changes:

```bash
python check_inspection.py \
  --permit-id "BLD25-01440" \
  --current-date "2024-12-10" \
  --login-url "https://trakit.losaltosca.gov/etrakit/login.aspx?lt=either&rd=~/dashboard.aspx" \
  --dashboard-url "https://trakit.losaltosca.gov/etrakit/dashboard.aspx"
```

### Optional headers

If the inspection page requires a specific header, add it with `--header`:

```bash
python check_inspection.py \
  --url "https://<los-altos-inspection-url>" \
  --current-date "2024-12-10" \
  --header "Accept: application/json"
```

## Notes

- The script detects dates in both `YYYY-MM-DD` and `MM/DD/YYYY` formats.
- If the page returns JSON, the script recursively scans the JSON payload for
  date strings.
- If the page returns HTML, the script scans visible text for date strings.
- The login flow uses best-effort form parsing; if the eTRAKiT login page
  changes, you may need to adjust the field detection logic.
