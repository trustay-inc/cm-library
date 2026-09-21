from __future__ import annotations

import os

import google.auth
from googleapiclient.discovery import build

SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"
OAUTH_CLIENT_FILE = os.environ.get("OAUTH_CLIENT_FILE", "credentials/oauth_client.json")
OAUTH_TOKEN_FILE = os.environ.get(
    "PRESENTER_ROTATION_TOKEN_FILE", "credentials/presenter_rotation_token.json"
)


def _credentials():
    if os.path.exists(OAUTH_CLIENT_FILE):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow

        credentials = None
        if os.path.exists(OAUTH_TOKEN_FILE):
            credentials = Credentials.from_authorized_user_file(
                OAUTH_TOKEN_FILE, [SHEETS_SCOPE]
            )
        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    OAUTH_CLIENT_FILE, [SHEETS_SCOPE]
                )
                credentials = flow.run_local_server(port=0)
            os.makedirs(os.path.dirname(OAUTH_TOKEN_FILE) or ".", exist_ok=True)
            with open(OAUTH_TOKEN_FILE, "w", encoding="utf-8") as handle:
                handle.write(credentials.to_json())
        return credentials

    credentials, _ = google.auth.default(scopes=[SHEETS_SCOPE])
    return credentials


def _records(values: list[list[str]]) -> list[dict]:
    if not values:
        return []
    headers = [header.strip() for header in values[0]]
    records = []
    for row in values[1:]:
        padded = row + [""] * (len(headers) - len(row))
        record = {headers[index]: padded[index].strip() for index in range(len(headers))}
        if any(record.values()):
            records.append(record)
    return records


def load_sheet_payload(sheet_id: str, cycle: dict) -> dict:
    service = build("sheets", "v4", credentials=_credentials(), cache_discovery=False)
    ranges = ["Employees!A:Z", "Deferrals!A:Z", "Completions!A:Z", "Assignments!A:Z", "Overrides!A:Z"]
    response = (
        service.spreadsheets()
        .values()
        .batchGet(spreadsheetId=sheet_id, ranges=ranges)
        .execute()
    )
    groups = response.get("valueRanges", [])
    while len(groups) < len(ranges):
        groups.append({"values": []})
    return {
        "cycle": cycle,
        "employees": _records(groups[0].get("values", [])),
        "deferrals": _records(groups[1].get("values", [])),
        "completions": _records(groups[2].get("values", [])),
        "assignments": _records(groups[3].get("values", [])),
        "overrides": _records(groups[4].get("values", [])),
    }
