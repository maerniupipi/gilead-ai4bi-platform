"""
评估模块 Pydantic schemas
"""
from .eval_folder import (
    EvalFolderBase, EvalFolderCreate, EvalFolderUpdate,
    EvalFolderResponse, EvalFolderTree,
)
from .eval_suite import (
    EvalSuiteBase, EvalSuiteCreate, EvalSuiteUpdate, EvalSuiteResponse,
    EvalShareIssueRequest, EvalShareIssueOut,
)
from .eval_tag import (
    EvalTagBase, EvalTagCreate, EvalTagUpdate, EvalTagResponse,
)
from .eval_case import (
    EvalCaseBase, EvalCaseCreate, EvalCaseUpdate, EvalCaseResponse,
)
from .eval_ground_truth import (
    EvalGroundTruthBase, EvalGroundTruthCreate, EvalGroundTruthUpdate,
    EvalGroundTruthResponse,
)
from .eval_output_template import (
    EvalOutputTemplateBase, EvalOutputTemplateCreate, EvalOutputTemplateUpdate,
    EvalOutputTemplateResponse,
)
from .eval_task import (
    EvalSubTaskCreate, EvalExecParams, EvalTaskCreate,
    EvalTaskResponse, EvalSubTaskResponse,
)
from .eval_run import (
    EvalRunResponse, EvalRunListResponse, EvalManualCorrection,
)
from .eval_comparison import (
    EvalComparisonResponse,
)
from .eval_comparison_template import (
    EvalComparisonTemplateCreate, EvalComparisonTemplateUpdate,
    EvalComparisonTemplateResponse,
)
from .eval_schedule import (
    EvalScheduleBase, EvalScheduleCreate, EvalScheduleUpdate,
    EvalScheduleResponse,
)
from .eval_generate import (
    EvalGenerateRequest, EvalImportPreview, EvalImportRequest,
)

__all__ = [
    # Folder
    "EvalFolderBase", "EvalFolderCreate", "EvalFolderUpdate",
    "EvalFolderResponse", "EvalFolderTree",
    # Suite
    "EvalSuiteBase", "EvalSuiteCreate", "EvalSuiteUpdate", "EvalSuiteResponse",
    "EvalShareIssueRequest", "EvalShareIssueOut",
    # Tag
    "EvalTagBase", "EvalTagCreate", "EvalTagUpdate", "EvalTagResponse",
    # Case
    "EvalCaseBase", "EvalCaseCreate", "EvalCaseUpdate", "EvalCaseResponse",
    # Ground Truth
    "EvalGroundTruthBase", "EvalGroundTruthCreate", "EvalGroundTruthUpdate",
    "EvalGroundTruthResponse",
    # Output Template
    "EvalOutputTemplateBase", "EvalOutputTemplateCreate", "EvalOutputTemplateUpdate",
    "EvalOutputTemplateResponse",
    # Task
    "EvalSubTaskCreate", "EvalExecParams", "EvalTaskCreate",
    "EvalTaskResponse", "EvalSubTaskResponse",
    # Run
    "EvalRunResponse", "EvalRunListResponse", "EvalManualCorrection",
    # Comparison
    "EvalComparisonResponse",
    # Comparison Template
    "EvalComparisonTemplateCreate", "EvalComparisonTemplateUpdate",
    "EvalComparisonTemplateResponse",
    # Schedule
    "EvalScheduleBase", "EvalScheduleCreate", "EvalScheduleUpdate",
    "EvalScheduleResponse",
    # Generate / Import
    "EvalGenerateRequest", "EvalImportPreview", "EvalImportRequest",
]
