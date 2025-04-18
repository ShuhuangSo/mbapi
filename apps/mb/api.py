from fastapi import APIRouter, HTTPException, Request, Body
from tortoise import connections
from typing import List
from decimal import Decimal
import pytz
from datetime import datetime
from apps.mb.models import Orders, OrderItems
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
                              "start_time": "2025-04-08 00:00:00",
                              "end_time": "2025-04-10 23:59:59"
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
async def get_all_celery_tasks():
    """
    获取所有Celery任务状态
    """
    inspector = celery_app.control.inspect()

    # 获取活跃任务
    active = inspector.active() or {}

    # 获取所有配置的定时任务计划
    scheduled = {
        'configured_schedules': celery_app.conf.beat_schedule,
        'pending_schedules': inspector.scheduled() or {}
    }
    # 获取保留任务
    reserved = inspector.reserved() or {}

    # 获取已完成任务(需要配置结果后端)
    completed_tasks = []
    if celery_app.backend:
        try:
            # 获取最近100个已完成任务ID
            task_ids = celery_app.backend.client.keys(
                'celery-task-meta-*')[:100]
            for task_id in task_ids:
                task_id = task_id.decode().replace('celery-task-meta-', '')
                result = AsyncResult(task_id, app=celery_app)
                if result.ready():
                    task_meta = celery_app.backend.get_task_meta(task_id)
                    date_done = task_meta.get('date_done')
                    if date_done:
                        # 确保date_done是datetime对象
                        if isinstance(date_done, str):
                            date_done = datetime.fromisoformat(date_done)
                        # 转换为北京时间
                        utc_time = date_done.replace(tzinfo=pytz.UTC)
                        beijing_time = utc_time.astimezone(
                            pytz.timezone('Asia/Shanghai'))
                        formatted_time = beijing_time.strftime(
                            "%Y-%m-%d %H:%M:%S")
                    else:
                        formatted_time = None
                    completed_tasks.append({
                        'id': task_id,
                        'status': result.status,
                        'result': result.result,
                        'date_done': formatted_time,
                        '_raw_date_done': date_done
                    })

            # 按原始时间排序
            if completed_tasks:
                completed_tasks.sort(key=lambda x: x['_raw_date_done']
                                     if x['_raw_date_done'] else datetime.min,
                                     reverse=True)
                # 移除临时字段
                for task in completed_tasks:
                    task.pop('_raw_date_done', None)

        except Exception as e:
            print(f"获取任务信息出错: {str(e)}")  # 添加错误日志

    return {
        'active': active,
        'scheduled': scheduled,
        'reserved': reserved,
        'completed': completed_tasks
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


@router.post("/get_order_info/", summary="获取mb订单额外信息")
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
            order_list.append({
                'order_number': order.order_number,
                'postage_out_rmb': order.postage_out_rmb,
                'profit_rmb': round(float(order.profit_rmb), 2),
                'order_items': order_items
            })

    return {"order_list": order_list}
