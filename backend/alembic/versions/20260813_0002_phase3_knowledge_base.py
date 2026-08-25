"""phase3 知识库分类 / 文档 / 分块 / 系统配置表

Revision ID: 20260813_0002
Revises: 20260813_0001
Create Date: 2026-08-13

Phase 3 建表:
- kb_category         知识库分类 (DESIGN.md 4.1.2, 树形结构)
- kb_document         知识库文档 (DESIGN.md 4.1.3)
- kb_document_chunk   文档分块记录 (DESIGN.md 4.1.4)
- sys_config          系统配置 (DESIGN.md 4.1.10, 提前建表: 分块参数需实时读取)
                      并写入 chunk_size / chunk_overlap 等种子配置
"""

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260813_0002"
down_revision = "20260813_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==========================================
    # kb_category — 知识库分类表 (DESIGN.md 4.1.2)
    # ==========================================
    op.create_table(
        "kb_category",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False, comment="分类名称"),
        sa.Column(
            "parent_id",
            sa.BigInteger(),
            nullable=True,
            comment="父分类ID（NULL=一级分类）",
        ),
        sa.Column("description", sa.Text(), nullable=True, comment="分类描述"),
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("'0'"),
            comment="同级排序值",
        ),
        sa.Column("icon", sa.String(255), nullable=True, comment="图标"),
        sa.Column(
            "status",
            mysql.TINYINT(),
            nullable=False,
            server_default=sa.text("'1'"),
            comment="状态: 1=启用 0=禁用",
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=True, comment="创建人ID"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=True,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="更新时间",
        ),
        sa.ForeignKeyConstraint(["parent_id"], ["kb_category.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["sys_user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("idx_cat_parent", "kb_category", ["parent_id"])
    op.create_index("idx_cat_sort", "kb_category", ["sort_order"])

    # ==========================================
    # kb_document — 知识库文档表 (DESIGN.md 4.1.3)
    # ==========================================
    op.create_table(
        "kb_document",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(255), nullable=False, comment="文档标题"),
        sa.Column("category_id", sa.BigInteger(), nullable=False, comment="所属分类ID"),
        sa.Column("file_name", sa.String(255), nullable=False, comment="原始文件名"),
        sa.Column(
            "file_type",
            sa.String(20),
            nullable=False,
            comment="文件类型 pdf/docx/txt/md/xlsx",
        ),
        sa.Column(
            "file_size", sa.BigInteger(), nullable=False, comment="文件大小(字节)"
        ),
        sa.Column(
            "file_path", sa.String(500), nullable=False, comment="MinIO 对象路径"
        ),
        sa.Column("file_hash", sa.String(64), nullable=True, comment="SHA256 去重"),
        sa.Column(
            "vector_status",
            mysql.ENUM("pending", "processing", "completed", "failed"),
            nullable=False,
            server_default=sa.text("'pending'"),
            comment="向量化状态: pending/processing/completed/failed",
        ),
        sa.Column(
            "chunk_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("'0'"),
            comment="分块数量",
        ),
        sa.Column("description", sa.Text(), nullable=True, comment="文档描述"),
        sa.Column("tags", sa.String(500), nullable=True, comment="标签（逗号分隔）"),
        sa.Column(
            "view_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("'0'"),
            comment="浏览次数",
        ),
        sa.Column(
            "download_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("'0'"),
            comment="下载次数",
        ),
        sa.Column(
            "status",
            mysql.TINYINT(),
            nullable=False,
            server_default=sa.text("'1'"),
            comment="状态: 1=发布 0=草稿 -1=已删除",
        ),
        sa.Column("uploaded_by", sa.BigInteger(), nullable=True, comment="上传人ID"),
        sa.Column(
            "vectorized_at", sa.DateTime(), nullable=True, comment="向量化完成时间"
        ),
        sa.Column(
            "error_message",
            sa.Text(),
            nullable=True,
            comment="向量化失败错误信息（支持重试排查）",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=True,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="更新时间",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"], ["kb_category.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["uploaded_by"], ["sys_user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("idx_doc_category", "kb_document", ["category_id"])
    op.create_index("idx_doc_status", "kb_document", ["status"])
    op.create_index("idx_doc_vector_status", "kb_document", ["vector_status"])
    op.create_index("idx_doc_file_hash", "kb_document", ["file_hash"])

    # ==========================================
    # kb_document_chunk — 文档分块记录表 (DESIGN.md 4.1.4)
    # ==========================================
    op.create_table(
        "kb_document_chunk",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.BigInteger(), nullable=False, comment="所属文档ID"),
        sa.Column("chunk_index", sa.Integer(), nullable=False, comment="分块序号"),
        sa.Column("chunk_text", sa.Text(), nullable=False, comment="分块文本"),
        sa.Column(
            "chunk_hash", sa.String(64), nullable=True, comment="分块文本哈希（去重）"
        ),
        sa.Column(
            "chroma_chunk_id",
            sa.String(255),
            nullable=True,
            comment="Chroma 中对应分块 ID",
        ),
        sa.Column(
            "token_count", sa.Integer(), nullable=True, comment="Token 数量（估算）"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="创建时间",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["kb_document.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("idx_chunk_document", "kb_document_chunk", ["document_id"])
    op.create_index("idx_chunk_chroma", "kb_document_chunk", ["chroma_chunk_id"])

    # ==========================================
    # sys_config — 系统配置表 (DESIGN.md 4.1.10)
    # ==========================================
    op.create_table(
        "sys_config",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("config_key", sa.String(100), nullable=False, comment="配置键"),
        sa.Column("config_value", sa.Text(), nullable=True, comment="配置值"),
        sa.Column(
            "config_type",
            sa.String(50),
            nullable=False,
            server_default=sa.text("'string'"),
            comment="值类型: string/json/number",
        ),
        sa.Column("description", sa.String(255), nullable=True, comment="配置说明"),
        sa.Column("updated_by", sa.BigInteger(), nullable=True, comment="更新人ID"),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=True,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="更新时间",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="创建时间",
        ),
        sa.ForeignKeyConstraint(["updated_by"], ["sys_user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("idx_config_key", "sys_config", ["config_key"], unique=True)

    # ---- 种子配置 (DESIGN.md 4.1.10 预置配置项) ----
    config_table = sa.table(
        "sys_config",
        sa.column("config_key", sa.String),
        sa.column("config_value", sa.String),
        sa.column("config_type", sa.String),
        sa.column("description", sa.String),
    )
    op.bulk_insert(
        config_table,
        [
            {
                "config_key": "default_model",
                "config_value": "gpt-4o",
                "config_type": "string",
                "description": "默认 LLM 模型名",
            },
            {
                "config_key": "chunk_size",
                "config_value": "512",
                "config_type": "number",
                "description": "文档分块大小",
            },
            {
                "config_key": "chunk_overlap",
                "config_value": "64",
                "config_type": "number",
                "description": "分块重叠大小",
            },
            {
                "config_key": "top_k",
                "config_value": "5",
                "config_type": "number",
                "description": "检索返回条数",
            },
            {
                "config_key": "similarity_threshold",
                "config_value": "0.7",
                "config_type": "number",
                "description": "相似度阈值",
            },
            {
                "config_key": "max_context_tokens",
                "config_value": "4096",
                "config_type": "number",
                "description": "上下文最大 Token 数",
            },
            {
                "config_key": "upload_max_size_mb",
                "config_value": "50",
                "config_type": "number",
                "description": "上传文件大小上限(MB)",
            },
        ],
    )


def downgrade() -> None:
    op.drop_index("idx_config_key", table_name="sys_config")
    op.drop_table("sys_config")

    op.drop_index("idx_chunk_chroma", table_name="kb_document_chunk")
    op.drop_index("idx_chunk_document", table_name="kb_document_chunk")
    op.drop_table("kb_document_chunk")

    op.drop_index("idx_doc_file_hash", table_name="kb_document")
    op.drop_index("idx_doc_vector_status", table_name="kb_document")
    op.drop_index("idx_doc_status", table_name="kb_document")
    op.drop_index("idx_doc_category", table_name="kb_document")
    op.drop_table("kb_document")

    op.drop_index("idx_cat_sort", table_name="kb_category")
    op.drop_index("idx_cat_parent", table_name="kb_category")
    op.drop_table("kb_category")
