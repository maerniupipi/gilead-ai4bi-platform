from __future__ import annotations

import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.eval import (
    EvalCase,
    EvalCaseGroundTruth,
    EvalComparison,
    EvalRun,
    EvalSubTask,
    EvalSuite,
    EvalTask,
)
from app.services.eval import eval_case_service
from app.services.eval import eval_comparison_service
from app.services.eval import eval_task_service


def _make_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    for table in (
        EvalSubTask.__table__,
        EvalSuite.__table__,
        EvalTask.__table__,
        EvalCase.__table__,
        EvalCaseGroundTruth.__table__,
        EvalRun.__table__,
        EvalComparison.__table__,
    ):
        table.create(engine)
    return sessionmaker(bind=engine)


class EvalTaskExecutionTests(unittest.TestCase):
    def test_create_case_uses_suite_default_comparison_method(self):
        Session = _make_session()
        db = Session()
        try:
            suite = EvalSuite(
                id=3,
                space_id=1,
                folder_id=0,
                name="suite",
                default_comparison_method="llm_judge",
                created_by=1,
            )
            db.add(suite)
            db.commit()

            item = eval_case_service.create_case_service(
                db,
                3,
                {
                    "input_prompt": "销售额是多少",
                    "expected_answer": "SELECT SUM(amount) FROM sales",
                },
            )

            self.assertEqual(item["ground_truths"][0]["comparison_method"], "llm_judge")
        finally:
            db.close()

    def test_execute_single_case_waits_for_llm_comparison_before_returning(self):
        Session = _make_session()
        db = Session()
        try:
            task = EvalTask(
                id=10,
                suite_id=3,
                name="task",
                exec_params={"timeout_seconds": 180},
                status="running",
                created_by=1,
            )
            sub_task = EvalSubTask(id=1, task_id=10, target_type="agent", status="running")
            case = EvalCase(id=2, suite_id=3, input_prompt="q", is_active=True)
            run = EvalRun(id=4, sub_task_id=1, case_id=2, status="pending")
            db.add_all([task, sub_task, case, run])
            db.commit()
        finally:
            db.close()

        async def fake_run_judge_blocking(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        def fake_compare(run_id, task_id=None, timeout_seconds=None):
            _db = Session()
            try:
                _run_row = _db.query(EvalRun).filter(EvalRun.id == run_id).first()
                _run_row.status = "success"
                _db.commit()
            finally:
                _db.close()

        async def _run():
            with patch.object(eval_task_service, "SessionLocal", Session), patch.object(
                eval_task_service,
                "call_target",
                new=AsyncMock(return_value={
                    "raw_response": "SELECT 1",
                    "parsed_response": {"generated_sql": "SELECT 1"},
                    "execution_time_ms": 12,
                    "error": None,
                }),
            ), patch.object(
                eval_task_service,
                "_run_llm_comparison_in_thread",
                side_effect=fake_compare,
            ) as compare, patch.object(eval_task_service, "_run_judge_blocking", new=fake_run_judge_blocking):
                await eval_task_service._execute_single_case(1, 2)
                compare.assert_called_once_with(4, 10, 180)

        asyncio.run(_run())

        db = Session()
        try:
            run = db.query(EvalRun).filter(EvalRun.id == 4).first()
            self.assertEqual(run.status, "success")
            self.assertEqual(run.parsed_response["generated_sql"], "SELECT 1")
        finally:
            db.close()

    def test_task_level_llm_config_forces_llm_judge_for_existing_exact_cases(self):
        Session = _make_session()
        db = Session()
        try:
            task = EvalTask(id=10, suite_id=3, name="task", status="running", created_by=1)
            sub_task = EvalSubTask(
                id=1,
                task_id=10,
                target_type="agent",
                target_config={"llm_provider_id": 7, "llm_model": "judge-model"},
                status="completed",
            )
            case = EvalCase(id=2, suite_id=3, input_prompt="q", is_active=True)
            gt = EvalCaseGroundTruth(
                id=8,
                case_id=2,
                ground_truth="SELECT 1",
                comparison_method="exact",
                is_active=True,
            )
            run = EvalRun(
                id=4,
                sub_task_id=1,
                case_id=2,
                status="success",
                parsed_response={"generated_sql": "SELECT 1"},
            )
            db.add_all([task, sub_task, case, gt, run])
            db.commit()

            seen = {}

            def fake_execute_comparison(actual_output, ground_truth, method, config):
                seen["method"] = method
                seen["config"] = config
                return {
                    "is_correct": True,
                    "score": 1,
                    "detail": {"reason": "ok"},
                    "llm_raw_output": '{"result":"pass","score":1,"reason":"ok"}',
                }

            with patch.object(
                eval_comparison_service,
                "execute_comparison",
                side_effect=fake_execute_comparison,
            ):
                eval_comparison_service.run_comparison(db, 4)

            comp = db.query(EvalComparison).filter(EvalComparison.run_id == 4).first()
            self.assertEqual(seen["method"], "llm_judge")
            self.assertEqual(seen["config"]["llm_provider_id"], 7)
            self.assertEqual(comp.comparison_method, "llm_judge")
            self.assertTrue(comp.llm_judge_raw_output)
        finally:
            db.close()

    def test_schedule_missing_comparisons_only_schedules_success_runs_without_comparison(self):
        Session = _make_session()
        db = Session()
        try:
            sub_task = EvalSubTask(id=1, task_id=10, target_type="agent", status="completed")
            success_missing = EvalRun(id=4, sub_task_id=1, case_id=2, status="success")
            success_compared = EvalRun(id=5, sub_task_id=1, case_id=3, status="success")
            errored = EvalRun(id=6, sub_task_id=1, case_id=4, status="error")
            comparison = EvalComparison(
                run_id=5,
                ground_truth_id=1,
                comparison_method="llm_judge",
                is_correct=True,
                score=1,
                comparison_detail={},
            )
            db.add_all([sub_task, success_missing, success_compared, errored, comparison])
            db.commit()

            scheduled = []
            with patch.object(
                eval_task_service,
                "_run_llm_comparison_in_thread",
                side_effect=lambda run_id, task_id=None, timeout_seconds=None: scheduled.append((run_id, task_id)),
            ):
                count = eval_task_service._schedule_missing_comparisons_for_task(db, 10)

            self.assertEqual(count, 1)
            self.assertEqual(scheduled, [(4, 10)])
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
