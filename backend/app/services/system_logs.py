"""Bounded asynchronous log persistence; failures fall back to existing file/console logs."""
import logging
import os
import queue
import socket
import threading
import time

from sqlalchemy import or_

from ..core.observability import log_context, snapshot, redact_text
from ..models.system_log import SystemLog

RETENTION_MS = 7 * 24 * 60 * 60 * 1000
_writer = None
_inside_writer = threading.local()


def cleanup_logs(db, *, now_ms=None, batch_size=5000):
    cutoff = (int(time.time()*1000) if now_ms is None else now_ms) - RETENTION_MS
    ids = [row[0] for row in db.query(SystemLog.id).filter(SystemLog.created_at < cutoff).order_by(SystemLog.id).limit(batch_size).all()]
    if ids:
        db.query(SystemLog).filter(SystemLog.id.in_(ids)).delete(synchronize_session=False)
    db.commit()
    return len(ids)


class DatabaseLogHandler(logging.Handler):
    def __init__(self, factory, *, capacity=10000):
        super().__init__(logging.DEBUG)
        self.factory = factory
        self.pending = queue.Queue(capacity)
        self.stopping = threading.Event()
        self.dropped = 0
        self.thread = threading.Thread(target=self._run, name='system-log-writer', daemon=True)
        self.thread.start()

    def emit(self, record):
        if getattr(_inside_writer, 'active', False) or record.name.startswith(('sqlalchemy.', 'pymysql.', 'mysql.')):
            return
        try:
            context = log_context.get()
            values = dict(created_at=int(record.created*1000), level=record.levelname,
                service=os.getenv('SERVICE_NAME','platform-backend'), instance=socket.gethostname(),
                logger=record.name[:255], message=redact_text(record.getMessage()),
                exception=redact_text(logging.Formatter().formatException(record.exc_info)) if record.exc_info else None,
                **{key:getattr(record,key,None) or context.get(key) for key in ('request_id','conversation_id','message_id','trace_id','user_id')},
                data=snapshot({**{k:v for k,v in context.items() if k not in {'request_id','conversation_id','message_id','trace_id','user_id'}},
                    'file':record.pathname,'line':record.lineno, **getattr(record,'support_data',{})}))
            try:
                self.pending.put_nowait(values)
            except queue.Full:
                self.dropped += 1
        except Exception:
            self.dropped += 1

    def _run(self):
        next_cleanup = 0
        _inside_writer.active = True
        while not self.stopping.is_set() or not self.pending.empty():
            batch, barriers = [], []
            try:
                item = self.pending.get(timeout=1)
                (barriers if isinstance(item,threading.Event) else batch).append(item)
                while len(batch) < 200:
                    try:
                        item = self.pending.get_nowait()
                    except queue.Empty:
                        break
                    (barriers if isinstance(item,threading.Event) else batch).append(item)
            except queue.Empty:
                pass
            try:
                if batch or time.monotonic() >= next_cleanup:
                    with self.factory() as db:
                        if batch:
                            db.bulk_insert_mappings(SystemLog, batch)
                            db.commit()
                        if time.monotonic() >= next_cleanup:
                            for _ in range(20):
                                if cleanup_logs(db) < 5000:
                                    break
                            next_cleanup = time.monotonic()+60
            except Exception:
                self.dropped += len(batch)
                next_cleanup = time.monotonic()+60
            finally:
                for _ in range(len(batch)+len(barriers)):
                    self.pending.task_done()
                for barrier in barriers:
                    barrier.set()
        _inside_writer.active = False

    def flush(self):
        if not hasattr(self,'pending') or not self.thread.is_alive():
            return
        barrier = threading.Event()
        try:
            self.pending.put(barrier, timeout=1)
            barrier.wait(5)
        except queue.Full:
            pass

    def close(self):
        self.stopping.set()
        if threading.current_thread() is not self.thread:
            self.thread.join(timeout=5)
        super().close()


def start_log_writer(factory):
    global _writer
    if _writer is None:
        _writer = DatabaseLogHandler(factory)
        logging.getLogger().addHandler(_writer)
        logging.getLogger('audit').addHandler(_writer)
    return _writer


def stop_log_writer():
    global _writer
    if _writer is not None:
        logging.getLogger().removeHandler(_writer)
        logging.getLogger('audit').removeHandler(_writer)
        _writer.close()
        _writer = None


def list_logs(db, *, page=1, page_size=50, level=None, keyword=None, request_id=None,
              conversation_id=None, message_id=None, trace_id=None, user_id=None,
              service=None, start_at=None, end_at=None):
    query = db.query(SystemLog).filter(SystemLog.created_at >= int(time.time()*1000)-RETENTION_MS)
    for key,value in dict(level=level,request_id=request_id,conversation_id=conversation_id,message_id=message_id,
                          trace_id=trace_id,user_id=user_id,service=service).items():
        if value:
            query = query.filter(getattr(SystemLog,key)==value)
    if keyword:
        pattern = '%'+keyword.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
        query = query.filter(or_(SystemLog.message.ilike(pattern,escape='\\'),SystemLog.exception.ilike(pattern,escape='\\'),SystemLog.logger.ilike(pattern,escape='\\')))
    if start_at is not None:
        query = query.filter(SystemLog.created_at >= start_at)
    if end_at is not None:
        query = query.filter(SystemLog.created_at <= end_at)
    total = query.count()
    rows = query.order_by(SystemLog.created_at.desc(),SystemLog.id.desc()).offset((page-1)*page_size).limit(page_size).all()
    fields = [c.name for c in SystemLog.__table__.columns]
    return {'items':[{key:getattr(row,key) for key in fields} for row in rows], 'total':total,
            'page':page,'page_size':page_size,'retention_days':7,'dropped_logs':_writer.dropped if _writer else 0}
