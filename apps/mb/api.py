from fastapi import APIRouter, HTTPException, Request, Body
from tortoise import connections
from typing import List
from decimal import Decimal
import pytz
from datetime import datetime
from apps.mb.models import Orders, OrderItems
from apps.logistic.models import AreaCode, PostPrice
from apps.mb.schemas import OrdersForm
from fastapi.templating import Jinja2Templates
from pathlib import Path
import json

from celery_app import celery_app
from celery.result import AsyncResult
from apps.mb.tasks import get_orders_task

templates = Jinja2Templates(directory="templates")  # 添加模板配置

router = APIRouter()


@router.get("/orders/", response_model=List[OrdersForm], summary="获取订单数据100条")
async def get_all_orders():
    """
    获取所有订单数据
    """
    return await Orders.all().prefetch_related("order_items").order_by(
        "-paid_time").limit(100)


# 执行SQL查询
@router.post("/sql-query/", summary="执行安全SQL查询")
async def execute_sql_query(
    request: Request,
    sql_query: dict = Body(...,
                           example={"sql":
                                    "SELECT * FROM mb_orders LIMIT 10"})):
    """
    执行安全SQL查询（仅支持SELECT语句）
    """
    # 基础安全校验
    if not sql_query.get("sql"):
        raise HTTPException(status_code=400, detail="SQL语句不能为空")

    # 修复后的表名转换逻辑（保持表名小写）
    safe_sql = sql_query["sql"].replace("mb_orders", "orders").replace(
        "ORDERS", "orders").replace("Orders", "orders")
    raw_sql = safe_sql.strip()  # 移除转换为大写的操作

    if not raw_sql.upper().startswith("SELECT"):  # 仅校验语句类型时使用大写
        raise HTTPException(status_code=403, detail="仅支持SELECT查询")
    try:
        # 获取数据库连接
        connection = connections.get("default")

        # 执行查询
        result = await connection.execute_query_dict(raw_sql)

        # 转换Decimal类型为float
        for row in result:
            for key, value in row.items():
                if isinstance(value, Decimal):
                    row[key] = float(value)

        return {"status": "success", "data": result}

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"执行查询失败: {str(e)}")


# 任务结果查询
@router.get("/result/{task_id}", summary="单个Celery任务结果查询")
def get_task_result(task_id: str):
    result = celery_app.AsyncResult(task_id)
    if result.ready():
        return {"task_status": "completed", "result": result.result}
    else:
        return {"task_status": "pending"}


@router.post("/sync_orders/", summary="同步mb订单数据")
async def sync_orders(request: Request,
                      time_range: dict = Body(
                          ...,
                          example={
                              "start_time": "2025-10-30 00:00:00",
                              "end_time": "2025-10-30 23:59:59"
                          })):
    """
    获取mb订单数据
    参数:
        start_time: 开始时间 (格式: YYYY-MM-DD HH:MM:SS)
        end_time: 结束时间 (格式: YYYY-MM-DD HH:MM:SS)
    """
    start_time = time_range.get("start_time")
    end_time = time_range.get("end_time")

    if not start_time or not end_time:
        raise HTTPException(status_code=400,
                            detail="必须提供start_time和end_time参数")

    task = get_orders_task.delay(start_time, end_time)
    return {"status": "started", "task_id": task.id}


