"""
评测模块服务层
"""
from .eval_folder_service import (
    list_folders_service,
    create_folder_service,
    update_folder_service,
    delete_folder_service,
)
from .eval_suite_service import (
    list_suites_service,
    get_suite_service,
    create_suite_service,
    update_suite_service,
    delete_suite_service,
    copy_suite_service,
)
from .eval_case_service import (
    list_cases_service,
    create_case_service,
    update_case_service,
    delete_case_service,
    batch_delete_cases_service,
    batch_update_cases_service,
    import_cases_service,
    import_preview_service,
    export_cases_service,
)
from .eval_case_generate_service import generate_cases_service
from .eval_ground_truth_service import (
    list_ground_truths_service,
    create_ground_truth_service,
    update_ground_truth_service,
    delete_ground_truth_service,
)
from .eval_output_template_service import (
    list_templates_service,
    create_template_service,
    update_template_service,
    delete_template_service,
    set_default_service,
)
from .eval_task_service import (
    list_tasks_service,
    get_task_service,
    create_task_service,
    start_task_service,
    pause_task_service,
    resume_task_service,
    cancel_task_service,
    retry_failed_service,
    delete_task_service,
)
from .eval_schedule_service import (
    list_schedules_service,
    create_schedule_service,
    update_schedule_service,
    delete_schedule_service,
    trigger_schedule_service,
)

__all__ = [
    # folder
    "list_folders_service",
    "create_folder_service",
    "update_folder_service",
    "delete_folder_service",
    # suite
    "list_suites_service",
    "get_suite_service",
    "create_suite_service",
    "update_suite_service",
    "delete_suite_service",
    "copy_suite_service",
    # case
    "list_cases_service",
    "create_case_service",
    "update_case_service",
    "delete_case_service",
    "batch_delete_cases_service",
    "batch_update_cases_service",
    "generate_cases_service",
    "import_cases_service",
    "import_preview_service",
    "export_cases_service",
    # ground truth
    "list_ground_truths_service",
    "create_ground_truth_service",
    "update_ground_truth_service",
    "delete_ground_truth_service",
    # output template
    "list_templates_service",
    "create_template_service",
    "update_template_service",
    "delete_template_service",
    "set_default_service",
    # task
    "list_tasks_service",
    "get_task_service",
    "create_task_service",
    "start_task_service",
    "pause_task_service",
    "resume_task_service",
    "cancel_task_service",
    "retry_failed_service",
    "delete_task_service",
    # schedule
    "list_schedules_service",
    "create_schedule_service",
    "update_schedule_service",
    "delete_schedule_service",
    "trigger_schedule_service",
]
