import os
import json
import aiosqlite
from core.logger import log

DB_PATH = "data/sniper_v2.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    entry_time REAL NOT NULL,
    entry_price REAL NOT NULL,
    entry_amount REAL NOT NULL,
    entry_fee REAL NOT NULL,
    entry_fee_asset TEXT NOT NULL DEFAULT 'USDT',
    entry_order_id TEXT,
    exit_time REAL,
    exit_price REAL,
    exit_amount REAL,
    exit_fee REAL,
    exit_fee_asset TEXT,
    exit_reason TEXT,
    net_pnl REAL,
    net_pnl_pct REAL,
    highest_price REAL,
    status TEXT NOT NULL DEFAULT 'OPEN',
    notes TEXT,
    created_at REAL DEFAULT (strftime('%s','now'))
);

CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    period TEXT NOT NULL,
    total_equity REAL NOT NULL,
    free_usdt REAL NOT NULL,
    positions_json TEXT,
    sharpe_ratio REAL,
    max_drawdown REAL,
    win_rate REAL,
    profit_factor REAL,
    consecutive_losses INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_entry_time ON trades(entry_time);
CREATE INDEX IF NOT EXISTS idx_snapshots_period ON snapshots(period);
CREATE INDEX IF NOT EXISTS idx_snapshots_timestamp ON snapshots(timestamp);
"""

_db = None

async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        os.makedirs("data", exist_ok=True)
        _db = await aiosqlite.connect(DB_PATH)
        _db.row_factory = aiosqlite.Row
        await _db.executescript(SCHEMA_SQL)
        # 迁移: 为旧库补加 highest_price 列
        try:
            await _db.execute("ALTER TABLE trades ADD COLUMN highest_price REAL")
        except Exception:
            pass
        await _db.commit()
        log.bind(tag="DB").info("数据库已连接并初始化")
    return _db

async def close_db():
    global _db
    if _db:
        await _db.close()
        _db = None
        log.bind(tag="DB").info("数据库已关闭")


# ── Trades CRUD ──

async def insert_trade(trade: dict) -> int:
    db = await get_db()
    cur = await db.execute(
        """INSERT INTO trades (symbol, entry_time, entry_price, entry_amount,
           entry_fee, entry_fee_asset, entry_order_id, highest_price, status, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?)""",
        (trade['symbol'], trade['entry_time'], trade['entry_price'],
         trade['entry_amount'], trade['entry_fee'], trade.get('entry_fee_asset', 'USDT'),
         trade.get('entry_order_id'), trade['entry_price'],
         trade.get('notes', ''))
    )
    await db.commit()
    return cur.lastrowid

async def update_trade_exit(trade_id: int, exit_data: dict):
    db = await get_db()
    await db.execute(
        """UPDATE trades SET exit_time=?, exit_price=?, exit_amount=?,
           exit_fee=?, exit_fee_asset=?, exit_reason=?,
           net_pnl=?, net_pnl_pct=?, status='CLOSED'
           WHERE id=?""",
        (exit_data['exit_time'], exit_data['exit_price'], exit_data['exit_amount'],
         exit_data['exit_fee'], exit_data.get('exit_fee_asset', 'USDT'), exit_data['exit_reason'],
         exit_data['net_pnl'], exit_data['net_pnl_pct'], trade_id)
    )
    await db.commit()

async def update_trade_partial(trade_id: int, partial_data: dict):
    db = await get_db()
    await db.execute(
        """UPDATE trades SET exit_time=?, exit_price=?, exit_amount=?,
           exit_fee=?, exit_fee_asset=?, exit_reason=?,
           net_pnl=?, net_pnl_pct=?, status='PARTIAL', notes=?
           WHERE id=?""",
        (partial_data['exit_time'], partial_data['exit_price'], partial_data['exit_amount'],
         partial_data['exit_fee'], partial_data.get('exit_fee_asset', 'USDT'),
         partial_data['exit_reason'], partial_data['net_pnl'], partial_data['net_pnl_pct'],
         partial_data.get('notes', ''), trade_id)
    )
    await db.commit()

async def update_trade_highest_price(trade_id: int, highest_price: float):
    db = await get_db()
    await db.execute(
        "UPDATE trades SET highest_price = MAX(COALESCE(highest_price, 0), ?) WHERE id = ?",
        (highest_price, trade_id)
    )
    await db.commit()


async def get_open_trades() -> list:
    """状态水合：恢复所有未平仓订单"""
    db = await get_db()
    cur = await db.execute("SELECT * FROM trades WHERE status IN ('OPEN', 'PARTIAL')")
    rows = await cur.fetchall()
    return [dict(r) for r in rows]

async def get_closed_trades(limit: int = 50) -> list:
    db = await get_db()
    cur = await db.execute(
        "SELECT * FROM trades WHERE status = 'CLOSED' ORDER BY exit_time DESC LIMIT ?", (limit,)
    )
    rows = await cur.fetchall()
    return [dict(r) for r in rows]

async def count_closed_trades() -> int:
    db = await get_db()
    cur = await db.execute("SELECT COUNT(*) as c FROM trades WHERE status = 'CLOSED'")
    row = await cur.fetchone()
    return row['c']

async def get_recent_closed_trades(limit: int = 50) -> list:
    db = await get_db()
    cur = await db.execute(
        "SELECT * FROM trades WHERE status = 'CLOSED' ORDER BY exit_time DESC LIMIT ?", (limit,)
    )
    return [dict(r) for r in await cur.fetchall()]

async def get_win_rate(limit: int = 50) -> float:
    trades = await get_recent_closed_trades(limit)
    if not trades:
        return 0.5
    wins = sum(1 for t in trades if (t['net_pnl'] or 0) > 0)
    return wins / len(trades)

async def get_all_trades() -> list:
    db = await get_db()
    cur = await db.execute("SELECT * FROM trades ORDER BY entry_time DESC")
    return [dict(r) for r in await cur.fetchall()]


# ── Snapshots CRUD ──

async def insert_snapshot(snap: dict):
    db = await get_db()
    await db.execute(
        """INSERT INTO snapshots (timestamp, period, total_equity, free_usdt,
           positions_json, sharpe_ratio, max_drawdown, win_rate, profit_factor,
           consecutive_losses)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (snap['timestamp'], snap['period'], snap['total_equity'], snap['free_usdt'],
         snap.get('positions_json', '{}'), snap.get('sharpe_ratio'),
         snap.get('max_drawdown'), snap.get('win_rate'), snap.get('profit_factor'),
         snap.get('consecutive_losses', 0))
    )
    await db.commit()

