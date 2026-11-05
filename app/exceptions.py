class AppError(Exception):
    status_code = 500
    code = "app_error"

    def __init__(self, message: str, headers: dict[str, str] | None = None):
        super().__init__(message)
        self.message = message
        self.headers = headers


# --- 401 Unauthorized --- (actually means unauthenticated, missing credentials)
class UnAuthenticatedClient(AppError):
    status_code = 401
    code = "unauthenticated_client_error"


# --- 403 Forbidden --- (authenticated, but lacks permissions)
class UnAuthorizedClient(AppError):
    status_code = 403
    code = "unauthorized_client_error"


# --- 404 Not Found ---
class NotFound(AppError):
    status_code = 404
    code = "not_found"


# --- 409 Conflict ---
class Conflict(AppError):
    status_code = 409
    code = "conflict_error"


# --- 413 Content Too Large
class TooLarge(AppError):
    status_code = 413
    code = "content_too_large"


# --- 415 Unsupported Media Type
class UnsupportedType(AppError):
    status_code = 415
    code = "unsupported_media_type"


# class DocumentProcessingError(AppError):
#     status_code=422
#     code="document_processing_error"

class PasswordProtected(AppError):
    status_code=403
    code="file_password_protected"

class InvalidFile(AppError):
    status_code=400
    code="invalid_file"

class EmbedderDimMismatchError(AppError):
    status_code=400
    code="dimension_mismatch"