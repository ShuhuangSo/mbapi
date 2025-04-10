from fastapi import FastAPI
from tortoise.contrib.fastapi import register_tortoise
from router import routers
from database import TORTOISE_ORM
from config import config

app = FastAPI(debug=config.FASTAPI_DEBUG, )
# 注册路由
app.include_router(routers)

# 注册 Tortoise ORM 到 FastAPI 应用
register_tortoise(
    app,
    config=TORTOISE_ORM,  # 数据库配置
    generate_schemas=False,  # 是否自动生成表结构
    add_exception_handlers=True,  # 是否添加异常处理器
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
