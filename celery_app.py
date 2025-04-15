import sys
from pathlib import Path
from celery import Celery
from celery.schedules import crontab
from config import config

REDIS_HOST = config.REDIS_HOST
REDIS_PORT = config.REDIS_PORT

# 添加项目根目录到系统路径
sys.path.append(str(Path(__file__).parent))

# 创建 Celery 实例
celery_app = Celery('project',
                    broker=f'redis://{REDIS_HOST}:{REDIS_PORT}/0',
                    backend=f'redis://{REDIS_HOST}:{REDIS_PORT}/0')

# 设置时区为北京时间
celery_app.conf.timezone = 'Asia/Shanghai'
celery_app.conf.enable_utc = False  # 禁用UTC

# 配置定时任务
celery_app.conf.beat_schedule = {
    'get-oneweek-orders-daily': {
        'task': 'apps.mb.tasks.get_oneweek_orders',  # 获取最近7天订单
        'schedule': crontab(minute='30', hour='0'),  # 每天0点30分执行
        'args': ()  # 可以在这里添加任务参数
    },
    'send-day-report-daily': {
        'task': 'apps.mb.tasks.get_day_orders_report_task',  # 获取订单报告
        'schedule': crontab(minute='0', hour='9'),  # 每天9点执行
        'args': ()  # 可以在这里添加任务参数
    },
    'send-week-report-weekly': {
        'task': 'apps.mb.tasks.get_week_orders_report_task',  # 获取周订单报告
        'schedule': crontab(minute='0', hour='10', day_of_week=2),  # 每周二10点执行
        'args': ()  # 可以在这里添加任务参数
    },
}

# 自动发现各个 app 中的任务
celery_app.autodiscover_tasks(['apps.mb'])
