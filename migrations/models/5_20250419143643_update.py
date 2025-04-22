from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `area_code` DROP COLUMN `platform_property`;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `area_code` ADD `platform_property` VARCHAR(150) COMMENT '平台SKU多属性';"""
