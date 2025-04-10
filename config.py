from pydantic_settings import BaseSettings, SettingsConfigDict


# 配置文件
class Settings(BaseSettings):
    # 数据库配置
    MYSQL_HOST: str
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = "123456"
    MYSQL_DATABASE: str = "mbdata"
    # redis配置
    REDIS_HOST: str
    REDIS_PORT: int = 6379
    # fastapi配置
    FASTAPI_DEBUG: bool
    # 订单日报接口配置
    MB_DAY_REPORT_URL: str

    model_config = SettingsConfigDict(env_file=".env",
                                      env_file_encoding="utf-8",
                                      extra="ignore")


config = Settings()  # type: ignore