@router.get("/celery/tasks/", summary="获取所有Celery任务状态")
async def get_all_celery_tasks(limit_completed: int = 10):
    """
    获取所有Celery任务状态
    参数:
        limit_completed: 限制返回的已完成任务数量，默认10条
    """
    inspector = celery_app.control.inspect()

    # 获取活跃任务
    active = inspector.active() or {}

    # 获取所有配置的定时任务计划
    scheduled = {
        'configured_schedules': {k: {'task': v['task'], 'schedule': str(v['schedule'])} 
                                for k, v in celery_app.conf.beat_schedule.items()},
        'pending_schedules': inspector.scheduled() or {}
    }
    # 获取保留任务
    reserved = inspector.reserved() or {}

    # 获取已完成任务(需要配置结果后端)
    completed_tasks = []
    if celery_app.backend:
        try:
            # 限制获取的任务ID数量，避免Redis操作过于耗时
            task_ids = celery_app.backend.client.keys('celery-task-meta-*')[-limit_completed:]
            for task_id in task_ids:
                task_id = task_id.decode().replace('celery-task-meta-', '')
                try:
                    # 简化获取任务元数据的操作
                    task_meta = celery_app.backend.get_task_meta(task_id)
                    if task_meta.get('status') in ['SUCCESS', 'FAILURE', 'REVOKED']:
                        # 只返回必要信息，避免处理过大的result
                        date_done = task_meta.get('date_done')
                        if date_done:
                            # 简化时间处理
                            try:
                                if isinstance(date_done, str):
                                    date_done = datetime.fromisoformat(date_done)
                                # 简化时区转换
                                formatted_time = date_done.strftime("%Y-%m-%d %H:%M:%S")
                            except:
                                formatted_time = str(date_done)
                        else:
                            formatted_time = None
                        
                        # 限制result大小
                        result = task_meta.get('result')
                        if result and isinstance(result, (dict, list)):
                            # 对于复杂结果，只返回类型信息
                            result = f"{type(result).__name__} (data omitted for performance)"
                        
                        completed_tasks.append({
                            'id': task_id,
                            'status': task_meta.get('status'),
                            'result': result,
                            'date_done': formatted_time
                        })
                except Exception as task_e:
                    # 单个任务出错不影响整体
                    continue

            # 简单排序，避免复杂操作
            completed_tasks.sort(key=lambda x: x['date_done'] or '', reverse=True)

        except Exception as e:
            print(f"获取任务信息出错: {str(e)}")  # 添加错误日志

    return {
        'active': active,
        'scheduled': scheduled,
        'reserved': reserved,
        'completed': completed_tasks,
        'info': f"已限制返回{limit_completed}条最近的完成任务以优化性能"
    }


@router.get("/day_orders_report/", summary="发送每日订单报告")
async def get_day_orders():
    """
    手动获取昨天订单报告，并发送到飞书 
    """
    from apps.mb.tasks import get_day_orders_report_task
    task = get_day_orders_report_task.delay()
    return {"status": "started", "task_id": task.id}


@router.get("/week_orders_report/", summary="发送每周订单报告")
async def get_week_orders():
    """
    手动获取上一周订单报告，并发送到飞书 
    """
    from apps.mb.tasks import get_week_orders_report_task
    task = get_week_orders_report_task.delay()
    return {"status": "started", "task_id": task.id}


@router.get("/mb_token/",
            summary="获取已保存的mb token",
            description="获取mb_token.json文件中的cookie和update_time")
async def get_mb_token():
    """
    获取mb_token.json文件中的cookie和update_time
    """
    config_path = Path(__file__).parent.parent.parent / "mb_token.json"
    with open(config_path, 'r') as f:
        config = json.load(f)
    return {"cookie": config["cookie"], "update_time": config["update_time"]}


@router.post("/update_cookie/", summary="更新mbtoken")
async def update_cookie(c_value: str = Body(..., embed=True)):
    """
    更新mb_token.json文件中的cookie值
    参数:
        c_value: 新的cookie值
    """
    config_path = Path(__file__).parent.parent.parent / "mb_token.json"

    # 读取现有配置
    with open(config_path, 'r') as f:
        config = json.load(f)

    # 更新配置
    config["cookie"] = c_value
    config["update_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 写回文件
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=4)

    return {"status": "success", "message": "cookie更新成功"}


