"""
提示词模板服务 — Phase 4 核心业务
模板 CRUD / 分类绑定解绑 / 按分类筛选 / 热门统计 / 变量渲染

规则 (CLAUDE.md 提示词模板系统):
- 系统预置模板 is_system=1 禁止删除
- 模板变量仅支持 {{question}} / {{context}}, 渲染时自动替换
- pt_template_category UNIQUE(template_id, category_id), 同一模板不可重复绑定
"""

import re

from loguru import logger
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import KbCategory
from app.models.template import PtTemplate, PtTemplateCategory
from app.models.user import SysUser
from app.schemas.template import (
    TemplateBindRequest,
    TemplateCreate,
    TemplateInfo,
    TemplateListItem,
    TemplateQuery,
    TemplateRenderRequest,
    TemplateRenderResult,
    TemplateUpdate,
    TemplateVariables,
    default_variables_json,
    validate_template_content,
)
from app.services.category_service import CategoryService
from app.utils.exceptions import (
    BadRequestException,
    ForbiddenException,
    NotFoundException,
)

# ==========================================
# 渲染工具 — {{question}} / {{context}} 占位符替换
# (Phase 5 RAG 问答组装 Prompt 时复用)
# ==========================================

_PLACEHOLDER_RE = re.compile(r"\{\{\s*question\s*\}\}")
_CONTEXT_RE = re.compile(r"\{\{\s*context\s*\}\}")


def render_template_content(
    template_content: str,
    *,
    question: str,
    context: str = "",
) -> str:
    """
    渲染模板内容: 自动填充 {{question}} / {{context}} 占位符。

    模板中未出现某占位符时对应值不注入; 渲染结果中不残留占位符。
    """
    rendered = _CONTEXT_RE.sub(lambda _m: context, template_content)
    rendered = _PLACEHOLDER_RE.sub(lambda _m: question, rendered)
    return rendered


