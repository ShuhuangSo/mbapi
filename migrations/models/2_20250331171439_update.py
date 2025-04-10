from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `orders` ADD `is_change_confirm` BOOL NOT NULL COMMENT '变更是否确认' DEFAULT 0;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `orders` DROP COLUMN `is_change_confirm`;"""
