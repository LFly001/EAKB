"""
统一 JSON 响应工具
提供快速构建 APIResponse / PageResponse 的辅助函数
"""

from typing import Any

from app.schemas.common import APIResponse, PageResponse


def success(data: Any = None, msg: str = "success") -> dict:
    """
    构建成功响应 dict。
    适用于路由直接 return 的场景，无需手动构建 APIResponse。

    使用:
        return success(data={"user_id": 1})
        return success(msg="登录成功", data={"token": "xxx"})
    """
    return APIResponse.ok(data=data, msg=msg).model_dump()


def fail(code: int, msg: str, data: Any = None) -> dict:
    """
    构建失败响应 dict。

    使用:
        return fail(40001, "用户名已存在")
        return fail(40100, "密码错误")
    """
    return APIResponse.fail(code=code, msg=msg, data=data).model_dump()


def paginate(
    items: list[Any],
    total: int,
    page: int,
    page_size: int,
) -> dict:
    """
    构建分页响应，包裹在统一 APIResponse 中。

    使用:
        items = service.get_users(page=1, page_size=20)
        total = service.count_users()
        return success(data=paginate(items, total, 1, 20))
    """
    page_data = PageResponse.from_list(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )
    return page_data.model_dump()
