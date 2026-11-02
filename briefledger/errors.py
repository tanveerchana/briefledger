class StoreError(Exception):
    """A bounded, user-facing validation or collection error."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status
