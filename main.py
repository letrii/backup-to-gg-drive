import shutil
import json
import os

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from datetime import datetime, timedelta

SCOPES = ["https://www.googleapis.com/auth/drive"]

dir_path = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(dir_path, 'config.json')) as f:
    config = json.load(f)


def get_credentials():
    token_path = os.path.join(dir_path, "token.json")
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                os.path.join(dir_path, "oauth_credentials.json"), SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as token:
            token.write(creds.to_json())
    return creds


def handler(service, folder_name, folder_path):
    current_date = datetime.now()
    filename = f"{config['parent_folder_name']}-{folder_name}-{current_date.strftime('%d-%m')}"
    shutil.make_archive(filename, "zip", folder_path)

    # upload file
    file_metadata = {
        "name": f"{filename}.zip",
        "mimeType": "application/zip",
        "parents": [config["folder_id"]]
    }
    media = MediaFileUpload(f"{filename}.zip", mimetype="application/zip", resumable=True)
    file = service.files().create(body=file_metadata, media_body=media, fields="id", supportsAllDrives=True).execute()

    file_path = os.path.join(dir_path, filename + ".zip")
    if os.path.isfile(file_path):
        os.remove(file_path)

    # List all files
    results = service.files().list().execute()
    items = results.get("files", [])
    previous_date = current_date + timedelta(days=config["keep_date"])
    old_file_name = f"{config['parent_folder_name']}-{folder_name}-{previous_date.strftime('%d-%m')}"
    for item in items:
        drive_file = item["name"]
        if old_file_name in drive_file:
            file_id = item["id"]
            service.files().delete(fileId=file_id).execute()
            old_file = os.path.join(dir_path, drive_file + ".zip")
            if os.path.isfile(old_file):
                os.remove(old_file)


if __name__ == "__main__":
    service = build("drive", "v3", credentials=get_credentials())
    for info in config["folders"]:
        handler(service, info["folder_name"], info["folder_path"])
