class OpenCAEError(RuntimeError):
    code = "OPEN_CAE_ERROR"


class WorkspaceViolation(OpenCAEError):
    code = "WORKSPACE_VIOLATION"


class ExecutableNotAllowed(OpenCAEError):
    code = "EXECUTABLE_NOT_ALLOWED"


class ExternalProcessError(OpenCAEError):
    code = "EXTERNAL_PROCESS_ERROR"


class CapabilityUnavailable(OpenCAEError):
    code = "CAPABILITY_UNAVAILABLE"

