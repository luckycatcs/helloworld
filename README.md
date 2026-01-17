# Los Altos Permit Inspection Checker

This is a small command-line app that logs into the Los Altos eTRAKiT portal,
opens a specific permit, and scans the response for available inspection dates.
It compares those dates to your currently scheduled inspection date and reports
whether an earlier date is available.

## Setup

Set the credentials in your environment (do not hardcode secrets):

```bash
export LOS_ALTOS_USERNAME="your-username"
export LOS_ALTOS_PASSWORD="your-password"
```

## Run

```bash
python check_inspection.py
```

## Configuration

Edit these constants in `check_inspection.py` to change the behavior:

- `LOGIN_URL`
- `DASHBOARD_URL`
- `PERMIT_ID`
- `CURRENT_DATE`

## Notes

- The script detects dates in both `YYYY-MM-DD` and `MM/DD/YYYY` formats.
- If the page returns JSON, the script recursively scans the JSON payload for
  date strings.
- If the page returns HTML, the script scans visible text for date strings.
- The login flow uses best-effort form parsing; if the eTRAKiT login page
  changes, you may need to adjust the field detection logic.
