from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `aerich` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `version` VARCHAR(255) NOT NULL,
    `app` VARCHAR(100) NOT NULL,
    `content` JSON NOT NULL
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `orders` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `order_number` VARCHAR(30) COMMENT '订单编号',
    `is_refund` BOOL COMMENT '是否已退款' DEFAULT 0,
    `order_id` VARCHAR(30) COMMENT '订单ID',
    `platform_number` VARCHAR(30) COMMENT '交易编号',
    `platform_status` VARCHAR(20) COMMENT '平台订单状态',
    `order_note` VARCHAR(600) COMMENT '订单备注',
    `paid_time` DATETIME(6) COMMENT '付款时间',
    `order_sent_time` DATETIME(6) COMMENT '发货时间',
    `create_time` DATETIME(6) COMMENT '创建时间',
    `carrier_company` VARCHAR(50) COMMENT '物流公司',
    `carrier_name` VARCHAR(50) COMMENT '物流渠道',
    `selected_carrier` VARCHAR(100) COMMENT '买家自选物流方式',
    `tracking_number` VARCHAR(50) COMMENT '货运单号',
    `country_code` VARCHAR(10) COMMENT '国家二字码',
    `store_name` VARCHAR(50) COMMENT '店铺名',
    `platform` VARCHAR(30) COMMENT '平台',
    `order_weight` DOUBLE COMMENT '订单重量',
    `sku_total_qty` INT COMMENT 'SKU总数量',
    `order_status` VARCHAR(30) COMMENT '订单状态',
    `is_resent` BOOL COMMENT '是否重发订单' DEFAULT 0,
    `resent_reason` VARCHAR(100) COMMENT '重发原因',
    `resent_sn` VARCHAR(30) COMMENT '重发来源订单编号',
    `buyer_id` VARCHAR(100) COMMENT '客户账号',
    `buyer_name` VARCHAR(100) COMMENT '客户姓名',
    `phone` VARCHAR(20) COMMENT '电话1',
    `country` VARCHAR(50) COMMENT '国家',
    `state` VARCHAR(50) COMMENT '省/州',
    `city` VARCHAR(80) COMMENT '城市',
    `post_code` VARCHAR(20) COMMENT '邮政编码',
    `address` VARCHAR(200) COMMENT '邮寄地址',
    `email` VARCHAR(50) COMMENT '联系邮箱',
    `postage_in_f` DOUBLE COMMENT '原始运费金额',
    `postage_in_rmb` DOUBLE COMMENT '运费收入',
    `postage_out_rmb` DOUBLE COMMENT '支出运费',
    `platform_fee_f` DOUBLE COMMENT '平台交易费',
    `order_price_f` DOUBLE COMMENT '订单原始总金额',
    `order_price_rmb` DOUBLE COMMENT '订单总金额',
    `product_cost` DOUBLE COMMENT '商品总成本',
    `currency` VARCHAR(10) COMMENT '币种',
    `platform_fee_rmb` DOUBLE COMMENT '平台交易费(人民币)',
    `profit_rmb` DOUBLE COMMENT '订单利润',
    `profit_f` DOUBLE COMMENT '订单利润(原始货币)',
    `margin` DOUBLE COMMENT '订单利润率',
    `ad_fee_f` DOUBLE COMMENT '广告费(原始货币)',
    `ad_fee_rmb` DOUBLE COMMENT '广告费(人民币)',
    `ex_rate` DOUBLE COMMENT '汇率（原始货币）',
    `transaction_id` VARCHAR(30) COMMENT 'TransactionId',
    `platform_note` VARCHAR(600) COMMENT '平台备注'
) CHARACTER SET utf8mb4 COMMENT='订单表';
CREATE TABLE IF NOT EXISTS `order_items` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `platform_property` VARCHAR(150) COMMENT '平台SKU多属性',
    `item_id` VARCHAR(50) COMMENT '商品编号(ItemId)',
    `item_url` VARCHAR(200) COMMENT '平台链接',
    `sku` VARCHAR(30) COMMENT 'SKU',
    `item_name` VARCHAR(200) COMMENT '订单商品名称',
    `item_qty` INT COMMENT '商品数量',
    `image_url` VARCHAR(200) COMMENT 'SKU图片链接',
    `item_cost` DOUBLE COMMENT '商品成本',
    `order_id` INT NOT NULL,
    CONSTRAINT `fk_order_it_orders_b892ad0e` FOREIGN KEY (`order_id`) REFERENCES `orders` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='订单商品表';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """
