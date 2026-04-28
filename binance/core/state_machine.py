import json
import os
import aiofiles
from core.logger import logger

STATE_FILE = "data/state.json"

async def load_state():
    """读取本地状态机，实现断电恢复与损坏防御"""
    if not os.path.exists(STATE_FILE):
        return {"position": None, "cooldown_until": 0}
        
    try:
        # 强制使用 utf-8 编码读取，防止跨平台乱码
        async with aiofiles.open(STATE_FILE, mode='r', encoding='utf-8') as f:
            content = await f.read()
            # 如果文件是空的，直接触发异常进入 except 分支
            if not content.strip():
                raise ValueError("状态文件为空")
            return json.loads(content)
            
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"⚠️ 发现损坏的本地状态文件 ({e})，系统已自动重置为空仓状态。")
        return {"position": None, "cooldown_until": 0}
    except Exception as e:
        logger.error(f"❌ 读取状态文件时发生未知异常: {e}")
        return {"position": None, "cooldown_until": 0}

async def save_state(state_dict):
    """原子化保存状态，防止写入时断电崩溃导致数据损坏"""
    # 动态获取目录名，比硬编码 "data" 更安全
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    temp_file = STATE_FILE + ".tmp"
    
    # 1. 先安全写入临时文件 (强行指定 utf-8)
    async with aiofiles.open(temp_file, mode='w', encoding='utf-8') as f:
        await f.write(json.dumps(state_dict, indent=4))
        
    # 2. 原子级覆盖（瞬间替换，绝不产生撕裂）
    os.replace(temp_file, STATE_FILE)