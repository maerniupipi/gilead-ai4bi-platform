"""
统一响应规范 - 定义标准响应码和HTTP状态码映射

所有接口通过 main.py 中的 ResponseEnvelopeMiddleware 自动包装成 {code, message, data}
"""
from typing import Any


class ResponseCode:
    """标准响应码定义"""
    SUCCESS = "SUCCESS"                    # 成功
    NOT_FOUND = "NOT_FOUND"                # 资源不存在
    BAD_REQUEST = "BAD_REQUEST"            # 请求参数有误
    DUPLICATE = "DUPLICATE"                # 唯一性冲突（如名称重复）
    VALIDATION_ERROR = "VALIDATION_ERROR"  # 请求体/路径参数校验失败
    UNAUTHORIZED = "UNAUTHORIZED"          # 未登录/Token无效
    FORBIDDEN = "FORBIDDEN"                # 无权限
    SERVER_ERROR = "SERVER_ERROR"          # 服务器内部错误

# HTTP状态码到ResponseCode的映射（用于异常处理器）
HTTP_STATUS_TO_CODE: dict[int, str] = {
    400: ResponseCode.BAD_REQUEST,
    401: ResponseCode.UNAUTHORIZED,
    403: ResponseCode.FORBIDDEN,
    404: ResponseCode.NOT_FOUND,
    409: ResponseCode.DUPLICATE,
    422: ResponseCode.VALIDATION_ERROR,
    500: ResponseCode.SERVER_ERROR,
}
