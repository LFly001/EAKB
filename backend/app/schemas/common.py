"""
通用 Pydantic Schema 定义
统一 API 返回体、分页模型、通用查询参数
Phase 2+ 各模块 schema 继承此文件中的基类
"""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

# ==========================================
# 泛型类型变量
# ==========================================
T = TypeVar("T")


# ==========================================
# 统一 API 返回体
# ==========================================


class APIResponse(BaseModel, Generic[T]):
    """
    所有 API 接口统一返回格式

    成功:
        { "code": 200, "msg": "success", "data": {...} }

    失败:
        { "code": 40001, "msg": "参数错误", "data": null }
    """

    code: int = Field(default=200, description="业务状态码: 200=成功, 非200=错误")
    msg: str = Field(default="success", description="提示信息")
    data: T | None = Field(default=None, description="业务数据")

    model_config = {"from_attributes": True}

    @classmethod
    def ok(cls, data: Any = None, msg: str = "success") -> "APIResponse":
        """快速构建成功响应"""
        return cls(code=200, msg=msg, data=data)

    @classmethod
    def fail(cls, code: int, msg: str, data: Any = None) -> "APIResponse":
        """快速构建失败响应"""
        return cls(code=code, msg=msg, data=data)


# ==========================================
# 通用分页 — 请求参数
# ==========================================


class PageQuery(BaseModel):
    """分页查询参数基类，各模块按需继承扩展"""

    page: int = Field(default=1, ge=1, description="当前页码 (从1开始)")
    page_size: int = Field(default=20, ge=1, le=100, description="每页条数 (最大100)")
    keyword: str | None = Field(default=None, description="搜索关键词")


# ==========================================
# 通用分页 — 响应体
# ==========================================


class PageResponse(BaseModel, Generic[T]):
    """
    分页结果统一包裹

    示例:
        {
          "total": 150,
          "page": 1,
          "page_size": 20,
          "pages": 8,
          "items": [...]
        }
    """

    total: int = Field(default=0, description="总记录数")
    page: int = Field(default=1, description="当前页码")
    page_size: int = Field(default=20, description="每页条数")
    pages: int = Field(default=0, description="总页数")
    items: list[T] = Field(default_factory=list, description="当前页数据列表")

    @classmethod
    def from_list(
        cls,
        items: list[T],
        total: int,
        page: int,
        page_size: int,
    ) -> "PageResponse":
        """从查询结果构建分页响应"""
        pages = (total + page_size - 1) // page_size if total > 0 else 0
        return cls(
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
            items=items,
        )
