"""phase2 初始化 sys_user 与 sys_operation_log 表

Revision ID: 20260813_0001
Revises:
Create Date: 2026-08-13

"""

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260813_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==========================================
    # sys_user — 系统用户表 (DESIGN.md 4.1.1)
    # ==========================================
    op.create_table(
        "sys_user",
        sa.Column(
            "id", sa.BigInteger(), autoincrement=True, nullable=False, comment="用户ID"
        ),
        sa.Column("username", sa.String(50), nullable=False, comment="用户名（工号）"),
        sa.Column(
            "password_hash", sa.String(255), nullable=False, comment="bcrypt 密码哈希"
        ),
        sa.Column("email", sa.String(100), nullable=True, comment="邮箱"),
        sa.Column("phone", sa.String(20), nullable=True, comment="手机号"),
        sa.Column("real_name", sa.String(50), nullable=True, comment="真实姓名"),
        sa.Column("department", sa.String(100), nullable=True, comment="部门"),
        sa.Column("position", sa.String(100), nullable=True, comment="职位"),
        sa.Column("avatar_url", sa.String(500), nullable=True, comment="头像URL"),
        sa.Column(
            "role",
            mysql.ENUM("admin", "employee"),
            nullable=False,
            server_default=sa.text("'employee'"),
            comment="角色: admin/employee",
        ),
        sa.Column(
            "status",
            mysql.TINYINT(),
            nullable=False,
            server_default=sa.text("'1'"),
            comment="状态: 1=启用 0=禁用",
        ),
        sa.Column(
            "last_login_at", sa.DateTime(), nullable=True, comment="最后登录时间"
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
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("idx_username", "sys_user", ["username"], unique=True)
    op.create_index("idx_department", "sys_user", ["department"])

    # ==========================================
    # sys_operation_log — 操作日志表 (DESIGN.md 4.1.9)
    # ==========================================
    op.create_table(
        "sys_operation_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True, comment="操作人ID"),
        sa.Column(
            "username", sa.String(50), nullable=True, comment="操作人用户名（冗余）"
        ),
        sa.Column("action", sa.String(100), nullable=False, comment="操作类型"),
        sa.Column("module", sa.String(100), nullable=True, comment="操作模块"),
        sa.Column("target_type", sa.String(50), nullable=True, comment="目标类型"),
        sa.Column("target_id", sa.String(100), nullable=True, comment="目标ID"),
        sa.Column("detail", sa.JSON(), nullable=True, comment="操作详情"),
        sa.Column("ip_address", sa.String(50), nullable=True, comment="IP地址"),
        sa.Column("user_agent", sa.String(500), nullable=True, comment="UserAgent"),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'success'"),
            comment="success / failed",
        ),
        sa.Column("error_info", sa.Text(), nullable=True, comment="错误信息"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="创建时间",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["sys_user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("idx_ol_user", "sys_operation_log", ["user_id"])
    op.create_index("idx_ol_module", "sys_operation_log", ["module"])
    op.create_index("idx_ol_created", "sys_operation_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_ol_created", table_name="sys_operation_log")
    op.drop_index("idx_ol_module", table_name="sys_operation_log")
    op.drop_index("idx_ol_user", table_name="sys_operation_log")
    op.drop_table("sys_operation_log")

    op.drop_index("idx_department", table_name="sys_user")
    op.drop_index("idx_username", table_name="sys_user")
    op.drop_table("sys_user")
