#!/bin/bash
set -e

echo "========================================"
echo " Binance Bot V2 - Docker 一键部署"
echo "========================================"

# ---- 1. 停止旧版 V1 bot ----
echo ""
echo "[1/4] 停止旧版 V1 进程..."
OLD_PIDS=$(pgrep -f "python.*main.py" 2>/dev/null || true)
if [ -n "$OLD_PIDS" ]; then
    echo "  发现旧进程: $OLD_PIDS"
    kill $OLD_PIDS 2>/dev/null || true
    sleep 2
    pkill -9 -f "python.*main.py" 2>/dev/null || true
    echo "  旧版 bot 已终止"
else
    echo "  未发现旧进程"
fi

# 清理旧的 tmux/screen 会话
tmux kill-session -t sniper 2>/dev/null || true
screen -S sniper -X quit 2>/dev/null || true

# ---- 2. 检查 .env ----
echo ""
echo "[2/4] 检查配置..."
if [ ! -f ".env" ]; then
    echo "  ERROR: .env 不存在，请先创建并填入 API keys"
    exit 1
fi
if ! grep -q "sk-" .env 2>/dev/null; then
    echo "  WARNING: .env 中未检测到 DeepSeek API key"
fi
echo "  .env OK"

# ---- 3. 构建镜像 ----
echo ""
echo "[3/4] 构建 Docker 镜像..."
docker compose build --pull

# ---- 4. 启动 ----
echo ""
echo "[4/4] 启动容器..."
docker compose down --remove-orphans 2>/dev/null || true
docker compose up -d

echo ""
echo "========================================"
echo " 部署完成"
echo "========================================"
echo ""
echo "常用命令:"
echo "  docker compose logs -f        # 实时日志"
echo "  docker compose logs --tail=50 # 最近50行"
echo "  docker compose restart       # 重启"
echo "  docker compose down          # 停止"
echo "  docker compose pull          # 更新镜像"
echo ""
echo "下载数据到本地分析:"
echo "  scp root@your-vps:/root/binance_bot_v2/data/sniper_v2.db ./"
echo "  python pnl_inspector.py"
echo ""
