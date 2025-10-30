from celery_app import celery_app
from datetime import datetime, timedelta
import requests
import math
from bs4 import BeautifulSoup

from apps.mb.models import Orders, OrderItems
import json
from pathlib import Path
from database import TORTOISE_ORM
from tortoise import Tortoise
from decimal import Decimal
from tortoise import connections
from tortoise.functions import Count
import asyncio
from config import config

# 通用时间解析函数，处理各种时间格式和时区信息
def robust_time_parse(time_str, default=None):
    """
    健壮的时间解析函数，能处理多种时间格式和时区信息
    支持格式：
    - YYYY-MM-DD HH:MM:SS
    - YYYY-MM-DD HH:MM
    - YYYY-MM-DD
    - 带有时区信息的格式如：YYYY-MM-DD HH:MM:SS(UTC+8)
    """
    if not time_str or time_str == '--':
        return default
    
    # 移除时区信息
    if '(UTC+8)' in time_str:
        time_str = time_str.replace(' (UTC+8)', '').replace('(UTC+8)', '')
    
    # 尝试不同的时间格式
    formats_to_try = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d"
    ]
    
    for fmt in formats_to_try:
        try:
            return datetime.strptime(time_str, fmt)
        except ValueError:
            continue
    
    # 如果都失败但格式看起来像 "HH:MM" 类型，尝试添加秒数
    if len(time_str.split(':')) == 2:
        try:
            return datetime.strptime(time_str + ':00', "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    
    # 最终尝试 - 对于只有日期和小时:分钟的格式
    if ' ' in time_str and len(time_str.split(' ')[1].split(':')) == 2:
        try:
            return datetime.strptime(time_str + ':00', "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    
    # 如果所有尝试都失败，返回默认值
    if default is not None:
        return default
    raise ValueError(f"无法解析时间字符串: {time_str}")


# 添加配置加载函数
def load_config():
    config_path = Path(__file__).parent.parent.parent / "mb_token.json"
    with open(config_path, 'r') as f:
        return json.load(f)


# 自定义时间获取mb订单任务
@celery_app.task
def get_orders_task(start_time, end_time):
    result = asyncio.run(get_mb_orders(start_time, end_time))
    return result


# 获取mb最近一周订单任务
@celery_app.task
def get_oneweek_orders():
    end_date = (datetime.now()).strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    # 转换日期格式
    start_time = datetime.strptime(start_date + " 00:00:00",
                                   "%Y-%m-%d %H:%M:%S")
    end_time = datetime.strptime(end_date + " 23:59:59", "%Y-%m-%d %H:%M:%S")
    result = asyncio.run(get_mb_orders(start_time, end_time))
    return result


async def get_mb_orders(start_time, end_time):
    """
    获取mb订单数据
    """
    # 初始化数据库连接
    await Tortoise.init(config=TORTOISE_ORM)

    try:
        # 获取第一页数据确定总页数
        first_page = send_order_requests(start_time, end_time, 1)
        soup = BeautifulSoup(first_page.content, 'html.parser')
        error_p = soup.find('p')

        if first_page.status_code != 200:
            return {"status": "error", "message": "获取订单失败"}
        if error_p and error_p.text == '错误原因：您的登录信息已超时，请刷新页面后重试':
            return {"status": "error", "message": "cookies过期"}

        orders_data = first_page.json()
        total_page = math.ceil(orders_data['pageCount'] / 500)
        all_orders = orders_data.get('orderDataList', [])

        # 获取剩余页数据
        for page in range(2, total_page + 1):
            response = send_order_requests(start_time, end_time, page)
            if response.status_code == 200:
                page_data = response.json()
                all_orders.extend(page_data.get('orderDataList', []))

        create_num = 0  # 新增订单数量
        update_num = 0  # 更新订单数量
        # 处理所有订单数据
        for order in all_orders:
            # 物流信息
            carrier_name = ''
            carrier_company = ''
            cansend1logisticsHtml = order['cansend1logisticsHtml']
            soup = BeautifulSoup(cansend1logisticsHtml, 'html.parser')
            p_tag = soup.find('p')
            if p_tag:
                text = p_tag.get_text()
                if text != '物流渠道未选择':
                    parts = text.split('[')
                    carrier_name = parts[0]
                    carrier_company = parts[1].replace(']', '')

            od = await Orders.filter(order_number=order['platformOrderId']
                                     ).first()
            mark_update = False  # 标记是否已更新订单
            if od:
                # 订单更新了发货状态 --> 更新所有可能变化的字段
                if od.order_status != order['showOrderStatusText'] and order[
                        'showOrderStatusText'] == '已发货':
                    od.order_status = order['showOrderStatusText']
                    # 使用全局健壮时间解析函数处理发货时间
                    if order['expressTime'] != '--':
                        if 'expressTimezone' in order and order['expressTimezone'] and order['expressTimezone'] != '--':
                            od.order_sent_time = robust_time_parse(order['expressTimezone'])  # type: ignore
                        else:
                            od.order_sent_time = robust_time_parse(order['expressTime'])  # type: ignore
                    else:
                        od.order_sent_time = None  # type: ignore
                    od.carrier_company = carrier_company  # 物流公司名称
                    od.carrier_name = carrier_name  # 承运商名称
                    od.tracking_number = order['trackNumber']  # 物流跟踪号
                    od.buyer_name = order['buyerName']  # 买家姓名
                    od.country = order['countryCodeEn']  # 国家(英文)
                    od.state = order['province']  # 省/州
                    od.city = order['city']  # 城市
                    od.post_code = order['postCode']  # 邮编
                    od.address = order['street1'] + order[
                        'street2']  # 地址(街道1+街道2)
                    od.email = order['email']  # 买家邮箱
                    od.order_note = order['orderRemarkText']  # 订单备注
                    od.is_change_confirm = True  # 变更是否确认
                    await od.save()
                    mark_update = True
                # 仅订单状态变化
                if od.order_status != order['showOrderStatusText']:
                    od.order_status = order['showOrderStatusText']
                    od.is_refund = True if order[
                        'isRefund'] == 1 else False  # 是否退款
                    await od.save()
                    mark_update = True
                # 仅物流信息变化
                if od.carrier_name != carrier_name or od.tracking_number != order[
                        'trackNumber']:
                    od.carrier_name = carrier_name  # 承运商名称
                    od.carrier_company = carrier_company  # 物流公司名称
                    od.tracking_number = order['trackNumber']  # 物流跟踪号
                    await od.save()
                    mark_update = True
                if mark_update:
                    update_num += 1  # 更新订单数量
                continue
            # 这里可以添加订单处理逻辑
            orders = Orders()
            # 订单基础信息
            orders.order_id = order['id']  # 订单ID（系统内部）
            orders.is_refund = True if order['isRefund'] == 1 else False  # 是否退款
            orders.order_number = order['platformOrderId']  # 平台订单号
            orders.platform_number = order['salesRecordNumber']  # 销售记录号
            orders.platform_status = order['platform_order_status']  # 平台订单状态
            if '_' in order['platformOrderId']:
                orders.is_resent = True  # 是否重发订单

            # 订单备注信息
            orders.order_note = order['orderRemarkText']  # 订单备注

            # 处理付款时间
            if 'paidTimeTimezone' in order and order['paidTimeTimezone'] and order['paidTimeTimezone'] != '--':
                orders.paid_time = robust_time_parse(order['paidTimeTimezone'])
            else:
                orders.paid_time = robust_time_parse(order['paidTime'])
            
            # 处理发货时间
            if order['expressTime'] != '--':
                if 'expressTimezone' in order and order['expressTimezone'] and order['expressTimezone'] != '--':
                    orders.order_sent_time = robust_time_parse(order['expressTimezone'])  # type: ignore
                else:
                    orders.order_sent_time = robust_time_parse(order['expressTime'])  # type: ignore
            else:
                orders.order_sent_time = None  # type: ignore
            
            # 处理创建时间
            if 'createDateTimezone' in order and order['createDateTimezone'] and order['createDateTimezone'] != '--':
                orders.create_time = robust_time_parse(order['createDateTimezone'])
            else:
                orders.create_time = robust_time_parse(order['createDate'])
            
            # 处理订单交付时间
            if 'orderDeliverTimezone' in order and order['orderDeliverTimezone'] and order['orderDeliverTimezone'] != '--':
                orders.order_deliver_time = robust_time_parse(order['orderDeliverTimezone'])  # type: ignore

            orders.carrier_company = carrier_company  # 物流公司名称
            orders.carrier_name = carrier_name  # 承运商名称
            orders.selected_carrier = order['shippingService']  # 选择的物流服务
            orders.tracking_number = order['trackNumber']  # 物流跟踪号

            # 店铺和平台信息
            orders.country_code = order['countryCode']  # 国家代码
            orders.store_name = order['shopIdText']  # 店铺名称
            orders.platform = order['platformIdText']  # 平台名称

            # 订单状态和重量
            orders.order_weight = order['orderWeight']  # 订单重量
            orders.order_status = order['showOrderStatusText']  # 订单状态显示文本

            # 买家信息
            orders.buyer_id = order['buyerUserId']  # 买家ID
            orders.buyer_name = order['buyerName']  # 买家姓名
            orders.country = order['countryCodeEn']  # 国家(英文)
            orders.state = order['province']  # 省/州
            orders.city = order['city']  # 城市
            orders.post_code = order['postCode']  # 邮编
            orders.address = order['street1'] + order['street2']  # 地址(街道1+街道2)
            orders.email = order['email']  # 买家邮箱

            # 价格信息
            # 在orders.save()之前添加以下转换逻辑
            orders.postage_in_f = float(order['shippingFee_original'].replace(
                ',', '')) if order['shippingFee_original'] else 0.0  # 原始运费(外币)
            orders.postage_in_rmb = float(order['shippingFee'].replace(
                ',', '')) if order['shippingFee'] else 0.0  # 运费(人民币)
            orders.postage_out_rmb = float(order['shippingCost'].replace(
                'RMB', '').replace(
                    ',',
                    '')) if order['shippingCost'] else 0.0  # 实际运费成本(去除RMB字符)
            orders.order_price_f = float(
                order['accountOrderFee_original'].replace(',', '')
            ) if order['accountOrderFee_original'] else 0.0  # 订单总价(外币)
            orders.order_price_rmb = float(order['accountOrderFee'].replace(
                ',', '')) if order['accountOrderFee'] else 0.0  # 订单总价(人民币)
            orders.currency = order['currencyId']  # 货币类型
            orders.profit_rmb = float(order['profit'].replace(
                ',', '')) if order['profit'] else 0.0  # 利润(人民币)
            orders.profit_f = float(order['profit_original'].replace(
                ',', '')) if order['profit_original'] else 0.0  # 利润(外币)

            orders.margin = order['profit_rate']  # 利润率

            # 平台备注
            orders.platform_note = order['buyerMessageText'][:500] if order[
                'buyerMessageText'] else None  # 买家留言/平台备注(截取前500字符)
            await orders.save()
            create_num += 1  # 新增订单数量+1

        id_list = []
        for order in all_orders:
            id_list.append(order['id'])

        # 分批处理并收集所有订单商品数据
        # 使用字典存储商品数据，键为订单ID
        all_items = {}
        batch_size = 1000  # 每批处理的订单数量
        for i in range(0, len(id_list), batch_size):
            batch_ids = id_list[i:i + batch_size]
            order_ids = ','.join(batch_ids)
            if order_ids:
                response = send_item_requests(order_ids)
                if response.status_code == 200:
                    order_items = response.json()
                    items = order_items.get('order_list_html_header', {})
                    # 合并字典数据
                    for order_id, item_data in items.items():
                        all_items[order_id] = item_data

        # 统一处理所有商品数据
        for order_id, items in all_items.items():
            od = await Orders.filter(order_id=order_id).first()
            if od:
                if od.is_change_confirm:
                    # 订单更新了发货状态 --> 删除所有商品数据，不管有没有变化，都重新
                    await OrderItems.filter(order=od).delete()
                    od.sku_total_qty = 0
                    od.is_change_confirm = False
                    await od.save()
                if od.sku_total_qty:
                    # 订单商品项已经更新过了，跳过
                    continue
                # 解析商品数据
                soup = BeautifulSoup(items, 'html.parser')
                tr_tags = soup.find_all('tr')
                for tr in tr_tags:
                    # 获取 SKU 编号
                    sku_tag = tr.find('a',
                                      attrs={"data-copy-id":
                                             "copySkuNumber"})  # type: ignore
                    sku = sku_tag.text  # type: ignore
                    # 获取图片
                    img_tag = tr.find('img')  # type: ignore
                    img_src = img_tag.get('src')  # type: ignore
                    # 获取数量
                    qty_tag = tr.find(
                        'span', class_='stock-product-nums')  # type: ignore
                    qty = qty_tag.text  # type: ignore
                    # 获取item id 和 url
                    item_id_tag = sku_tag.find_next('a')  # type: ignore
                    item_id = item_id_tag.text if item_id_tag else ''  # type: ignore
                    item_url = item_id_tag[
                        'href'] if item_id_tag else ''  # type: ignore
                    # 获取商品名称
                    item_name_tag = tr.find(
                        'span',  # type: ignore
                        attrs={"data-field": "productName"})  # type: ignore
                    item_name = item_name_tag['title']
                    # 获取商品规格
                    specifics_tag = tr.find('p',
                                            attrs={"data-field": "specifics"})
                    specifics = specifics_tag['data-original-title'].replace(
                        "<br/>", ",")
                    # 获取商品成本价格
                    price_td = tr.find('td', attrs={"data-field": "sellPrice"})
                    if price_td:
                        price_p = price_td.find('p')
                        if price_p:
                            price = price_p.text.strip()

                    await OrderItems.create(order=od,
                                            item_id=item_id,
                                            item_url=item_url,
                                            platform_property=specifics,
                                            sku=sku,
                                            item_name=item_name,
                                            item_qty=int(qty),
                                            image_url=img_src,
                                            item_cost=float(price))
                # 更新订单商品总数量
                od.sku_total_qty = len(tr_tags)
                await od.save()

        return {
            "status":
            "success",
            "message":
            f"获取到 {len(all_orders)} 个订单数据，新增 {create_num} 个，更新 {update_num} 个"
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        await Tortoise.close_connections()


# 发送请求获取订单数据
def send_order_requests(start_time, end_time, page):
    config = load_config()
    headers = {
        "cookie": config["cookie"],
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
    }
    form_data = {
        "queryTime": "paidTime",
        "startTime1": start_time,
        "endTime1": end_time,
        "page": page,
        "rowsPerPage": "500",
        "a": "orderalllist",
        "TextZx": "",
        "TextZd": "",
        "post_tableBase": "1"
    }
    # 定义API URL
    api_url = "https://vip.mabangerp.com/index.php?mod=order.oTc"
    # 发送GET请求
    response = requests.post(api_url, headers=headers, data=form_data)
    return response


# 发送请求获取订单商品数据
def send_item_requests(order_ids):
    config = load_config()
    headers = {
        "cookie": config["cookie"],
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
    }
    form_data = {"orderItemIq": order_ids, "tableBase": 2, "isAllList": 1}
    # 定义API URL
    api_url = "https://vip.mabangerp.com/index.php?mod=order.showOrderItems"
    # 发送GET请求
    response = requests.post(api_url, headers=headers, data=form_data)
    return response


@celery_app.task
def get_day_orders_report_task():
    """
    Celery任务版本 - 每日订单统计报告
    """

    async def _async_task():
        # 初始化数据库连接
        await Tortoise.init(config=TORTOISE_ORM)
        try:
            end_date = (datetime.now() -
                        timedelta(days=1)).strftime("%Y-%m-%d")
            start_date = (datetime.now() -
                          timedelta(days=2)).strftime("%Y-%m-%d")
            weekday = (datetime.now() - timedelta(days=1)).strftime(
                "%A")  # 获取周几（英文）
            weekday_cn = {
                'Monday': '星期一',
                'Tuesday': '星期二',
                'Wednesday': '星期三',
                'Thursday': '星期四',
                'Friday': '星期五',
                'Saturday': '星期六',
                'Sunday': '星期日'
            }.get(weekday, '未知')  # 转换为中文
            full_date = f"{end_date} {weekday_cn}"  # 组合日期和周几

            # 转换日期格式
            start_datetime = datetime.strptime(start_date + " 00:00:00",
                                               "%Y-%m-%d %H:%M:%S")
            end_datetime = datetime.strptime(end_date + " 23:59:59",
                                             "%Y-%m-%d %H:%M:%S")

            # 获取订单总量前8的店铺
            top_stores = await Orders.filter(
                paid_time__range=(start_datetime, end_datetime)
            ).annotate(
                count=Count("order_id")  # 使用正确的Count函数
            ).group_by("store_name").order_by("-count").limit(8).values_list(
                "store_name", flat=True)

            if not top_stores:
                return {"status": "error", "message": "订单数据为空"}

            # 使用原始SQL查询
            store_names = "','".join(top_stores)
            query = f"""
            SELECT
                DATE(paid_time) AS date,
                store_name,
                COUNT(id) AS count
            FROM orders
            WHERE
                paid_time BETWEEN '{start_datetime}' AND '{end_datetime}'
                AND store_name IN ('{store_names}')
            GROUP BY date, store_name
            ORDER BY date
            """

            connection = connections.get("default")
            results = await connection.execute_query_dict(query)

            # 格式化结果
            formatted_data = {}
            for row in results:
                date_str = row['date'].strftime("%Y-%m-%d")
                if date_str not in formatted_data:
                    formatted_data[date_str] = {}
                formatted_data[date_str][row['store_name']] = row['count']

            # 按店铺名整理数据，将多天销量用箭头连接起来
            store_stats_list = []
            for store in top_stores:
                daily_counts = []
                prev_count = None
                for date in sorted(formatted_data.keys()):
                    current_count = formatted_data[date].get(store, 0)
                    daily_counts.append(str(current_count))
                    if prev_count is not None and current_count < prev_count:
                        daily_counts[-1] += " ⬇️"  # 销量下降时添加标记
                    prev_count = current_count

                store_stats_list.append({
                    "store_name": store,
                    "od_qty": " → ".join(daily_counts)
                })

            # 获取end_date当天的总订单数量和总订单金额
            total_query = f"""
            SELECT 
                COUNT(order_id) AS total_count,
                SUM(order_price_rmb) AS total_amount
            FROM orders
            WHERE 
                DATE(paid_time) = '{end_date}'
            """
            total_result = await connection.execute_query_dict(total_query)
            total_stats = {
                "total_count":
                total_result[0]['total_count'] if total_result else 0,
                "total_amount":
                f"{float(total_result[0]['total_amount']):,.2f} 元" if
                total_result and total_result[0]['total_amount'] else "0.00 元"
            }

            # 获取end_date当天销量前10的商品
            top_products_query = f"""
            SELECT 
                oi.sku,
                oi.item_name,
                oi.image_url,
                SUM(oi.item_qty) AS total_qty
            FROM orders o
            JOIN items oi ON o.id = oi.order_id
            WHERE 
                DATE(o.paid_time) = '{end_date}'
            GROUP BY oi.sku, oi.item_name, oi.image_url
            ORDER BY total_qty DESC
            LIMIT 5
            """
            top_products = await connection.execute_query_dict(
                top_products_query)

            # 格式化商品数据
            formatted_products = []
            for product in top_products:
                formatted_products.append({
                    "sku":
                    product["sku"],
                    "item_name":
                    product["item_name"],
                    "image_url":
                    product["image_url"],
                    "total_qty":
                    int(product["total_qty"])
                })

            # 获取end_date当天按商品ID统计的订单数据(仅按item_id分组)
            item_stats_query = f"""
            SELECT 
                oi.item_id,
                oi.item_url,
                MAX(oi.item_name) AS item_name,  # 取任意一个item_name
                o.store_name,
                COUNT(DISTINCT o.id) AS order_count
            FROM orders o
            JOIN items oi ON o.id = oi.order_id
            WHERE 
                DATE(o.paid_time) = '{end_date}'
            GROUP BY oi.item_id  # 仅按item_id分组
            ORDER BY order_count DESC
            LIMIT 5
            """
            item_stats = await connection.execute_query_dict(item_stats_query)

            # 格式化商品ID数据
            formatted_items = []
            for item in item_stats:
                item_name = item["item_name"]  # 保留item_name但可能不准确
                # 保留前10个汉字，超过部分用...替代
                short_name = (item_name[:10] +
                              '...') if len(item_name) > 10 else item_name
                formatted_items.append({
                    "item_id": item["item_id"],
                    "item_url": item["item_url"],
                    "item_name": short_name,
                    "store_name": item["store_name"],
                    "order_count": item["order_count"]
                })

            # 获取end_date当天金额前5的订单
            top_orders_query = f"""
            SELECT 
                order_number,
                store_name,
                order_price_f,
                currency
            FROM orders
            WHERE 
                DATE(paid_time) = '{end_date}'
            ORDER BY order_price_rmb DESC
            LIMIT 5
            """
            top_orders = await connection.execute_query_dict(top_orders_query)

            # 格式化订单数据
            formatted_top_orders = []
            for order in top_orders:
                formatted_top_orders.append({
                    "order_number":
                    order["order_number"],
                    "store_name":
                    order["store_name"],
                    "order_price_f":
                    float(order["order_price_f"]),
                    "currency":
                    order["currency"]
                })

            # 获取end_date当天按物流商统计的订单数据
            carrier_stats_query = f"""
            SELECT 
                carrier_name,
                COUNT(order_id) AS order_count
            FROM orders
            WHERE 
                DATE(paid_time) = '{end_date}'
                AND carrier_name IS NOT NULL
            GROUP BY carrier_name
            ORDER BY order_count DESC
            """
            carrier_stats = await connection.execute_query_dict(
                carrier_stats_query)

            # 格式化物流商数据
            formatted_carriers = []
            for carrier in carrier_stats:
                formatted_carriers.append({
                    "carrier_name":
                    carrier["carrier_name"],
                    "order_count":
                    carrier["order_count"]
                })

            # 获取end_date当天按国家代码统计的订单数据
            country_stats_query = f"""
            SELECT 
                country_code,
                COUNT(order_id) AS order_count,
                SUM(order_price_rmb) AS total_amount
            FROM orders
            WHERE 
                DATE(paid_time) = '{end_date}'
                AND country_code IS NOT NULL
            GROUP BY country_code
            ORDER BY order_count DESC
            """
            country_stats = await connection.execute_query_dict(
                country_stats_query)

            # 格式化国家数据
            formatted_countries = []
            for country in country_stats:
                formatted_countries.append({
                    "type": country["country_code"],
                    "value": country["order_count"]
                })
            # 转换Decimal类型为float
            def convert_decimals(obj):
                if isinstance(obj, Decimal):
                    return float(obj)
                elif isinstance(obj, dict):
                    return {k: convert_decimals(v) for k, v in obj.items()}
                elif isinstance(obj, (list, tuple)):
                    return [convert_decimals(item) for item in obj]
                return obj

            import requests
            import json

            res = requests.post(
                headers={
                    "Authorization": "Bearer app-DhlGqIKpgBtZipEIkFwb4T3L"
                },
                url=config.MB_DAY_REPORT_URL,
                json={
                    "inputs": {
                        "report_type":
                        "DAY",
                        "store_order_stats":
                        json.dumps(convert_decimals(
                            store_stats_list)),  # 按店铺名整理的每日订单数据
                        "total_count":
                        total_stats["total_count"],  # 当天总订单数量
                        "total_amount":
                        total_stats["total_amount"],  # 当天总订单金额
                        "full_date":
                        full_date,  # 当天日期
                        "formatted_carriers":
                        json.dumps(convert_decimals(
                            formatted_carriers)),  # 当天按物流商统计的订单数据
                        "formatted_products":
                        json.dumps(
                            convert_decimals(formatted_products)),  # 当天销量前5的商品
                        "formatted_items":
                        json.dumps(convert_decimals(
                            formatted_items)),  # 当天按商品item_id统计的订单数据
                        "formatted_top_orders":
                        json.dumps(convert_decimals(
                            formatted_top_orders)),  # 当天金额前5的订单
                        "country_stats":
                        json.dumps(convert_decimals(
                            formatted_countries)),  # 当天按国家代码统计的订单数据
                        "formatted_data":
                        json.dumps(convert_decimals(formatted_data))  # 原始数据
                    },
                    "response_mode": "blocking",
                    "user": "abc-123"
                })

            if res.json()['data'].get("status") == "succeeded":
                return {"status": "success", "message": "订单日报发送成功"}
            else:
                return {"status": "error", "message": "订单日报发送失败"}

        except Exception as e:
            print(f"获取订单数据出错: {str(e)}")
            return {"status": "error", "message": str(e)}
        finally:
            await Tortoise.close_connections()

    # 运行异步函数并返回结果
    return asyncio.run(_async_task())


@celery_app.task
def get_week_orders_report_task():
    """
    Celery任务版本 - 每周订单统计报告
    """

    async def _async_task():
        # 初始化数据库连接
        await Tortoise.init(config=TORTOISE_ORM)
        try:
            # 获取上周一和上周日的日期
            today = datetime.now()
            last_sunday = today - timedelta(days=today.weekday() + 1)
            last_monday = last_sunday - timedelta(days=6)

            # 获取上上周一和上上周日的日期
            prev_week_sunday = last_monday - timedelta(days=1)
            prev_week_monday = prev_week_sunday - timedelta(days=6)

            # 转换日期格式
            start_datetime = last_monday.strftime("%Y-%m-%d") + " 00:00:00"
            end_datetime = last_sunday.strftime("%Y-%m-%d") + " 23:59:59"
            prev_start_datetime = prev_week_monday.strftime(
                "%Y-%m-%d") + " 00:00:00"
            prev_end_datetime = prev_week_sunday.strftime(
                "%Y-%m-%d") + " 23:59:59"

            # 获取上周总订单量前8的店铺
            top_stores = await Orders.filter(
                paid_time__range=(start_datetime, end_datetime)
            ).annotate(
                count=Count("order_id")
            ).group_by("store_name").order_by("-count").limit(8).values_list(
                "store_name", flat=True)

            if not top_stores:
                return {"status": "error", "message": "订单数据为空"}

            # 使用原始SQL查询两周的数据
            store_names = "','".join(top_stores)
            query = f"""
            SELECT
                DATE(paid_time) AS date,
                store_name,
                COUNT(id) AS count
            FROM orders
            WHERE
                (paid_time BETWEEN '{prev_start_datetime}' AND '{prev_end_datetime}'
                OR paid_time BETWEEN '{start_datetime}' AND '{end_datetime}')
                AND store_name IN ('{store_names}')
            GROUP BY date, store_name
            ORDER BY date
            """

            connection = connections.get("default")
            results = await connection.execute_query_dict(query)

            # 格式化结果
            formatted_data = {}
            for row in results:
                date_str = row['date'].strftime("%Y-%m-%d")
                if date_str not in formatted_data:
                    formatted_data[date_str] = {}
                formatted_data[date_str][row['store_name']] = row['count']

            # 按店铺名整理两周数据
            store_stats_list = []
            for store in top_stores:
                # 获取上上周和上周的总销量
                prev_week_total = sum(
                    row['count'] for row in results
                    if datetime.strptime(row['date'].strftime(
                        "%Y-%m-%d"), "%Y-%m-%d") >= datetime.strptime(
                            prev_week_monday.strftime("%Y-%m-%d"), "%Y-%m-%d")
                    and datetime.strptime(row['date'].strftime(
                        "%Y-%m-%d"), "%Y-%m-%d") <= datetime.strptime(
                            prev_week_sunday.strftime("%Y-%m-%d"), "%Y-%m-%d")
                    and row['store_name'] == store)

                last_week_total = sum(
                    row['count'] for row in results
                    if datetime.strptime(row['date'].strftime(
                        "%Y-%m-%d"), "%Y-%m-%d") >= datetime.strptime(
                            last_monday.strftime("%Y-%m-%d"), "%Y-%m-%d")
                    and datetime.strptime(row['date'].strftime(
                        "%Y-%m-%d"), "%Y-%m-%d") <= datetime.strptime(
                            last_sunday.strftime("%Y-%m-%d"), "%Y-%m-%d")
                    and row['store_name'] == store)

                # 添加趋势标记
                trend = ""
                if prev_week_total > 0 and last_week_total < prev_week_total:
                    trend = " ⬇️"

                store_stats_list.append({
                    "store_name":
                    store,
                    "od_qty":
                    f"{prev_week_total} → {last_week_total}{trend}"
                })

            # 获取上周总订单数量和总订单金额
            total_query = f"""
            SELECT 
                COUNT(order_id) AS total_count,
                SUM(order_price_rmb) AS total_amount
            FROM orders
            WHERE 
                paid_time BETWEEN '{start_datetime}' AND '{end_datetime}'
            """
            total_result = await connection.execute_query_dict(total_query)
            total_stats = {
                "total_count":
                total_result[0]['total_count'] if total_result else 0,
                "total_amount":
                f"{float(total_result[0]['total_amount']):,.2f} 元" if
                total_result and total_result[0]['total_amount'] else "0.00 元"
            }

            # 获取上周销量前10的商品
            top_products_query = f"""
            SELECT 
                oi.sku,
                oi.item_name,
                oi.image_url,
                SUM(oi.item_qty) AS total_qty
            FROM orders o
            JOIN items oi ON o.id = oi.order_id
            WHERE 
                o.paid_time BETWEEN '{start_datetime}' AND '{end_datetime}'
            GROUP BY oi.sku, oi.item_name, oi.image_url
            ORDER BY total_qty DESC
            LIMIT 10
            """
            top_products = await connection.execute_query_dict(
                top_products_query)

            # 格式化商品数据
            formatted_products = []
            for product in top_products:
                formatted_products.append({
                    "sku":
                    product["sku"],
                    "item_name":
                    product["item_name"],
                    "image_url":
                    product["image_url"],
                    "total_qty":
                    int(product["total_qty"])
                })

            # 获取上周按商品ID统计的订单数据(仅按item_id分组)
            item_stats_query = f"""
            SELECT 
                oi.item_id,
                oi.item_url,
                MAX(oi.item_name) AS item_name,
                o.store_name,
                COUNT(DISTINCT o.id) AS order_count
            FROM orders o
            JOIN items oi ON o.id = oi.order_id
            WHERE 
                o.paid_time BETWEEN '{start_datetime}' AND '{end_datetime}'
            GROUP BY oi.item_id
            ORDER BY order_count DESC
            LIMIT 10
            """
            item_stats = await connection.execute_query_dict(item_stats_query)

            # 格式化商品ID数据
            formatted_items = []
            for item in item_stats:
                item_name = item["item_name"]  # 保留item_name但可能不准确
                # 保留前10个汉字，超过部分用...替代
                short_name = (item_name[:10] +
                              '...') if len(item_name) > 10 else item_name
                formatted_items.append({
                    "item_id": item["item_id"],
                    "item_url": item["item_url"],
                    "item_name": short_name,
                    "store_name": item["store_name"],
                    "order_count": item["order_count"]
                })

            # 获取上周金额前5的订单
            top_orders_query = f"""
            SELECT 
                order_number,
                store_name,
                order_price_f,
                currency
            FROM orders
            WHERE 
                paid_time BETWEEN '{start_datetime}' AND '{end_datetime}'
            ORDER BY order_price_rmb DESC
            LIMIT 5
            """
            top_orders = await connection.execute_query_dict(top_orders_query)

            # 格式化订单数据
            formatted_top_orders = []
            for order in top_orders:
                formatted_top_orders.append({
                    "order_number":
                    order["order_number"],
                    "store_name":
                    order["store_name"],
                    "order_price_f":
                    float(order["order_price_f"]),
                    "currency":
                    order["currency"]
                })

            # 获取上周按物流商统计的订单数据
            carrier_stats_query = f"""
            SELECT 
                carrier_name,
                COUNT(order_id) AS order_count
            FROM orders
            WHERE 
                paid_time BETWEEN '{start_datetime}' AND '{end_datetime}'
                AND carrier_name IS NOT NULL
            GROUP BY carrier_name
            ORDER BY order_count DESC
            """
            carrier_stats = await connection.execute_query_dict(
                carrier_stats_query)

            # 格式化物流商数据
            formatted_carriers = []
            for carrier in carrier_stats:
                formatted_carriers.append({
                    "carrier_name":
                    carrier["carrier_name"],
                    "order_count":
                    carrier["order_count"]
                })

            # 先获取上周订单量前8的店铺
            top_stores_query = f"""
            SELECT store_name
            FROM orders
            WHERE paid_time BETWEEN '{start_datetime}' AND '{end_datetime}'
            GROUP BY store_name
            ORDER BY COUNT(order_id) DESC
            LIMIT 6
            """
            top_stores_result = await connection.execute_query_dict(
                top_stores_query)
            top_store_names = [
                store['store_name'] for store in top_stores_result
            ]

            # 获取这些店铺上周每日订单数据
            account_daily_query = f"""
            SELECT 
                store_name AS account,
                DAYNAME(paid_time) AS weekday,
                COUNT(order_id) AS order_count
            FROM orders
            WHERE 
                paid_time BETWEEN '{start_datetime}' AND '{end_datetime}'
                AND store_name IN ('{"','".join(top_store_names)}')
            GROUP BY store_name, DAYNAME(paid_time)
            ORDER BY store_name, FIELD(weekday, 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')
            """
            account_daily_stats = await connection.execute_query_dict(
                account_daily_query)

            # 格式化账号每日数据
            formatted_account_daily = []
            weekday_cn_map = {
                'Monday': '周一',
                'Tuesday': '周二',
                'Wednesday': '周三',
                'Thursday': '周四',
                'Friday': '周五',
                'Saturday': '周六',
                'Sunday': '周日'
            }
            for stat in account_daily_stats:
                formatted_account_daily.append({
                    "account":
                    stat["account"],
                    "type":
                    weekday_cn_map.get(stat["weekday"], stat["weekday"]),
                    "value":
                    stat["order_count"]
                })

            # 转换Decimal类型为float
            def convert_decimals(obj):
                if isinstance(obj, Decimal):
                    return float(obj)
                elif isinstance(obj, dict):
                    return {k: convert_decimals(v) for k, v in obj.items()}
                elif isinstance(obj, (list, tuple)):
                    return [convert_decimals(item) for item in obj]
                return obj

            import requests
            import json

            res = requests.post(
                headers={
                    "Authorization": "Bearer app-DhlGqIKpgBtZipEIkFwb4T3L"
                },
                url=config.MB_DAY_REPORT_URL,
                json={
                    "inputs": {
                        "report_type":
                        "WEEK",
                        "store_order_stats":
                        json.dumps(convert_decimals(
                            store_stats_list)),  # 按店铺名整理的每日订单数据
                        "total_count":
                        total_stats["total_count"],  # 当天总订单数量
                        "total_amount":
                        total_stats["total_amount"],  # 当天总订单金额
                        "full_date":
                        f"{last_monday.strftime('%Y-%m-%d')} 至 {last_sunday.strftime('%Y-%m-%d')}",  # 上一周
                        "formatted_carriers":
                        json.dumps(convert_decimals(
                            formatted_carriers)),  # 当天按物流商统计的订单数据
                        "formatted_products":
                        json.dumps(
                            convert_decimals(formatted_products)),  # 当天销量前5的商品
                        "formatted_items":
                        json.dumps(convert_decimals(
                            formatted_items)),  # 当天按商品item_id统计的订单数据
                        "formatted_top_orders":
                        json.dumps(convert_decimals(
                            formatted_top_orders)),  # 当天金额前5的订单
                        "formatted_account_daily":
                        json.dumps(formatted_account_daily),  # 账号每日订单数据
                        "formatted_data":
                        json.dumps(convert_decimals(formatted_data))  # 原始数据
                    },
                    "response_mode": "blocking",
                    "user": "abc-123"
                })

            if res.json()['data'].get("status") == "succeeded":
                return {"status": "success", "message": "订单周报发送成功"}
            else:
                return {"status": "error", "message": "订单周报发送失败"}

        except Exception as e:
            print(f"获取订单数据出错: {str(e)}")
            return {"status": "error", "message": str(e)}
        finally:
            await Tortoise.close_connections()

    # 运行异步函数并返回结果
    return asyncio.run(_async_task())
