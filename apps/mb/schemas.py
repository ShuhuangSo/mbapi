from pydantic import BaseModel, field_serializer
from datetime import datetime
from typing import Optional, List


class OrderItem(BaseModel):
    # 商品基础信息
    sku: Optional[str] = None
    item_name: Optional[str] = None
    item_qty: Optional[int] = None
    image_url: Optional[str] = None

    # 平台属性
    platform_property: Optional[str] = None
    item_id: Optional[str] = None
    item_url: Optional[str] = None

    class Config:
        from_attributes = True


class OrdersForm(BaseModel):
    # 主订单信息
    order_number: Optional[str] = None
    paid_time: Optional[datetime] = None
    platform: Optional[str] = None
    store_name: Optional[str] = None
    order_status: Optional[str] = None
    currency: Optional[str] = None
    order_price_f: Optional[float] = None

    # 商品列表
    order_items: List[OrderItem] = []

    @field_serializer('paid_time')
    def format_datetime(self, dt: datetime) -> str:
        return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None  # type: ignore

    class Config:
        from_attributes = True
