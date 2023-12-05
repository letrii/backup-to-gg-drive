import shutil
import json
import os

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from datetime import datetime, timedelta

dir_path = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(dir_path, 'config.json')) as f:
    config = json.load(f)


def handler(folder_name, folder_path):
    # Create a Credentials object from the JSON data
    credentials = service_account.Credentials.from_service_account_file(os.path.join(dir_path, 'credentials.json'))

    # Build the Drive API service
    service = build("drive", "v3", credentials=credentials)

    current_date = datetime.now()
    filename = f"{config['parent_folder_name']}-{folder_name}-{current_date.strftime('%d-%m')}"
    shutil.make_archive(filename, "zip", folder_path)

    # upload file
    file_metadata = {
        "name": f"{filename}.zip",
        "mimeType": "application/zip"
    }
    media = MediaFileUpload(f"{filename}.zip", mimetype="application/zip", resumable=True)
    file = service.files().create(body=file_metadata, media_body=media, fields="id").execute()

    # share file
    new_permission = {
        "type": "user",
        "role": "writer",
        "emailAddress": config["share_email"],
    }
    service.permissions().create(fileId=file.get("id"), body=new_permission, transferOwnership=False).execute()

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
            old_file = os.path.join(dir_path, drive_file)
            if os.path.isfile(old_file):
                os.remove(old_file)


if __name__ == "__main__":
    for info in config["folders"]:
        handler(info["folder_name"], info["folder_path"])
