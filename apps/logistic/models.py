from tortoise.models import Model
from tortoise import fields


# 物流分区
class AreaCode(Model):
    id = fields.IntField(pk=True)
    country_code = fields.CharField(max_length=5,
                                    null=True,
                                    description="国家二字码")
    name = fields.CharField(max_length=20, null=True, description="物流渠道名称")
    ship_code = fields.CharField(max_length=20,
                                 null=True,
                                 description="物流渠道代码")
    post_code = fields.CharField(max_length=10, null=True, description="邮编")
    area = fields.CharField(max_length=10, null=True, description="区域")
    is_service = fields.BooleanField(default=True, description="是否服务")

    def __str__(self):
        return self.name

    class Meta:
        table = "area_code"
        table_description = "物流分区表"


# 物流价格
class PostPrice(Model):
    id = fields.IntField(pk=True)
    country_code = fields.CharField(max_length=5,
                                    null=True,
                                    description="国家二字码")
    carrier_name = fields.CharField(max_length=20,
                                    null=True,
                                    description="物流渠道名称")
    carrier_code = fields.CharField(max_length=20,
                                    null=True,
                                    description="物流渠道代码")
    area = fields.CharField(max_length=10, null=True, description="区域")
    is_elec = fields.BooleanField(default=False, description="是否带电")
    min_weight = fields.IntField(null=True, description="最小重量g")
    max_weight = fields.IntField(null=True, description="最大重量g")
    basic_price = fields.FloatField(null=True, description="基础价格")
    calc_price = fields.FloatField(null=True, description="计算价格")
    volume_ratio = fields.IntField(null=True, description="体积计算率")

    def __str__(self):
        return self.carrier_name

    class Meta:
        table = "post_price"
        table_description = "物流价格表"
