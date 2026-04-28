import logging
from logging.handlers import RotatingFileHandler
import os

def setup_logger():
    os.makedirs("data", exist_ok=True)
    logger = logging.getLogger("DeepSniper")
    logger.setLevel(logging.INFO)

    # 限制单个日志文件最大 5MB，最多保留 3 个备份
    handler = RotatingFileHandler(
        "data/sniper.log", maxBytes=5*1024*1024, backupCount=3, encoding='utf-8'
    )
    
    # 格式：[时间] [级别] - 消息
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    handler.setFormatter(formatter)
    
    # 控制台输出
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    
    if not logger.handlers:
        logger.addHandler(handler)
        logger.addHandler(console)
        
    return logger

logger = setup_logger()