"""Explicit failures for workflow storage; absence is not a storage error."""


class WorkflowStoreError(RuntimeError):
    pass


class WorkflowStorageError(WorkflowStoreError):
    pass


class WorkflowBusyError(WorkflowStorageError):
    pass


class WorkflowIntegrityError(WorkflowStorageError):
    pass


class WorkflowConfigurationError(WorkflowStoreError):
    pass


class WorkflowSchemaError(WorkflowConfigurationError):
    pass


class WorkflowConflictError(WorkflowStoreError):
    pass


class WorkflowRevisionError(WorkflowConflictError):
    pass


class WorkflowGenerationError(WorkflowConflictError):
    pass


class WorkflowNotFoundError(WorkflowStoreError):
    pass
