"""移除 AIOps 表名中重复的 aiops 前缀，保留原有数据和外键。"""

from alembic import op


revision = "0002_normalize_aiops_names"
down_revision = "0001_fastapi_initial"
branch_labels = None
depends_on = None

TABLE_RENAMES = (
    ("aiops_aiopsagentconfig", "aiops_agentconfig"),
    ("aiops_aiopschatmessage", "aiops_chatmessage"),
    ("aiops_aiopschatsession", "aiops_chatsession"),
    ("aiops_aiopsexternaltask", "aiops_externaltask"),
    ("aiops_aiopsknowledgeenvironment", "aiops_knowledgeenvironment"),
    ("aiops_aiopsmcpserver", "aiops_mcpserver"),
    ("aiops_aiopsmodelinvocation", "aiops_modelinvocation"),
    ("aiops_aiopsmodelprovider", "aiops_modelprovider"),
    ("aiops_aiopspendingaction", "aiops_pendingaction"),
    ("aiops_aiopsreviewknowledge", "aiops_reviewknowledge"),
    ("aiops_aiopsrunbook", "aiops_runbook"),
    ("aiops_aiopsrunbookversion", "aiops_runbookversion"),
    ("aiops_aiopsskill", "aiops_skill"),
    ("aiops_aiopstoolinvocation", "aiops_toolinvocation"),
)


def upgrade() -> None:
    """以一条 MySQL 原子重命名语句更新全部目标表，自动维护外键引用。"""
    pairs = ", ".join(f"`{old}` TO `{new}`" for old, new in TABLE_RENAMES)
    op.execute("RENAME TABLE " + pairs)


def downgrade() -> None:
    """恢复旧表名而不删除数据，供明确要求回退时使用。"""
    pairs = ", ".join(f"`{new}` TO `{old}`" for old, new in TABLE_RENAMES)
    op.execute("RENAME TABLE " + pairs)
