# DeepSniper V2 - 高频流数据监控与自动化决策系统

## 📖 项目简介
本项目是一套基于异步并发架构的高频时序数据监控与自动化决策 Agent。系统能够实时对接海量底层流数据，利用大模型（LLM）进行深度的异常检测（Anomaly Detection），并结合统计算法动态输出资源调配与风控指令。目前已具备完整的底层数据持久化与进程级守护闭环。

## 🚀 核心特性 (Core Features)
- **高频异步并发 (Asyncio & CCXT)**: 毫秒级多周期流数据采集，彻底解决 I/O 阻塞。
- **确定性信号引擎 (Signal Engine)**: 基于多周期（1h + 15min）时序动能共振的量化检测。
- **AI 智能守门人 (LLM Guard)**: 定时接管全局数据，利用大模型进行极端黑天鹅行情识别与风控否决。
- **动态资源调配 (Kelly Criterion)**: 基于历史胜率与盈亏比的动态仓位与资源管理算法。
- **全量数据闭环 (aiosqlite)**: 具备完整的状态水合（State Hydration）、异步 CRUD 及 Markdown 审计报表生成能力。

## 🛠️ 技术栈
`Python 3.11+` | `asyncio` | `aiosqlite` | `CCXT` | `Loguru`