class TemplateService:
    """提示词模板业务服务"""

    # ==========================================
    # 查询
    # ==========================================

    @staticmethod
    async def get_by_id(db: AsyncSession, template_id: int) -> PtTemplate:
        """按 ID 查询模板, 不存在 → 404"""
        result = await db.execute(
            select(PtTemplate).where(PtTemplate.id == template_id)
        )
        template = result.scalar_one_or_none()
        if template is None:
            raise NotFoundException("提示词模板不存在")
        return template

    @staticmethod
    async def get_list(
        db: AsyncSession,
        query: TemplateQuery,
    ) -> tuple[list[TemplateListItem], int]:
        """
        模板分页列表:
        - keyword 模糊匹配 名称/描述/标签
        - category_id 过滤: 模板绑定该分类 (关联表) 或默认分类为该分类
        - is_system / tag / status 精确过滤
        """
        conditions: list = []

        if query.keyword:
            like = f"%{query.keyword}%"
            conditions.append(
                or_(
                    PtTemplate.name.like(like),
                    PtTemplate.description.like(like),
                    PtTemplate.tags.like(like),
                )
            )

        if query.category_id is not None:
            # 绑定分类 OR 默认分类命中
            bound_ids = select(PtTemplateCategory.template_id).where(
                PtTemplateCategory.category_id == query.category_id
            )
            conditions.append(
                or_(
                    PtTemplate.id.in_(bound_ids),
                    PtTemplate.category_id == query.category_id,
                )
            )

        if query.is_system is not None:
            conditions.append(PtTemplate.is_system == query.is_system)
        if query.tag:
            conditions.append(PtTemplate.tags.like(f"%{query.tag}%"))
        if query.status is not None:
            conditions.append(PtTemplate.status == query.status)

        total = (
            await db.execute(select(func.count(PtTemplate.id)).where(*conditions))
        ).scalar() or 0

        result = await db.execute(
            select(PtTemplate)
            .where(*conditions)
            .order_by(
                PtTemplate.is_system.desc(),
                PtTemplate.usage_count.desc(),
                PtTemplate.id.desc(),
            )
            .offset((query.page - 1) * query.page_size)
            .limit(query.page_size)
        )
        templates = list(result.scalars().all())

        return await TemplateService._to_list_items(db, templates), total

    @staticmethod
    async def get_detail(db: AsyncSession, template_id: int) -> TemplateInfo:
        """模板详情 (含完整内容 + 变量定义 + 绑定分类)"""
        template = await TemplateService.get_by_id(db, template_id)
        items = await TemplateService._to_list_items(db, [template])
        item = items[0]
        info = TemplateInfo(
            **item.model_dump(),
            template_content=template.template_content,
        )
        # variables: 无定义时返回标准结构
        info.variables = (
            TemplateVariables.model_validate(template.variables)
            if template.variables
            else TemplateVariables()
        )
        return info

    @staticmethod
    async def get_hot(
        db: AsyncSession,
        limit: int = 10,
        is_system: int | None = None,
    ) -> list[TemplateListItem]:
        """热门模板 — 按使用次数倒序 (仅启用状态)"""
        conditions = [PtTemplate.status == 1]
        if is_system is not None:
            conditions.append(PtTemplate.is_system == is_system)

        result = await db.execute(
            select(PtTemplate)
            .where(*conditions)
            .order_by(PtTemplate.usage_count.desc(), PtTemplate.id.asc())
            .limit(limit)
        )
        templates = list(result.scalars().all())
        return await TemplateService._to_list_items(db, templates)

    @staticmethod
    async def get_by_category(
        db: AsyncSession,
        category_id: int,
    ) -> list[TemplateListItem]:
        """
        按分类获取可用模板 (DESIGN.md 6.5 by-category, Phase 5 问答自动匹配用):
        - 模板绑定该分类 (关联表) 或默认分类为该分类
        - 仅启用状态, 绑定该分类的模板排在前面 (更精确的匹配优先)
        """
        await CategoryService.get_by_id(db, category_id)

        bound_ids = select(PtTemplateCategory.template_id).where(
            PtTemplateCategory.category_id == category_id
        )
        result = await db.execute(
            select(PtTemplate)
            .where(
                PtTemplate.status == 1,
                or_(
                    PtTemplate.id.in_(bound_ids),
                    PtTemplate.category_id == category_id,
                ),
            )
            .order_by(PtTemplate.usage_count.desc(), PtTemplate.id.asc())
        )
        templates = list(result.scalars().all())

        # 绑定该分类的模板优先 (默认分类命中的次之)
        bound_set = set(
            (
                await db.execute(
                    select(PtTemplateCategory.template_id).where(
                        PtTemplateCategory.category_id == category_id
                    )
                )
            )
            .scalars()
            .all()
        )
        templates.sort(key=lambda t: 0 if t.id in bound_set else 1)
        return await TemplateService._to_list_items(db, templates)

    @staticmethod
    async def _to_list_items(
        db: AsyncSession,
        templates: list[PtTemplate],
    ) -> list[TemplateListItem]:
        """ORM → TemplateListItem, 补充分类名 / 创建人 / 绑定分类冗余字段"""
        if not templates:
            return []

        template_ids = [t.id for t in templates]

        # 绑定分类 (关联表, 按绑定顺序)
        bind_rows = (
            await db.execute(
                select(PtTemplateCategory.template_id, PtTemplateCategory.category_id)
                .where(PtTemplateCategory.template_id.in_(template_ids))
                .order_by(PtTemplateCategory.id.asc())
            )
        ).all()
        bound_ids: dict[int, list[int]] = {}
        for row in bind_rows:
            bound_ids.setdefault(row[0], []).append(row[1])

        # 分类名称 (默认分类 + 绑定分类统一查询)
        needed_category_ids = {
            t.category_id for t in templates if t.category_id is not None
        } | {cid for ids in bound_ids.values() for cid in ids}
        category_map: dict[int, str] = {}
        if needed_category_ids:
            rows = (
                await db.execute(
                    select(KbCategory.id, KbCategory.name).where(
                        KbCategory.id.in_(needed_category_ids)
                    )
                )
            ).all()
            category_map = {row[0]: row[1] for row in rows}

        # 创建人用户名
        creator_ids = {t.created_by for t in templates if t.created_by is not None}
        user_map: dict[int, str] = {}
        if creator_ids:
            rows = (
                await db.execute(
                    select(SysUser.id, SysUser.username).where(
                        SysUser.id.in_(creator_ids)
                    )
                )
            ).all()
            user_map = {row[0]: row[1] for row in rows}

        items: list[TemplateListItem] = []
        for t in templates:
            info = TemplateListItem.model_validate(t)
            info.category_name = (
                category_map.get(t.category_id) if t.category_id else None
            )
            info.creator_name = user_map.get(t.created_by) if t.created_by else None
            ids = bound_ids.get(t.id, [])
            info.category_ids = ids
            info.category_names = [category_map.get(cid, f"#{cid}") for cid in ids]
            items.append(info)
        return items

    # ==========================================
    # CRUD
    # ==========================================

    @staticmethod
    async def create(
        db: AsyncSession,
        req: TemplateCreate,
        user: SysUser,
    ) -> PtTemplate:
        """创建用户自定义模板 (默认分类存在性校验, variables 缺省用标准结构)"""
        if req.category_id is not None:
            await CategoryService.get_by_id(db, req.category_id)

        try:
            validate_template_content(req.template_content)
        except ValueError as exc:
            raise BadRequestException(str(exc)) from exc

        template = PtTemplate(
            name=req.name,
            description=req.description,
            category_id=req.category_id,
            template_content=req.template_content,
            variables=(
                req.variables.model_dump()
                if req.variables is not None
                else default_variables_json()
            ),
            tags=req.tags,
            status=1 if req.status is None else req.status,
            is_system=0,
            created_by=user.id,
        )
        db.add(template)
        await db.commit()
        await db.refresh(template)
        logger.info(
            f"[模板] 创建成功: {template.name} (id={template.id}, by={user.username})"
        )
        return template

    @staticmethod
    async def update(
        db: AsyncSession,
        template_id: int,
        req: TemplateUpdate,
    ) -> PtTemplate:
        """更新模板 (仅更新传入字段; 系统模板允许编辑内容但不可删除)"""
        template = await TemplateService.get_by_id(db, template_id)

        data = req.model_dump(exclude_unset=True)
        if "category_id" in data and data["category_id"] is not None:
            await CategoryService.get_by_id(db, data["category_id"])
        if "template_content" in data:
            try:
                validate_template_content(data["template_content"])
            except ValueError as exc:
                raise BadRequestException(str(exc)) from exc

        for field, value in data.items():
            setattr(template, field, value)

        await db.commit()
        await db.refresh(template)
        logger.info(f"[模板] 更新成功: id={template_id}")
        return template

    @staticmethod
    async def delete(db: AsyncSession, template_id: int) -> PtTemplate:
        """
        删除模板 (物理删除, 关联绑定 CASCADE):
        - 系统预置模板 is_system=1 → 禁止删除 (403)
        """
        template = await TemplateService.get_by_id(db, template_id)

        if template.is_system == 1:
            raise ForbiddenException("系统预置模板不可删除")

        name = template.name
        await db.delete(template)
        await db.commit()
        logger.info(f"[模板] 删除成功: {name} (id={template_id})")
        return template

    @staticmethod
    async def increment_usage(db: AsyncSession, template_id: int) -> None:
        """
        使用次数 +1 (Phase 5 问答使用模板时调用)。
        模板不存在时静默忽略, 不阻断问答主流程。
        """
        result = await db.execute(
            select(PtTemplate).where(PtTemplate.id == template_id)
        )
        template = result.scalar_one_or_none()
        if template is None:
            return
        template.usage_count = (template.usage_count or 0) + 1
        await db.commit()

    # ==========================================
    # 分类绑定 / 解绑
    # ==========================================

    @staticmethod
    async def bind_categories(
        db: AsyncSession,
        template_id: int,
        req: TemplateBindRequest,
    ) -> list[int]:
        """
        批量绑定分类 (追加语义):
        - 已绑定的分类跳过 (UNIQUE 约束兜底)
        - 全部分类存在性校验, 任一不存在整体拒绝
        返回绑定后的完整分类ID列表
        """
        await TemplateService.get_by_id(db, template_id)

        category_ids: list[int] = []
        for cid in req.category_ids:
            if cid not in category_ids:
                category_ids.append(cid)
        if category_ids:
            rows = (
                (
                    await db.execute(
                        select(KbCategory.id).where(KbCategory.id.in_(category_ids))
                    )
                )
                .scalars()
                .all()
            )
            existing = set(rows)
            missing = [cid for cid in category_ids if cid not in existing]
            if missing:
                raise BadRequestException(f"分类不存在: {missing}")

        # 已绑定集合
        bound = set(
            (
                await db.execute(
                    select(PtTemplateCategory.category_id).where(
                        PtTemplateCategory.template_id == template_id
                    )
                )
            )
            .scalars()
            .all()
        )

        added = 0
        for cid in category_ids:
            if cid in bound:
                continue
            db.add(PtTemplateCategory(template_id=template_id, category_id=cid))
            bound.add(cid)
            added += 1

        await db.commit()
        logger.info(
            f"[模板] 绑定分类: template_id={template_id}, 新增 {added} 个, 共 {len(bound)} 个"
        )
        return sorted(bound)

    @staticmethod
    async def set_categories(
        db: AsyncSession,
        template_id: int,
        req: TemplateBindRequest,
    ) -> list[int]:
        """
        设置分类 (整体替换语义): 解绑不在列表中的分类, 绑定列表中的分类。
        前端表单保存时调用, 一次对齐最终绑定关系。
        """
        await TemplateService.get_by_id(db, template_id)

        category_ids: list[int] = []
        for cid in req.category_ids:
            if cid not in category_ids:
                category_ids.append(cid)
        if category_ids:
            rows = (
                (
                    await db.execute(
                        select(KbCategory.id).where(KbCategory.id.in_(category_ids))
                    )
                )
                .scalars()
                .all()
            )
            existing = set(rows)
            missing = [cid for cid in category_ids if cid not in existing]
            if missing:
                raise BadRequestException(f"分类不存在: {missing}")

        target = set(category_ids)
        bound_rows = (
            (
                await db.execute(
                    select(PtTemplateCategory).where(
                        PtTemplateCategory.template_id == template_id
                    )
                )
            )
            .scalars()
            .all()
        )

        removed = 0
        added = 0
        for row in bound_rows:
            if row.category_id not in target:
                await db.delete(row)
                removed += 1
            else:
                target.discard(row.category_id)
        for cid in target:
            db.add(PtTemplateCategory(template_id=template_id, category_id=cid))
            added += 1

        await db.commit()
        logger.info(
            f"[模板] 设置分类: template_id={template_id}, "
            f"新增 {added} 个, 移除 {removed} 个, 共 {len(category_ids)} 个"
        )
        return category_ids

    @staticmethod
    async def unbind_category(
        db: AsyncSession,
        template_id: int,
        category_id: int,
    ) -> None:
        """解绑单个分类 (未绑定时不报错, 幂等)"""
        await TemplateService.get_by_id(db, template_id)

        row = (
            await db.execute(
                select(PtTemplateCategory).where(
                    PtTemplateCategory.template_id == template_id,
                    PtTemplateCategory.category_id == category_id,
                )
            )
        ).scalar_one_or_none()
        if row is not None:
            await db.delete(row)
            await db.commit()
            logger.info(
                f"[模板] 解绑分类: template_id={template_id}, category_id={category_id}"
            )

    # ==========================================
    # 渲染 (预览 / Phase 5 问答复用)
    # ==========================================

    @staticmethod
    async def render(
        db: AsyncSession,
        template_id: int,
        req: TemplateRenderRequest,
    ) -> TemplateRenderResult:
        """渲染模板 — 填充 {{question}}/{{context}} 生成完整 Prompt (预览/测试用)"""
        template = await TemplateService.get_by_id(db, template_id)

        if template.status != 1:
            raise BadRequestException("模板已禁用，无法使用")

        rendered = render_template_content(
            template.template_content,
            question=req.question,
            context=req.context,
        )
        return TemplateRenderResult(
            template_id=template.id,
            template_name=template.name,
            variables={"question": req.question, "context": req.context},
            rendered=rendered,
        )
