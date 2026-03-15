from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore[import]
import json

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)

creds = flow.run_console()

data = {
    "token": creds.token,
    "refresh_token": creds.refresh_token,
    "token_uri": creds.token_uri,
    "client_id": creds.client_id,
    "client_secret": creds.client_secret,
    "scopes": SCOPES,
}

with open("authorized_user.json", "w") as f:
    json.dump(data, f, indent=2)

print("✅ Сохранено в authorized_user.json")
