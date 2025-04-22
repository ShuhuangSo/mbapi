from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `post_price` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `country_code` VARCHAR(5) COMMENT '国家二字码',
    `carrier_name` VARCHAR(20) COMMENT '物流渠道名称',
    `carrier_code` VARCHAR(20) COMMENT '物流渠道代码',
    `area` VARCHAR(10) COMMENT '区域',
    `is_elec` BOOL NOT NULL COMMENT '是否带电' DEFAULT 0,
    `min_weight` INT COMMENT '最小重量g',
    `max_weight` INT COMMENT '最大重量g',
    `basic_price` DOUBLE COMMENT '基础价格',
    `calc_price` DOUBLE COMMENT '计算价格',
    `volume_ratio` INT COMMENT '体积计算率'
) CHARACTER SET utf8mb4 COMMENT='物流价格表';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `post_price`;"""
