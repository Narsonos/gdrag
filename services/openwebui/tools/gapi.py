"""
title: Simple GoogleDrive
author: Narsonos
description: A simple Google Drive integration that allows LLMs access files stored at google drive dynamically.
version: 0.0.1
license: None
requirements: google-api-python-client, google-auth, google-auth-oauthlib, pandas, pydantic, PyMuPDF, pymupdf4llm, openpyxl, tabulate
"""

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.http import MediaIoBaseDownload
import os, io, pandas
from typing import Callable, Any
from pydantic import BaseModel, Field
import pymupdf4llm  # type: ignore
import pymupdf  # type: ignore
import json
import unittest

EXPORT_MIME = {
    "application/vnd.google-apps.document": "application/pdf",
    "application/vnd.google-apps.spreadsheet": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

EXPORT_EXT_MAP = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
}

SERVICE_ACCOUNT = True


class GAPIClientWrapper:

    def __init__(
        self,
        service_key,
        folder_id,
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    ):
        self.service_key = service_key
        self.scopes = scopes
        self.folder_id = folder_id

    async def auth(self):
        creds = None
        if SERVICE_ACCOUNT:
            creds = service_account.Credentials.from_service_account_info(
                self.service_key, scopes=self.scopes
            )
            return creds
        if os.path.exists("token.json"):
            creds = Credentials.from_authorized_user_file("token.json")

        if not creds:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    "credentials.json", scopes=self.scopes
                )
                creds = flow.run_local_server(port=3000)
            with open("token.json", "w") as token:
                token.write(creds.to_json())
        return creds

    async def list(self, page_size=10, pages=None, q=None):
        page_token = None
        rs = []
        read_pages = 0
        while True:
            if pages is None or (not pages is None and read_pages < pages):
                with build("drive", "v3", credentials=await self.auth()) as service:
                    results = (
                        service.files()
                        .list(
                            q=(
                                f"'{self.folder_id}' in parents and ({q})"
                                if q
                                else f"'{self.folder_id}' in parents"
                            ),
                            pageSize=page_size,
                            fields="nextPageToken, files(id, name, mimeType, description)",
                            pageToken=page_token,
                        )
                        .execute()
                    )
                    rs.extend(results.get("files", []))
                    page_token = results.get("nextPageToken")
                read_pages += 1
            else:
                break
            if not page_token:
                break
        return rs

    async def getById(self, file_id):
        with build("drive", "v3", credentials=await self.auth()) as service:
            file = (
                service.files()
                .get(fileId=file_id, fields="id, name, mimeType")
                .execute()
            )
            filename = file["name"]
            mime_type = file["mimeType"]

            if mime_type in EXPORT_MIME:
                request = service.files().export_media(
                    fileId=file_id, mimeType=EXPORT_MIME[mime_type]
                )
                base_name, _ = os.path.splitext(filename)
                filename = base_name + EXPORT_EXT_MAP.get(EXPORT_MIME[mime_type], "")
            else:
                request = service.files().get_media(fileId=file_id)

            file_buffer = io.BytesIO()
            loader = MediaIoBaseDownload(file_buffer, request)
            done = False
            while not done:
                status, done = loader.next_chunk()
                print(f"Download {int(status.progress() * 100)}%")
            file_buffer.seek(0)
        return file_buffer, filename


async def main():
    """Just for test"""
    gapi = GAPIClientWrapper()
    files = await gapi.list()
    print(f"Fetched {len(files)} files md")
    print(files)
    if not files:
        raise FileNotFoundError

    file, filename = await gapi.getById(file_id=files[0]["id"])
    print(pandas.read_excel(file))


class EventEmitter:
    def __init__(self, event_emitter: Callable[[dict], Any] = None):
        self.event_emitter = event_emitter

    async def progress_update(self, description):
        await self.emit(description)

    async def error_update(self, description):
        await self.emit(description, "error", True)

    async def success_update(self, description):
        await self.emit(description, "success", True)

    async def emit(self, description="Unknown State", status="in_progress", done=False):
        if self.event_emitter:
            await self.event_emitter(
                {
                    "type": "status",
                    "data": {
                        "status": status,
                        "description": description,
                        "done": done,
                    },
                }
            )


class Tools:
    class Valves(BaseModel):
        FOLDER_ID: str = Field(
            default=None,
            description="ID of a ROOT folder for the agent",
        )

        KEY_JSON_CONTENT: str = Field(
            default=None, description="Content of service account key.json"
        )

    def __init__(self):
        self.valves = self.Valves()

    async def list_files(
        self,
        __event_emitter__: Callable[[dict], Any] = None,
        __user__: dict = {},
    ) -> str:
        """
        Fetches the lists available files from Google Drive.
        :return: A list of file_objects
        """
        gapi = GAPIClientWrapper(
            service_key=json.loads(self.valves.KEY_JSON_CONTENT),
            folder_id=self.valves.FOLDER_ID,
        )
        emitter = EventEmitter(__event_emitter__)
        await emitter.progress_update("Fetching filenames from Google Drive")
        results = await gapi.list(q="mimeType != 'application/vnd.google-apps.folder'")
        await emitter.success_update(
            "Filenames fetched from Google drive successfully!"
        )
        return results

    async def fetch_content(
        self,
        file_id,
        __event_emitter__: Callable[[dict], Any] = None,
        __user__: dict = {},
    ) -> str:
        """
        Extracts content of a file by its id and transforms it into readable form.
        :param file_id: String, the id of a file.
        :return: File content as a string. If possible, as markdown formatted one.
        """

        gapi = GAPIClientWrapper(
            service_key=json.loads(self.valves.KEY_JSON_CONTENT),
            folder_id=self.valves.FOLDER_ID,
        )
        emitter = EventEmitter(__event_emitter__)
        await emitter.progress_update(f"Downloading file {file_id}")
        filebytes, filename = await gapi.getById(file_id)
        await emitter.progress_update(f"File {filename} downloaded. Parsing...")

        if filename.endswith(".pdf"):
            doc = pymupdf.Document(stream=filebytes, filetype="pdf")
            content = pymupdf4llm.to_markdown(
                doc, ignore_images=True, ignore_graphics=False
            )
            await emitter.success_update(f"File read successfully as PDF - {filename}")
            return content
        elif filename.endswith(".xlsx"):
            content = pandas.read_excel(filebytes).to_markdown(index=False)
            await emitter.success_update(f"File read successfully as XLSX- {filename}")
            return content
        else:
            await emitter.error_update(f"File format is not supported - {filename}")
            return None


class GAPItest(unittest.IsolatedAsyncioTestCase):
    async def test_list(self):
        service_key = '<ENTER key.json content>'
        folder_id = "<ROOT Folder ID>"

        gapi = GAPIClientWrapper(
            service_key=json.loads(service_key), folder_id=folder_id
        )
        results = await gapi.list(q="mimeType != 'application/vnd.google-apps.folder'")
        print(results)


if __name__ == "__main__":
    unittest.main()
