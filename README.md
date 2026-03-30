# DragonMem — DragonflyDB Unified Memory System

**龙记忆 - 一体化存储系统**

[![npm version](https://badge.fury.io/js/@ggvc%2Fdragon-mem.svg)](https://badge.fury.io/js/@ggvc%2Fdragon-mem)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![OpenClaw Plugin](https://img.shields.io/badge/OpenClaw-Plugin-blue.svg)](https://openclaw.ai)

---

## 🚀 快速开始

### 1. 安装

```bash
# 从 npm 安装
npm install @ggvc/dragon-mem
```

### 2. 安装 DragonflyDB

```bash
# macOS
brew install dragonflydb

# 启动
dragonfly --logtostderr &
```

### 3. 配置 OpenClaw

在 `~/.openclaw/openclaw.json` 中添加：

```json
{
  "plugins": {
    "entries": {
      "dragon-mem": {
        "enabled": true,
        "config": {
          "autoInject": true,
          "autoSave": true,
          "maxMemories": 3,
          "dragonflyUrl": "redis://localhost:6379"
        }
      }
    }
  }
}
```

### 4. 重启 OpenClaw

```bash
openclaw gateway restart
```

---

## 🧠 核心特性

### DragonflyDB 一体化存储

| 功能 | CortexMem | DragonMem |
|------|-----------|-----------|
| **KV 存储** | Redis | DragonflyDB |
| **向量存储** | LanceDB | DragonflyDB |
| **数据库数** | 2 个 | **1 个** ✅ |
| **架构复杂度** | 中 | **低** ✅ |
| **维护成本** | 中 | **低** ✅ |

### 类脑记忆分层

- **L0** 感觉缓冲（5 分钟）
- **L1** 工作记忆（2 小时）
- **L2** 情景缓冲（24 小时）
- **L3** 长期记忆（永久）
- **L4** 概念层（永久）

### 核心工具

- `remember` - 显式记忆存储
- `search_memories` - 语义检索
- `memory_stats` - 系统统计
- 更多工具开发中...

---

## 📊 架构设计

```
┌─────────────────────────────────────────┐
│           OpenClaw Gateway              │
├─────────────────────────────────────────┤
│         DragonMem Plugin                │
│  ┌─────────────────────────────────┐    │
│  │  TypeScript (index.ts)          │    │
│  │  - 记忆管理工具                  │    │
│  │  - before_prompt_build 钩子      │    │
│  │  - 自动记忆注入                  │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
           ↓ HTTP (port 9722)
┌─────────────────────────────────────────┐
│   DragonflyDB Server (Python)           │
│  ┌─────────────────────────────────┐    │
│  │  单一数据库                     │    │
│  │  - KV 存储 (L0-L2)              │    │
│  │  - 向量搜索 (L3-L4)             │    │
│  │  - 多智能体隔离                 │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

---

## 🔧 配置选项

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `autoInject` | boolean | `true` | 自动注入记忆 |
| `autoSave` | boolean | `true` | 自动保存对话 |
| `maxMemories` | number | `3` | 最大注入数量 |
| `dragonflyUrl` | string | `redis://localhost:6379` | DragonflyDB 连接 |
| `vectorIndex` | string | `idx:dragonmem` | 向量索引名称 |

---

## 📈 性能表现

| 操作 | 响应时间 | 说明 |
|------|----------|------|
| KV 读取 | ~2ms | DragonflyDB |
| KV 写入 | ~3ms | DragonflyDB |
| 向量搜索 | ~50ms | 512 维向量 |
| 记忆保存 | ~100ms | 批量写入 |

---

## 🧪 测试

```bash
# 运行测试
npm test

# 启动服务器
npm start

# 验证服务
curl http://127.0.0.1:9722/health
```

---

## 📄 许可证

MIT License - 查看 [LICENSE](./LICENSE) 文件

---

## 🔗 相关链接

- **GitHub:** https://github.com/Lyra-eva/dragon-mem
- **npm:** https://www.npmjs.com/package/@ggvc/dragon-mem
- **OpenClaw:** https://openclaw.ai
- **DragonflyDB:** https://dragonflydb.io

---

**DragonMem — Where Memory Meets Simplicity** 🐉
