import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import update, or_
from sqlalchemy.exc import IntegrityError
from ...core.database import SessionLocal
from ...core.execution import read_database
from ...models.chatbi import ChatBIExport, ChatBIMessage, ChatBIResult
from .chat import owned_conversation, uid
from .config import APIError, positive_env
from .export_names import export_file_name
from .ppt_settings import resolve_ppt_model
from .xlsx_renderer import generate_xlsx

logger = logging.getLogger(__name__)


def export_worker_enabled():
    # A shared database does not imply shared file storage. Only deployments
    # serving CHATBI_STORAGE_DIR may consume this queue; local dev stays off.
    return bool(os.getenv("CHATBI_API_KEY") or os.getenv("CHATBI_DOWNLOAD_SIGNING_KEY")) and os.getenv(
        "CHATBI_EXPORT_WORKER_ENABLED", "false"
    ).strip().lower() in {"1", "true", "yes", "on"}


def export_state(job, db=None):
    if job.summary_type == 'ALL':
        if db is None:
            raise ValueError('双版本 PPT 状态查询需要数据库会话')
        children = [db.get(ChatBIExport, identifier) for identifier in job.payload['child_task_ids']]
        valid = [child for child in children if child and child.owner == job.owner]
        files = [export_state(child) for child in valid]
        failed = len(valid) != 2 or any(f['status'] == 'failed' for f in files)
        status = ('failed' if failed else 'succeeded' if all(f['status'] == 'succeeded' for f in files)
                  else 'running' if any(f['status'] in {'running', 'succeeded'} for f in files) else 'pending')
        expiries = [f['expires_at'] for f in files if f['expires_at']]
        finished = [f['finished_at'] for f in files if f['finished_at']]
        terminal = len(files) == 2 and all(f['status'] in {'succeeded', 'failed'} for f in files)
        return {'task_id': job.id, 'file_id': None, 'file_type': 'ppt', 'summaryType': 'ALL',
                'status': status, 'error': '部分 PPT 生成失败，请查看 files 中的任务状态' if failed else None,
                'file_name': '', 'file_size': sum(f['file_size'] for f in files), 'created_at': job.created_at,
                'finished_at': max(finished) if terminal and finished else None,
                'expires_at': min(expiries) if len(expiries) == 2 else None,
                'downloadable': False, 'expired': any(f['expired'] for f in files), 'files': files}
    expired = bool(job.expires_at and job.expires_at <= int(time.time()))
    return {"task_id": job.id, "file_id": job.file_id, "file_type": job.kind,
            "summaryType": job.summary_type, "status": job.status, "error": job.error,
            "file_name": job.file_name, "file_size": job.file_size, "created_at": job.created_at,
            "finished_at": job.finished_at, "expires_at": job.expires_at,
            "downloadable": job.status == "succeeded" and not expired, "expired": expired}


def get_job(db, task_id, user):
    job = db.get(ChatBIExport, str(task_id))
    if not job or job.owner != user.owner:
        raise APIError(404, "task_not_found", "文件任务不存在")
    return job


def _complete_ppt_table(db, message, item, owner):
    reference = (item.get("outputs") or {}).get("data_ref")
    result = db.get(ChatBIResult, str(reference)) if reference else None
    if (not result or result.owner != owner or result.message_id != message.id
            or result.conversation_id != message.conversation_id):
        raise APIError(404, "result_not_found", "表格数据引用不存在")
    if not result.complete or result.total_rows != len(result.rows):
        raise APIError(409, "incomplete_result", "历史记录只有预览数据，无法生成完整 PPT")
    return result


