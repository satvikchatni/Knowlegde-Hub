import asyncio
import re  # regular expression
import shutil
import uuid
from pathlib import Path, PureWindowsPath
from typing import BinaryIO

from fastapi import UploadFile


# BinaryIO,expects a binary file stream(a sequence of raw,unformatted bytes(0s and 1s)) instead of text file stream(sequence of human-readable text charcaters)
class StorageService:
    def __init__(self, upload_dir: str):
        self.upload_dir = Path(upload_dir)

    def verify_file_type(self, file_obj: BinaryIO):
        header = file_obj.read(1024)
        file_obj.seek(0)  # pointer at byte 1024, rewind it to index 0.
        if header.startswith(b"%PDF-"):  # read the first 1024 bytes and check for pdf signature.
            return "application/pdf"
        try:  # try to decode the bytes into string
            header.decode(
                "utf-8"
            )  # text file conatins nothing but valid text characters, every single byte in a text file matches a valid entry in "UTF-8" dictionary.
            return "text/plain"
        except UnicodeDecodeError:
            raise ValueError("invalid file type")

    def clean_display_name(self, filename: str):
        if not filename or not filename.strip():  # .strip() removes whitespaces
            return "untitled"
        text = PureWindowsPath(filename).name  # to remove any '/' or '\'.
        # strip out any bad business
        cleaned = re.sub(
            r"[\x00-\x1f\x7f-\x9f]", "", text
        )  # \x00-null byte means "stop reading here",\x1f-bell makes the computer go beep.\x7f-\x9f backspaces,delete commands and escape sequences.
        cleaned = cleaned.strip(" .")
        name = cleaned[0:255]  # till 255 characters.
        return name if name else "untitled"

    async def save_file(
        self, file: UploadFile, workspace_id: uuid.UUID, document_id: uuid.UUID
    ) -> str:
        ext = Path(file.filename or "").suffix
        relative_path = Path(str(workspace_id)) / f"{document_id}{ext}"
        absolute_path = self.upload_dir / relative_path

        def _sync_write():  # synchronous write- mkdir,shutil,open are synchronous -will block the entire thread,it must be offloaded using asyncio.to_thred(...)
            absolute_path.parent.mkdir(
                parents=True, exist_ok=True
            )  # create folders if they don't exist already.
            with (
                open(absolute_path, "wb") as buffer
            ):  # to open a write binary stream,treats date as raw,unformatted bytes, writes the exact 0s and 1s onto the disk.
                shutil.copyfileobj(
                    file.file, buffer
                )  # to copy data in chunks,shutil stands for shell utilities ,built-in python module for advanced file management functions

        await asyncio.to_thread(_sync_write)
        return str(relative_path)

    async def delete_file(self, relative_path: str) -> None:
        absolute_path = self.upload_dir / Path(relative_path)

        def _sync_delete():
            try:  # if it's there,delete it.If it's already gone,unlink() will throw a FileNotFoundError.
                absolute_path.unlink()
            except FileNotFoundError:
                pass

        await asyncio.to_thread(_sync_delete)
