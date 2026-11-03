from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.exceptions import Conflict, UnsupportedType


def file_extraction(file_path: str):
    if str(file_path).lower().endswith(".txt"):
        with (
            open(file_path) as file
        ):  # with statement closes the file for you,wo with you would have to close the file too
            content = file.read()
            return [{"page_number": 1, "text": content}]
    elif str(file_path).lower().endswith(".pdf"):
        pages = []
        try:
            reader = PdfReader(file_path)
            if reader.is_encrypted:
                raise Conflict("Password protected")
            for number, page in enumerate(reader.pages, start=1):
                text = page.extract_text()
                if text == "" or text.strip() == "":
                    continue  # skip the current one maybe it contains qr, move on to the next one
                pages.append({"page_number": number, "text": text})
            if not pages:  # if the entire pdf is blank
                raise Conflict("No readable text content")
            return pages
        except PdfReadError:
            raise ValueError("Has garbage bytes") from None

    else:
        raise UnsupportedType("Only .txt file or PDF.")