def create_export(db, kind, body, user, *, background_tasks=None):
    owned_conversation(db, body.conversation_id, user)
    # Naming context must not change the identity of an existing export request.
    request_data = body.model_dump(mode="json", by_alias=True, exclude={"user", "idempotency_key", "first_question"})
    digest = hashlib.sha256(json.dumps({"kind": kind, **request_data}, sort_keys=True).encode()).hexdigest()
    if body.idempotency_key:
        previous = db.query(ChatBIExport).filter_by(owner=user.owner, idempotency_key=body.idempotency_key).first()
        if previous:
            if previous.request_hash != digest:
                raise APIError(409, "idempotency_conflict", "同一幂等标识不能用于不同导出请求")
            return previous
    if kind == "xlsx":
        result = db.get(ChatBIResult, str(body.data_ref))
        if not result or result.owner != user.owner or result.message_id != str(body.message_id) or result.conversation_id != str(body.conversation_id):
            raise APIError(404, "result_not_found", "表格数据引用不存在")
        message = db.get(ChatBIMessage, result.message_id)
        if not message or message.status != "succeeded":
            raise APIError(409, "answer_not_ready", "回答尚未成功完成")
        if not result.complete or result.total_rows != len(result.rows):
            raise APIError(409, "incomplete_result", "分析引擎只提供了样本数据，无法导出完整数据")
        if result.total_rows > 1048575 or len(result.columns) > 16384:
            raise APIError(413, "xlsx_limit", "结果超过单张 Excel 工作表的容量")
        payload = {"data_ref": result.id}
        summary_type = None
    else:
        summary_model = resolve_ppt_model(db) if body.summary_type in {"AI_SUMMARY", "ALL"} else None
        query = db.query(ChatBIMessage).filter_by(conversation_id=str(body.conversation_id), owner=user.owner, status="succeeded")
        if body.message_ids is not None:
            query = query.filter(ChatBIMessage.id.in_([str(m) for m in body.message_ids]))
        messages = query.order_by(ChatBIMessage.sequence).all()
        if not messages or (body.message_ids is not None and len(messages) != len(set(map(str, body.message_ids)))):
            raise APIError(404, "message_not_found", "没有可导出的完整回答")
        for message in messages:
            for item in message.content or []:
                if item.get("type") == "table":
                    _complete_ppt_table(db, message, item, user.owner)
        # Snapshot selected IDs now, so later chat turns cannot enter an already-created export.
        payload = {"message_ids": [m.id for m in messages]}
        if summary_model:
            payload["summary_model"] = summary_model
        summary_type = body.summary_type
    file_id = uid()
    first_question = body.first_question
    if kind == 'xlsx':
        first_question = result.title or message.query
    if first_question is None:
        first_message = db.query(ChatBIMessage).filter_by(
            conversation_id=str(body.conversation_id), owner=user.owner
        ).order_by(ChatBIMessage.sequence, ChatBIMessage.created_at, ChatBIMessage.id).first()
        first_question = first_message.query if first_message else None
    now = datetime.now(timezone.utc)
    name = export_file_name(kind, summary_type, first_question, now)
    # A local server may share the job DB but not file storage. Reserve its own
    # accepted request before commit, so shared queue workers cannot consume it.
    request_worker = background_tasks is not None and os.getenv("CHATBI_EXPORT_REQUEST_WORKER_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
    job = ChatBIExport(id=uid(), file_id=file_id, owner=user.owner, user_id=user.user_id,
                       conversation_id=str(body.conversation_id), kind=kind, summary_type=summary_type,
                       payload=payload, request_hash=digest, idempotency_key=body.idempotency_key,
                       status="running" if request_worker else "pending", file_name=name, created_at=int(now.timestamp()),
                       started_at=int(now.timestamp()) if request_worker else None,
                       lease_until=int(now.timestamp()) + 900 if request_worker else None)
    children = []
    if summary_type == 'ALL':
        for mode in ('FULL_SUMMARY', 'AI_SUMMARY'):
            child_payload = {'message_ids': list(payload['message_ids'])}
            if mode == 'AI_SUMMARY':
                child_payload['summary_model'] = payload['summary_model']
            children.append(ChatBIExport(id=uid(), file_id=uid(), owner=user.owner, user_id=user.user_id,
                conversation_id=str(body.conversation_id), kind='ppt', summary_type=mode,
                payload=child_payload, request_hash=hashlib.sha256((digest + mode).encode()).hexdigest(),
                status='running' if request_worker else 'pending', file_name=export_file_name('ppt', mode, first_question, now),
                created_at=int(now.timestamp()), started_at=int(now.timestamp()) if request_worker else None,
                lease_until=int(now.timestamp()) + 900 if request_worker else None))
        job.payload = {'child_task_ids': [child.id for child in children], 'message_ids': payload['message_ids']}
        job.status, job.file_name, job.started_at, job.lease_until = 'pending', '', None, None
        db.add_all(children)
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if not body.idempotency_key:
            raise
        previous = db.query(ChatBIExport).filter_by(owner=user.owner, idempotency_key=body.idempotency_key).first()
        if not previous or previous.request_hash != digest:
            raise APIError(409, "idempotency_conflict", "导出请求冲突")
        return previous
    if request_worker:
        for task in children or [job]:
            background_tasks.add_task(process_requested_export, task.id)
    return job


def renew_requested_export(job_id):
    # BackgroundTasks runs sequentially. The second PPT's generation lease
    # starts when it actually runs, rather than while the first PPT renders.
    now = int(time.time())
    with SessionLocal() as db:
        changed = db.execute(update(ChatBIExport).where(ChatBIExport.id == job_id,
            ChatBIExport.status == 'running').values(started_at=now, lease_until=now + 900))
        db.commit()
        return changed.rowcount == 1


async def process_requested_export(job_id):
    if await asyncio.to_thread(renew_requested_export, job_id):
        await asyncio.wait_for(process_export(job_id), timeout=840)


def file_path(job):
    root = Path(os.getenv("CHATBI_STORAGE_DIR", "data/chatbi-exports")).resolve()
    # Only server-generated UUIDs and enum values are used in the path.
    return root / f"{job.file_id}.{'xlsx' if job.kind == 'xlsx' else 'pptx'}"


def signing_key():
    key = os.getenv("CHATBI_DOWNLOAD_SIGNING_KEY") or os.getenv("CHATBI_API_KEY")
    if not key:
        raise APIError(503, "not_configured", "下载签名尚未配置")
    return key.encode()


def signature(job, expires):
    return hmac.new(signing_key(), f"{job.file_id}:{job.owner}:{expires}".encode(), hashlib.sha256).hexdigest()


def ensure_downloadable(job):
    if job.summary_type == 'ALL':
        raise APIError(409, 'multiple_files', '双版本 PPT 请分别使用 files 内的 file_id 获取下载链接')
    if job.status != "succeeded":
        raise APIError(409, "file_not_ready", "文件尚未生成成功")
    if not job.expires_at or job.expires_at <= int(time.time()):
        raise APIError(410, "file_expired", "文件已过期，请重新生成")
    if not file_path(job).is_file():
        raise APIError(404, "file_not_found", "文件不存在，请重新生成")


def download_url(db, file_id, user, base_url):
    job = db.query(ChatBIExport).filter_by(file_id=str(file_id), owner=user.owner).first()
    if not job:
        raise APIError(404, "file_not_found", "文件不存在")
    ensure_downloadable(job)
    expires = min(job.expires_at, int(time.time()) + positive_env("CHATBI_DOWNLOAD_TTL", 900))
    base = (os.getenv("CHATBI_PUBLIC_BASE_URL") or base_url).rstrip("/")
    return {"file_id": job.file_id, "file_name": job.file_name, "downloadable": True,
            "url": f"{base}/api/service/files/{job.file_id}/content?expires={expires}&signature={signature(job, expires)}",
            "expires_at": expires, "file_expires_at": job.expires_at}


def signed_file(db, file_id, expires, sig):
    job = db.query(ChatBIExport).filter_by(file_id=str(file_id)).first()
    if not job or not hmac.compare_digest(signature(job, expires).encode(), sig.encode()):
        raise APIError(403, "invalid_signature", "下载链接无效")
    if expires <= int(time.time()):
        raise APIError(410, "link_expired", "下载链接已过期")
    ensure_downloadable(job)
    return job


def ppt_models(db, job):
    models = []
    for mid in job.payload["message_ids"]:
        msg = db.get(ChatBIMessage, mid)
        if not msg or msg.owner != job.owner or msg.status != "succeeded":
            raise ValueError("导出快照已失效")
        tables, charts = [], []
        for item in msg.content:
            output = item.get("outputs") or {}
            if item.get("type") == "table":
                result = _complete_ppt_table(db, msg, item, job.owner)
                tables.append({"query": item["title"], "data": result.rows})
            elif item.get("type") == "chart":
                cols = [{**c, "target": "xaxis"} for c in output["dimensions"]]
                cols += [{**c, "target": "yaxis"} for c in output["series"]]
                charts.append({"query": item["title"], "chart": {"type": {"bar": "A", "line": "B", "pie": "C"}.get(output["chart_type"], "A"),
                               "columns": cols, "data": output["rows"]}})
        models.append({"question": msg.query, "title": msg.query, "biz_date": "", "ppt_answer_models": [{
            "answer": msg.answer, "sql_data": [], "excel_data": tables, "chart_data": charts,
        }]})
    return models


async def process_export(job_id, *, factory=None):
    factory = factory or SessionLocal
    db = factory()

    def load_snapshot(session):
        job = session.get(ChatBIExport, job_id)
        if job is None:
            raise ValueError("文件任务不存在")
        if job.summary_type == "ALL":
            return job, None
        if job.kind == "xlsx":
            result = session.get(ChatBIResult, job.payload["data_ref"])
            if not result or result.owner != job.owner or not result.complete or result.total_rows != len(result.rows):
                raise ValueError("完整数据快照已失效")
            return job, result
        return job, ppt_models(session, job)

    def persist(session, **values):
        session.execute(update(ChatBIExport).where(ChatBIExport.id == job_id).values(**values))
        session.commit()

    tmp = None
    try:
        job, snapshot = await read_database(db, load_snapshot)
        if job.summary_type == 'ALL':
            for child_id in job.payload['child_task_ids']:
                await process_export(child_id, factory=factory)
            return
        if job.kind == "xlsx":
            result = snapshot
            data = await asyncio.to_thread(generate_xlsx, result.columns, result.rows)
        else:
            from .ppt_renderer import generate_ppt_from_models_to_bytes, generate_ai_summary_ppt_to_bytes
            models = snapshot
            if job.summary_type == "AI_SUMMARY":
                from .summary import AISummaryPPTService
                summary = await AISummaryPPTService().build_summary(models, db, binding=job.payload.get("summary_model"))
                data = await asyncio.to_thread(generate_ai_summary_ppt_to_bytes, summary, models[0]["question"])
            else:
                data = await asyncio.to_thread(generate_ppt_from_models_to_bytes, models)
            if not data:
                raise ValueError("PPT 生成结果为空")
        path = file_path(job)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        await asyncio.to_thread(tmp.write_bytes, data)
        tmp.replace(path)
        finished_at = int(time.time())
        await read_database(db, persist, status="succeeded", file_size=len(data), finished_at=finished_at,
                            expires_at=finished_at + positive_env("CHATBI_FILE_TTL", 604800), lease_until=None)
    except asyncio.CancelledError:
        await read_database(db, persist, status="failed", error="文件生成超时或服务中断，请重试",
                            lease_until=None, finished_at=int(time.time()))
        raise
    except Exception:
        logger.exception("ChatBI export failed task_id=%s", job_id)
        await read_database(db, persist, status="failed", error="文件生成失败，请重试或联系管理员",
                            lease_until=None, finished_at=int(time.time()))
    finally:
        if tmp:
            tmp.unlink(missing_ok=True)
        db.close()


def claim_export(factory):
    now = int(time.time())
    with factory() as db:
        # Process termination must not leave a job permanently 'running'.
        db.execute(update(ChatBIExport).where(ChatBIExport.status == "running", ChatBIExport.lease_until < now)
                   .values(status="failed", error="生成任务超时或服务中断，请重试", finished_at=now, lease_until=None))
        job = db.query(ChatBIExport).filter(ChatBIExport.status == 'pending',
            or_(ChatBIExport.summary_type.is_(None), ChatBIExport.summary_type != 'ALL')).order_by(ChatBIExport.created_at).first()
        if not job:
            db.commit()
            return None
        job_id = job.id
        claimed = db.execute(update(ChatBIExport).where(ChatBIExport.id == job_id, ChatBIExport.status == "pending")
                             .values(status="running", started_at=now, lease_until=now + 900))
        db.commit()
        return job_id if claimed.rowcount == 1 else None


def cleanup_expired_files(factory):
    with factory() as db:
        expired = db.query(ChatBIExport).filter(ChatBIExport.status == "succeeded", ChatBIExport.expires_at <= int(time.time())).all()
        for job in expired:
            file_path(job).unlink(missing_ok=True)


async def export_worker(*, factory=None):
    factory = factory or SessionLocal
    last_cleanup = 0
    while True:
        try:
            if time.monotonic() - last_cleanup > 3600:
                await asyncio.to_thread(cleanup_expired_files, factory)
                last_cleanup = time.monotonic()
            # Each operation owns its session. A slow remote DB poll must not
            # block HTTP download responses on the application event loop.
            job_id = await asyncio.to_thread(claim_export, factory)
            if job_id:
                await asyncio.wait_for(process_export(job_id, factory=factory), timeout=840)
                continue
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("ChatBI export worker iteration failed")
        await asyncio.sleep(2)
