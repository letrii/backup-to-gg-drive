import json
import os
import yaml
import zipfile

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


def get_target_paths(folder_path, include_paths=None):
    if include_paths is not None:
        result = []
        for p in include_paths:
            full = os.path.join(folder_path, p)
            if os.path.isfile(full):
                result.append((full, p, True))
            elif os.path.isdir(full):
                result.append((full, p, False))
        return result

    compose_path = os.path.join(folder_path, "docker-compose.yml")
    if os.path.exists(compose_path):
        with open(compose_path) as f:
            compose = yaml.safe_load(f)
        seen = []
        for service in (compose.get("services") or {}).values():
            for vol in (service.get("volumes") or []):
                raw = vol if isinstance(vol, str) else vol.get("source", "")
                if not raw.startswith("./"):
                    continue
                local = raw.split(":")[0][2:].strip("/").split("/")[0]
                if local and local not in seen:
                    seen.append(local)
        return [
            (os.path.join(folder_path, p), p, False)
            for p in seen
            if os.path.exists(os.path.join(folder_path, p))
        ]

    return [(folder_path, "", False)]


def handler(service, folder_name, folder_path, include_paths=None):
    current_date = datetime.now()
    filename = f"{config['parent_folder_name']}-{folder_name}-{current_date.strftime('%d-%m')}"
    zip_path = filename + ".zip"
    targets = get_target_paths(folder_path, include_paths)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for src, prefix, is_file in targets:
            if is_file:
                try:
                    zf.write(src, prefix)
                except (UnicodeEncodeError, OSError) as e:
                    print("Skipped: %r - %s" % (src, e))
            else:
                for root, dirs, files in os.walk(src):
                    for file in files:
                        file_full = os.path.join(root, file)
                        try:
                            rel = os.path.relpath(file_full, src)
                            arcname = os.path.join(prefix, rel) if prefix else rel
                            zf.write(file_full, arcname)
                        except (UnicodeEncodeError, OSError) as e:
                            print("Skipped: %r - %s" % (file_full, e))

    file_metadata = {
        "name": f"{filename}.zip",
        "mimeType": "application/zip",
        "parents": [config["folder_id"]]
    }
    media = MediaFileUpload(f"{filename}.zip", mimetype="application/zip", resumable=True)
    file = service.files().create(body=file_metadata, media_body=media, fields="id", supportsAllDrives=True).execute()

    if os.path.isfile(zip_path):
        os.remove(zip_path)

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
        handler(service, info["folder_name"], info["folder_path"], info.get("include_paths"))
