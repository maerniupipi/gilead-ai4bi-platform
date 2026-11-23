"""
日志配置模块
按年月日生成日志文件夹，所有日志自动记录到文件
"""
import os
import logging
import atexit
import copy
import queue
import time
from logging.handlers import TimedRotatingFileHandler, QueueHandler, QueueListener
from datetime import datetime

# 日志根目录
LOG_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "logs")
_listeners = []


class BufferedLogHandler(QueueHandler):
    def __init__(self, target):
        super().__init__(queue.Queue(maxsize=10000))
        self.dropped = 0
        listener = QueueListener(self.queue, target, respect_handler_level=True)
        listener.start()
        _listeners.append(listener)

    def prepare(self, record):
        # Formatting and disk writes happen on the listener thread.
        return copy.copy(record)

    def enqueue(self, record):
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            self.dropped += 1


def stop_logging():
    for listener in _listeners:
        # Drain before enqueuing the sentinel, even when the buffer is full.
        listener.queue.join()
        listener.stop()
        for handler in listener.handlers:
            handler.close()
    _listeners.clear()


def log_buffer_stats():
    handlers = logging.getLogger().handlers + logging.getLogger("audit").handlers
    return [{"queued": handler.queue.qsize(), "dropped": handler.dropped}
            for handler in handlers if isinstance(handler, BufferedLogHandler)]


atexit.register(stop_logging)


def get_log_dir(date: datetime = None) -> str:
    """获取指定日期的日志目录，格式: logs/YYYY/MM/DD"""
    if date is None:
        date = datetime.now()
    log_dir = os.path.join(LOG_ROOT, str(date.year), f"{date.month:02d}", f"{date.day:02d}")
    os.makedirs(log_dir, exist_ok=True)
    return log_dir


class _ExcludeInfoFilter(logging.Filter):
    """过滤 INFO 级别日志，使控制台只输出 DEBUG 和 WARNING+"""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno != logging.INFO


class DailyLogHandler(TimedRotatingFileHandler):
    """每天轮转的日志处理器"""

    def __init__(self, filename, flush_every=False, **kwargs):
        # 确保目录存在
        log_dir = os.path.dirname(filename)
        os.makedirs(log_dir, exist_ok=True)
        super().__init__(
            filename=filename,
            when="midnight",
            interval=1,
            backupCount=30,
            encoding="utf-8",
            **kwargs
        )
        self._flush_every = flush_every

    def emit(self, record):
        """记录日志，可选每次写入后立即刷盘"""
        super().emit(record)
        if self._flush_every and self.stream:
            self.stream.flush()

    def doRollover(self):
        """日志轮转时，更新到新的日期目录"""
        # 关闭当前文件
        if self.stream:
            self.stream.close()
            self.stream = None
        # 更新文件名到新的日期（保留原始文件名，如 audit.log / app.log）
        old_filename = os.path.basename(self.baseFilename)
        new_log_dir = get_log_dir()
        new_filename = os.path.join(new_log_dir, old_filename)
        self.baseFilename = os.path.abspath(new_filename)
        # 确保目录存在
        os.makedirs(os.path.dirname(self.baseFilename), exist_ok=True)
        # 重新打开文件
        if not self.delay:
            self.stream = self._open()
        self.rolloverAt = self.computeRollover(int(time.time()))


def setup_logging():
    """配置应用日志"""
    # 创建根logger
    root_logger = logging.getLogger()
    stop_logging()
    root_logger.setLevel(os.getenv("PLATFORM_LOG_LEVEL", "DEBUG").upper())

    # 清除现有处理器
    root_logger.handlers.clear()

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.addFilter(_ExcludeInfoFilter())
    console_format = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_format)

    # 文件处理器（按日期目录）
    log_dir = get_log_dir()
    log_file = os.path.join(log_dir, "app.log")
    file_handler = DailyLogHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s [%(filename)s:%(lineno)d]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_format)

    # 添加处理器
    root_logger.addHandler(BufferedLogHandler(console_handler))
    root_logger.addHandler(BufferedLogHandler(file_handler))

    # 创建审计日志专用logger
    audit_logger = logging.getLogger("audit")
    audit_logger.setLevel(logging.INFO)
    audit_logger.propagate = False
    audit_logger.handlers.clear()

    # 审计日志文件处理器（flush_every=True 确保每次写入立即刷盘）
    audit_log_file = os.path.join(log_dir, "audit.log")
    audit_file_handler = DailyLogHandler(audit_log_file, flush_every=True)
    audit_file_handler.setLevel(logging.INFO)
    audit_format = logging.Formatter(
        "%(asctime)s [AUDIT] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    audit_file_handler.setFormatter(audit_format)

    # 只写文件，不刷屏控制台（错误由 root logger 单独输出）
    audit_logger.addHandler(BufferedLogHandler(audit_file_handler))

    # 启动验证：写入一条测试日志确认审计日志系统正常
    audit_logger.info(
        "Audit log system started | file=%s",
        os.path.abspath(audit_log_file),
    )

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """获取指定模块的logger"""
    return logging.getLogger(name)


def get_audit_logger() -> logging.Logger:
    """获取审计日志logger"""
    return logging.getLogger("audit")