async def get_latest_snapshot(period: str = "instant") -> dict:
    db = await get_db()
    cur = await db.execute(
        "SELECT * FROM snapshots WHERE period=? ORDER BY timestamp DESC LIMIT 1", (period,)
    )
    row = await cur.fetchone()
    return dict(row) if row else None

async def get_snapshots(period: str, since_ts: float = None) -> list:
    db = await get_db()
    if since_ts:
        cur = await db.execute(
            "SELECT * FROM snapshots WHERE period=? AND timestamp >= ? ORDER BY timestamp ASC",
            (period, since_ts)
        )
    else:
        cur = await db.execute(
            "SELECT * FROM snapshots WHERE period=? ORDER BY timestamp ASC", (period,)
        )
    return [dict(r) for r in await cur.fetchall()]

async def get_last_snapshot_before(period: str, ts: float) -> dict:
    db = await get_db()
    cur = await db.execute(
        "SELECT * FROM snapshots WHERE period=? AND timestamp <= ? ORDER BY timestamp DESC LIMIT 1",
        (period, ts)
    )
    row = await cur.fetchone()
    return dict(row) if row else None

async def count_consecutive_losses() -> int:
    trades = await get_recent_closed_trades(50)
    count = 0
    for t in trades:
        if (t['net_pnl'] or 0) < 0:
            count += 1
        else:
            break
    return count
