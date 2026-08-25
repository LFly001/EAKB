"""
知识库分类服务
树形查询 / CRUD / 拖拽排序 / 父子级递归 / 删除守卫
"""

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import KbCategory
from app.models.document import KbDocument
from app.models.user import SysUser
from app.schemas.category import (
    CategoryCreate,
    CategoryInfo,
    CategoryMoveRequest,
    CategoryTreeNode,
    CategoryUpdate,
)
from app.utils.exceptions import BadRequestException, NotFoundException


class CategoryService:
    """知识库分类业务服务"""

    # ==========================================
    # 树形查询
    # ==========================================

    @staticmethod
    async def get_tree(db: AsyncSession) -> list[CategoryTreeNode]:
        """
        全量分类树 (按 sort_order 排序, 递归组装 children)。

        同时统计各分类下未删除文档数量, 用于前端展示与删除守卫提示。
        """
        result = await db.execute(
            select(KbCategory).order_by(
                KbCategory.sort_order.asc(), KbCategory.id.asc()
            )
        )
        categories = list(result.scalars().all())

        # 文档数量统计 (仅未删除文档)
        count_rows = (
            await db.execute(
                select(KbDocument.category_id, func.count(KbDocument.id))
                .where(KbDocument.status != -1)
                .group_by(KbDocument.category_id)
            )
        ).all()
        doc_counts: dict[int, int] = {row[0]: row[1] for row in count_rows}

        # 组装树 (注意: 不能用 model_validate 直接从 ORM 转换,
        # 否则会顺着 children relationship 递归展开导致重复)
        nodes: dict[int, CategoryTreeNode] = {}
        for cat in categories:
            info = CategoryInfo.model_validate(cat)
            nodes[cat.id] = CategoryTreeNode(
                **info.model_dump(),
                document_count=doc_counts.get(cat.id, 0),
            )

        roots: list[CategoryTreeNode] = []
        for cat in categories:
            node = nodes[cat.id]
            if cat.parent_id is not None and cat.parent_id in nodes:
                nodes[cat.parent_id].children.append(node)
            else:
                roots.append(node)

        return roots

    @staticmethod
    async def get_flat_list(db: AsyncSession) -> list[KbCategory]:
        """全量分类平铺列表 (下拉选择使用)"""
        result = await db.execute(
            select(KbCategory).order_by(
                KbCategory.sort_order.asc(), KbCategory.id.asc()
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_subtree_ids(db: AsyncSession, category_id: int) -> list[int]:
        """
        递归收集某分类自身 + 所有子孙分类 ID。
        文档按父分类过滤时同时命中子分类文档。
        """
        categories = await CategoryService.get_flat_list(db)
        children_map: dict[int | None, list[int]] = {}
        for cat in categories:
            children_map.setdefault(cat.parent_id, []).append(cat.id)

        ids: list[int] = []
        stack = [category_id]
        while stack:
            current = stack.pop()
            if current in ids:
                continue
            ids.append(current)
            stack.extend(children_map.get(current, []))
        return ids

    # ==========================================
    # 基础查询 / CRUD
    # ==========================================

    @staticmethod
    async def get_by_id(db: AsyncSession, category_id: int) -> KbCategory:
        """按 ID 查询分类, 不存在 → 404"""
        result = await db.execute(
            select(KbCategory).where(KbCategory.id == category_id)
        )
        category = result.scalar_one_or_none()
        if category is None:
            raise NotFoundException("分类不存在")
        return category

    @staticmethod
    async def create(
        db: AsyncSession,
        req: CategoryCreate,
        user: SysUser,
    ) -> KbCategory:
        """创建分类 (父分类存在性校验)"""
        if req.parent_id is not None:
            await CategoryService.get_by_id(db, req.parent_id)

        category = KbCategory(
            name=req.name,
            parent_id=req.parent_id,
            description=req.description,
            icon=req.icon,
            sort_order=req.sort_order,
            status=1,
            created_by=user.id,
        )
        db.add(category)
        await db.commit()
        await db.refresh(category)
        logger.info(f"[分类] 创建成功: {category.name} (id={category.id})")
        return category

    @staticmethod
    async def update(
        db: AsyncSession,
        category_id: int,
        req: CategoryUpdate,
    ) -> KbCategory:
        """更新分类 (父分类合法性校验: 不能是自身或自己的子孙)"""
        category = await CategoryService.get_by_id(db, category_id)

        if req.parent_id is not None:
            await CategoryService._validate_parent(db, category_id, req.parent_id)

        data = req.model_dump(exclude_unset=True)
        for field, value in data.items():
            setattr(category, field, value)

        await db.commit()
        await db.refresh(category)
        logger.info(f"[分类] 更新成功: id={category_id}")
        return category

    @staticmethod
    async def _validate_parent(
        db: AsyncSession,
        category_id: int,
        new_parent_id: int,
    ) -> None:
        """
        父分类合法性校验 (update / move 共用):
        - 不能是分类自身
        - 不能是自己的子孙节点 (否则形成环)
        """
        if new_parent_id == category_id:
            raise BadRequestException("父分类不能是分类自身")

        cursor: KbCategory | None = await CategoryService.get_by_id(db, new_parent_id)
        # 沿祖先链向上回溯, 校验目标不是自己的子孙
        while cursor is not None and cursor.parent_id is not None:
            if cursor.id == category_id:
                raise BadRequestException("不能将分类移动到自己的子分类下")
            cursor = (
                await db.execute(
                    select(KbCategory).where(KbCategory.id == cursor.parent_id)
                )
            ).scalar_one_or_none()

    @staticmethod
    async def move(
        db: AsyncSession,
        category_id: int,
        req: CategoryMoveRequest,
    ) -> KbCategory:
        """
        拖拽排序: 变更父分类 / 同级排序值。
        - 仅传 sort_order 时保持原父级 (同层级内排序)
        - 禁止移动到自己的子孙节点下 (会产生环)
        - 同级编号压缩为 0..n-1, 避免前端下标与既有 sort_order 撞值
        """
        category = await CategoryService.get_by_id(db, category_id)

        data = req.model_dump(exclude_unset=True)
        new_parent_id = data.get("parent_id")
        if new_parent_id is not None:
            await CategoryService._validate_parent(db, category_id, new_parent_id)
            category.parent_id = new_parent_id

        # 同级重排: 将目标插入 sort_order 位置, 同级编号重排为连续值
        if "sort_order" in data or "parent_id" in data:
            siblings = list(
                (
                    await db.execute(
                        select(KbCategory)
                        .where(
                            KbCategory.parent_id == category.parent_id,
                            KbCategory.id != category_id,
                        )
                        .order_by(KbCategory.sort_order.asc(), KbCategory.id.asc())
                    )
                )
                .scalars()
                .all()
            )
            target = data.get("sort_order")
            target = (
                len(siblings) if target is None else max(0, min(target, len(siblings)))
            )
            siblings.insert(target, category)
            for index, sibling in enumerate(siblings):
                sibling.sort_order = index

        await db.commit()
        await db.refresh(category)
        logger.info(
            f"[分类] 移动成功: id={category_id}, parent_id={category.parent_id}, "
            f"sort_order={category.sort_order}"
        )
        return category

    @staticmethod
    async def delete(db: AsyncSession, category_id: int) -> KbCategory:
        """
        删除分类 (物理删除, 带守卫):
        - 存在未删除子分类 → 拒绝
        - 分类下存在未删除文档 → 拒绝
        """
        category = await CategoryService.get_by_id(db, category_id)

        # 守卫 1: 子分类
        child_count = (
            await db.execute(
                select(func.count(KbCategory.id)).where(
                    KbCategory.parent_id == category_id
                )
            )
        ).scalar() or 0
        if child_count > 0:
            raise BadRequestException("该分类存在子分类，请先删除子分类")

        # 守卫 2: 文档
        doc_count = (
            await db.execute(
                select(func.count(KbDocument.id)).where(
                    KbDocument.category_id == category_id,
                    KbDocument.status != -1,
                )
            )
        ).scalar() or 0
        if doc_count > 0:
            raise BadRequestException(
                f"该分类下存在 {doc_count} 篇文档，请先删除或移动文档"
            )

        name = category.name
        await db.delete(category)
        await db.commit()
        logger.info(f"[分类] 删除成功: {name} (id={category_id})")
        return category
