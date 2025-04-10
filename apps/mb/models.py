from tortoise.models import Model
from tortoise import fields


# 马帮订单表
class Orders(Model):
    id = fields.IntField(pk=True)
    # 基础信息
    order_number = fields.CharField(max_length=30,
                                    null=True,
                                    description="订单编号")
    is_refund = fields.BooleanField(default=False,
                                    null=True,
                                    description="是否已退款")
    is_change_confirm = fields.BooleanField(default=False,
                                            description="变更是否确认")
    order_id = fields.CharField(max_length=30, null=True, description="订单ID")
    platform_number = fields.CharField(max_length=30,
                                       null=True,
                                       description="交易编号")
    platform_status = fields.CharField(max_length=20,
                                       null=True,
                                       description="平台订单状态")
    order_note = fields.CharField(max_length=600,
                                  null=True,
                                  description="订单备注")

    # 时间信息
    paid_time = fields.DatetimeField(null=True, description="付款时间")
    order_sent_time = fields.DatetimeField(null=True, description="发货时间")
    create_time = fields.DatetimeField(null=True, description="创建时间")

    # 物流信息
    carrier_company = fields.CharField(max_length=50,
                                       null=True,
                                       description="物流公司")
    carrier_name = fields.CharField(max_length=50,
                                    null=True,
                                    description="物流渠道")
    selected_carrier = fields.CharField(max_length=100,
                                        null=True,
                                        description="买家自选物流方式")
    tracking_number = fields.CharField(max_length=50,
                                       null=True,
                                       description="货运单号")
    country_code = fields.CharField(max_length=10,
                                    null=True,
                                    description="国家二字码")

    # 店铺信息
    store_name = fields.CharField(max_length=50, null=True, description="店铺名")
    platform = fields.CharField(max_length=30, null=True, description="平台")

    # 商品信息
    order_weight = fields.FloatField(null=True, description="订单重量")
    sku_total_qty = fields.IntField(null=True, description="SKU总数量")

    # 订单状态
    order_status = fields.CharField(max_length=30,
                                    null=True,
                                    description="订单状态")
    is_resent = fields.BooleanField(default=False,
                                    null=True,
                                    description="是否重发订单")
    resent_reason = fields.CharField(max_length=100,
                                     null=True,
                                     description="重发原因")
    resent_sn = fields.CharField(max_length=30,
                                 null=True,
                                 description="重发来源订单编号")

    # 收件人信息
    buyer_id = fields.CharField(max_length=100, null=True, description="客户账号")
    buyer_name = fields.CharField(max_length=100,
                                  null=True,
                                  description="客户姓名")
    phone = fields.CharField(max_length=20, null=True, description="电话1")
    country = fields.CharField(max_length=50, null=True, description="国家")
    state = fields.CharField(max_length=50, null=True, description="省/州")
    city = fields.CharField(max_length=80, null=True, description="城市")
    post_code = fields.CharField(max_length=20, null=True, description="邮政编码")
    address = fields.CharField(max_length=200, null=True, description="邮寄地址")
    email = fields.CharField(max_length=50, null=True, description="联系邮箱")

    # 金额信息
    postage_in_f = fields.FloatField(null=True, description="原始运费金额")
    postage_in_rmb = fields.FloatField(null=True, description="运费收入")
    postage_out_rmb = fields.FloatField(null=True, description="支出运费")
    platform_fee_f = fields.FloatField(null=True, description="平台交易费")
    order_price_f = fields.FloatField(null=True, description="订单原始总金额")
    order_price_rmb = fields.FloatField(null=True, description="订单总金额")
    product_cost = fields.FloatField(null=True, description="商品总成本")
    currency = fields.CharField(max_length=10, null=True, description="币种")
    platform_fee_rmb = fields.FloatField(null=True, description="平台交易费(人民币)")
    profit_rmb = fields.FloatField(null=True, description="订单利润")
    profit_f = fields.FloatField(null=True, description="订单利润(原始货币)")
    margin = fields.FloatField(null=True, description="订单利润率")
    ad_fee_f = fields.FloatField(null=True, description="广告费(原始货币)")
    ad_fee_rmb = fields.FloatField(null=True, description="广告费(人民币)")
    ex_rate = fields.FloatField(null=True, description="汇率（原始货币）")

    transaction_id = fields.CharField(max_length=30,
                                      null=True,
                                      description="TransactionId")
    # 文本字段
    platform_note = fields.CharField(max_length=600,
                                     null=True,
                                     description="平台备注")

    def __str__(self):
        return self.order_number

    class Meta:
        table = "orders"
        table_description = "订单表"


# 马帮订单商品表
class OrderItems(Model):
    id = fields.IntField(pk=True)
    order = fields.ForeignKeyField("models.Orders",
                                   related_name="order_items",
                                   on_delete=fields.CASCADE)
    platform_property = fields.CharField(max_length=150,
                                         null=True,
                                         description="平台SKU多属性")
    item_id = fields.CharField(max_length=50,
                               null=True,
                               description="商品编号(ItemId)")
    item_url = fields.CharField(max_length=200, null=True, description="平台链接")
    sku = fields.CharField(max_length=30, null=True, description="SKU")
    item_name = fields.CharField(max_length=200,
                                 null=True,
                                 description="订单商品名称")
    item_qty = fields.IntField(null=True, description="商品数量")
    image_url = fields.CharField(max_length=200,
                                 null=True,
                                 description="SKU图片链接")
    item_cost = fields.FloatField(null=True, description="商品成本")

    def __str__(self):
        return self.sku

    class Meta:
        table = "items"
        table_description = "订单商品表"
