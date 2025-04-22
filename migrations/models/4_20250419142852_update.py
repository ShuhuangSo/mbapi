from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `area_code` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `platform_property` VARCHAR(150) COMMENT '平台SKU多属性',
    `country_code` VARCHAR(5) COMMENT '国家二字码',
    `name` VARCHAR(20) COMMENT '物流渠道名称',
    `ship_code` VARCHAR(20) COMMENT '物流渠道代码',
    `post_code` VARCHAR(10) COMMENT '邮编',
    `area` VARCHAR(10) COMMENT '区域',
    `is_service` BOOL NOT NULL COMMENT '是否服务' DEFAULT 1
) CHARACTER SET utf8mb4 COMMENT='物流分区表';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `area_code`;"""
