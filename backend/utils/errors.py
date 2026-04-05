class ApplicationError(Exception):
    def __init__(self, detail: str, status_code: int = 400, error_code: str = "application_error") -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
        self.error_code = error_code


class ExternalServiceError(ApplicationError):
    def __init__(self, detail: str = "External service request failed") -> None:
        super().__init__(detail=detail, status_code=503, error_code="external_service_error")

