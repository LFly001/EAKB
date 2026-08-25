"""
知识图谱 Pydantic Schema — Phase 6
对齐 DESIGN.md 4.3 图模型 (Entity/Document/Category 节点,
BELONGS_TO/MENTIONS/RELATED_TO/SIMILAR_TO 关系) 与 6.7 接口
"""

from pydantic import BaseModel, Field

# ==========================================
# 请求体
# ==========================================


class GraphBuildRequest(BaseModel):
    """图谱构建请求: 无 document_id = 全量重建"""

    document_id: int | None = Field(
        default=None, ge=1, description="单文档重建的文档ID"
    )

    model_config = {"extra": "forbid"}


# ==========================================
# 实体查询
# ==========================================


class EntityListItem(BaseModel):
    """实体列表项 (GET /graph/entities/)"""

    name: str = Field(description="实体名称")
    type: str = Field(
        description="实体类型: Person/Org/Term/Product/Policy/Event/Location"
    )
    description: str = Field(default="", description="实体描述")
    aliases: list[str] = Field(default_factory=list, description="别名列表")
    mention_count: int = Field(default=0, description="被文档提及次数")


class EntityNeighbor(BaseModel):
    """实体关联邻居 (RELATED_TO 一跳)"""

    name: str = Field(description="邻居实体名称")
    type: str = Field(description="邻居实体类型")
    description: str = Field(default="", description="邻居实体描述")
    aliases: list[str] = Field(default_factory=list, description="邻居实体别名")
    relation_type: str = Field(description="关系类型")
    weight: float = Field(default=0.0, description="关系权重 0-1")


class EntityMentionDoc(BaseModel):
    """提及该实体的文档"""

    document_id: int = Field(description="文档ID (MySQL kb_document.id)")
    title: str = Field(description="文档标题")
    file_name: str = Field(description="原始文件名")
    count: int = Field(default=0, description="提及次数")
    positions: list[int] = Field(default_factory=list, description="命中分块下标列表")


class EntityDetailResponse(EntityListItem):
    """实体详情 (GET /graph/entities/{name})"""

    neighbors: list[EntityNeighbor] = Field(
        default_factory=list, description="关联实体"
    )
    documents: list[EntityMentionDoc] = Field(
        default_factory=list, description="提及文档"
    )


# ==========================================
# 画布/搜索 (GET /graph/search)
# ==========================================


class GraphNode(BaseModel):
    """统一图节点: Entity(id=name) / Document(id=doc_{id}) / Category(id=cat_{id})"""

    id: str = Field(description="画布内唯一 ID")
    node_type: str = Field(description="节点类型: Entity|Document|Category")
    label: str = Field(description="显示名称")
    type: str | None = Field(default=None, description="实体类型 (仅 Entity)")
    description: str | None = Field(default=None, description="实体描述 (仅 Entity)")
    aliases: list[str] = Field(default_factory=list, description="实体别名 (仅 Entity)")
    mention_count: int | None = Field(
        default=None, description="被提及次数 (仅 Entity)"
    )
    document_id: int | None = Field(default=None, description="文档ID (仅 Document)")
    title: str | None = Field(default=None, description="文档标题 (仅 Document)")
    file_name: str | None = Field(default=None, description="文件名 (仅 Document)")
    category_id: int | None = Field(
        default=None, description="分类ID (Document/Category)"
    )
    category_name: str | None = Field(
        default=None, description="分类名 (Document/Category)"
    )


class GraphEdge(BaseModel):
    """统一图边"""

    source: str = Field(description="源节点 ID")
    target: str = Field(description="目标节点 ID")
    edge_type: str = Field(
        description="边类型: RELATED_TO|MENTIONS|BELONGS_TO|SIMILAR_TO"
    )
    relation_type: str | None = Field(
        default=None, description="关系类型 (仅 RELATED_TO)"
    )
    weight: float | None = Field(default=None, description="关系权重 (仅 RELATED_TO)")
    count: int | None = Field(default=None, description="提及次数 (仅 MENTIONS)")
    score: float | None = Field(default=None, description="相似度 (仅 SIMILAR_TO)")


class GraphStats(BaseModel):
    """图谱统计 (按响应内实际数据计数)"""

    entity_count: int = Field(default=0, description="实体数")
    document_count: int = Field(default=0, description="文档数")
    category_count: int = Field(default=0, description="分类数")
    related_to_count: int = Field(default=0, description="RELATED_TO 边数")
    mentions_count: int = Field(default=0, description="MENTIONS 边数")
    similar_to_count: int = Field(default=0, description="SIMILAR_TO 边数")


class GraphSearchResponse(BaseModel):
    """图谱搜索/画布全景统一返回 (GET /graph/search)"""

    nodes: list[GraphNode] = Field(default_factory=list, description="节点列表")
    edges: list[GraphEdge] = Field(default_factory=list, description="边列表")
    stats: GraphStats = Field(default_factory=GraphStats, description="统计")
    truncated: bool = Field(default=False, description="节点数达上限被截断")