@router.post("/get_order_info/", summary="获取mb订单额外信息(客服信息)")
async def get_order_info(order_nums: List = Body(..., embed=True)):
    """
    获取mb订单额外信息
    参数:
        order_nums: 订单编号列表
    """
    order_list = []
    if order_nums:
        for order_num in order_nums:
            order = await Orders.get_or_none(order_number=order_num)
            if not order:
                continue
            order_items = await OrderItems.filter(order=order).values(
                'item_cost', 'sku', 'platform_property')
            # 获取邮编分区
            area_list = await AreaCode.filter(
                country_code=order.country_code,
                post_code=order.post_code).values('name', 'area', 'is_service',
                                                  'ship_code')
            # 添加信封渠道
            if order.country_code == 'AU':
                area_list.append({
                    'name': '信封',
                    'area': None,
                    'is_service': True,
                    'ship_code': 'ZMAU-L'
                })
            post_list = []
            for i in area_list:
                postage = await calc_post_price(i['area'],
                                                int(order.order_weight),
                                                i['ship_code'])
                post_list.append({
                    'name': i['name'],
                    'area': i['area'],
                    'is_service': i['is_service'],
                    'postage': postage
                })

            # 按postage从小到大排序
            post_list.sort(key=lambda x: x['postage'])
            order_list.append({
                'order_number': order.order_number,
                'postage_out_rmb': order.postage_out_rmb,
                'profit_rmb': round(float(order.profit_rmb), 2),
                'order_items': order_items,
                'post_list': post_list
            })

    return {"order_list": order_list}


@router.post("/get_order_list_info/", summary="获取mb订单列表额外信息(订单列表页)")
async def get_order_list_info(orders: List = Body(...)):
    """
    获取mb订单列表额外信息(订单列表页)
    参数:
        orders: 订单列表，格式示例:
        [{
            orderNumber: "081298327265", 
            country: "澳大利亚",
            postCode: "2848",
            weight: "80"
        }]
    """
    order_list = []
    if orders:
        for od in orders:
            order_num = od.get('orderNumber', '')
            country = od.get('country', '')
            country_code = 'AU' if country == '澳大利亚' else 'GB' if country == '英国' else ''
            post_code = od.get('postCode', '')
            try:
                weight = int(od.get('weight', 0))
            except (ValueError, TypeError):
                weight = 0

            # 获取邮编分区
            area_list = await AreaCode.filter(country_code=country_code,
                                              post_code=post_code).values(
                                                  'name', 'area', 'is_service',
                                                  'ship_code')
            # 添加信封渠道
            if country_code == 'AU':
                area_list.append({
                    'name': '信封',
                    'area': None,
                    'is_service': True,
                    'ship_code': 'ZMAU-L'
                })
            post_list = []
            # 英国添加联邮通(普货)渠道
            if country_code == 'GB':
                post_list.append({
                    'name':
                    '联邮通(普货)',
                    'area':
                    None,
                    'is_service':
                    True,
                    'postage':
                    await calc_post_price(None, weight, '4PX_WBP')
                })
            for i in area_list:
                postage = await calc_post_price(i['area'], weight,
                                                i['ship_code'])
                post_list.append({
                    'name': i['name'],
                    'area': i['area'],
                    'is_service': i['is_service'],
                    'postage': postage if weight else 0
                })

            # 按postage从小到大排序
            post_list.sort(key=lambda x: x['postage'])
            order_list.append({
                'order_number': order_num,
                'post_list': post_list
            })

    return {"order_list": order_list}


async def calc_post_price(area: str, weight: int, carrier_code: str):
    """
    计算订单运费
    参数:
        area: 区域
        weight: 重量(克)
        carrier_code: 物流渠道代码
    返回: 运费计算结果
    """

    # 查询符合条件的物流价格
    price = await PostPrice.filter(area=area,
                                   carrier_code=carrier_code,
                                   min_weight__lte=weight,
                                   max_weight__gte=weight).first()

    if not price:
        return 0

    # 计算运费: calc_price * weight / 1000 + basic_price
    total_price = (price.calc_price * weight / 1000) + price.basic_price
    return round(total_price, 2)
