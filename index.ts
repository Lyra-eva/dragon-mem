/**
 * DragonMem - DragonflyDB Unified Memory System for OpenClaw
 * 
 * 龙记忆 - 一体化存储系统
 * 
 * 特性：
 * - DragonflyDB 单一数据库（KV + 向量）
 * - L0-L4 类脑记忆分层
 * - 语义搜索 + 多跳检索
 * - 自动记忆巩固
 * - 多智能体隔离
 */

import { Type } from '@sinclair/typebox';
import * as fs from 'node:fs';

const LOG_PATH = '/Users/lx/.openclaw/workspace/cognition/dragonmem.log';
function debugLog(msg: string) { 
  try { 
    fs.appendFileSync(LOG_PATH, `[${new Date().toISOString()}] ${msg}\n`); 
  } catch {} 
}

// ===== 配置 =====
interface DragonMemConfig {
  autoInject?: boolean;
  autoSave?: boolean;
  maxMemories?: number;
  dragonflyUrl?: string;
  vectorIndex?: string;
  disabledTools?: string[];
}

const DEFAULT_CONFIG: DragonMemConfig = {
  autoInject: true,
  autoSave: true,
  maxMemories: 3,
  dragonflyUrl: 'redis://localhost:6379',
  vectorIndex: 'idx:dragonmem',
  disabledTools: [],
};

let config: DragonMemConfig = DEFAULT_CONFIG;
let dragonflyClient: any = null;

// 跳过的消息模式
const SKIP_PATTERNS = ['你好', 'hello', 'hi', '早', '好', '谢谢', '感谢', '在吗', '嗯', '哦', 'ok', 'OK'];
const SKIP_SAVE_PATTERNS = ['HEARTBEAT', 'NO_REPLY', 'HEARTBEAT_OK'];

// ===== Plugin 入口 =====
const definePluginEntry = (def: any) => def;

export default definePluginEntry({
  id: 'dragon-mem',
  name: 'DragonMem',
  description: 'DragonMem — DragonflyDB Unified Memory System (龙记忆 - 一体化存储系统)',

  async register(api: any) {
    const g = global as any;
    const isFirstLoad = !g.dragonMemInitialized;
    g.dragonMemInitialized = true;
    debugLog(`REGISTER mode=${api.registrationMode}, first=${isFirstLoad}`);

    config = { ...DEFAULT_CONFIG, ...api.pluginConfig };

    // DragonflyDB 连接（只连一次）
    if (isFirstLoad) {
      try {
        const redisModule = await import('redis');
        const client = redisModule.default.createClient({ 
          url: config.dragonflyUrl || 'redis://localhost:6379' 
        });
        await client.connect();
        dragonflyClient = client;
        debugLog('DragonflyDB connected');
      } catch (e) {
        debugLog(`DragonflyDB connection error: ${(e as Error).message}`);
      }
    }

    // ========== 能力 1: 语义记忆检索 (before_prompt_build) ==========
    api.on('before_prompt_build', async (event: any, _ctx: any) => {
      if (!config.autoInject) return {};

      // 从 event.prompt 提取用户真实消息
      let content = '';
      const prompt = event?.prompt || '';
      if (typeof prompt === 'string' && prompt.length > 0) {
        const lines = prompt.split('\n');
        for (let i = lines.length - 1; i >= 0; i--) {
          const line = lines[i].trim();
          if (line.length > 0) {
            content = line.replace(/^[^\s:]+:\s*/, '');
            break;
          }
        }
      }

      debugLog(`content resolved (${content.length}): ${content.slice(0,80)}`);

      if (content.length < 8) return {};
      if (SKIP_PATTERNS.some(p => content.toLowerCase().includes(p.toLowerCase()))) return {};

      // 能力 3: 自动积累
      if (config.autoSave && shouldSaveMessage(content, 'user')) {
        saveToDragonfly(content, 'user', {}).then(() => {
          debugLog(`✅ saved: ${content.slice(0,50)}`);
        }).catch((e: any) => {
          debugLog(`❌ save error: ${e?.message || e}`);
        });
      }

      // 语义搜索
      const memories = await semanticSearch(content, config.maxMemories || 3);
      if (!memories || memories.length === 0) return {};

      const memoryText = memories.map((m: any) => {
        if (m.title) return `• [${m.category || ''}] ${m.title}: ${(m.content || m.concepts || '').slice(0, 200)}`;
        if (m.key) return `• ${m.key}: ${m.value}`;
        return `• ${(m.content || '').slice(0, 200)}`;
      }).join('\n');

      debugLog(`injecting ${memories.length} memories`);
      return { prependSystemContext: `[记忆检索] 与当前话题相关的记忆：\n${memoryText}` };
    });

    // ===== 注册工具 =====

    // 工具 1: remember - 存储显式事实
    api.registerTool({
      name: 'remember',
      description: '存储显式事实到记忆中',
      parameters: Type.Object({
        key: Type.String({ description: '记忆的键' }),
        value: Type.String({ description: '记忆的值' })
      }),
      async execute(_id: string, params: { key: string; value: string }) {
        if (dragonflyClient) {
          await dragonflyClient.hSet('memories:explicit', params.key, JSON.stringify({
            key: params.key, value: params.value, created_at: new Date().toISOString()
          }));
        }
        const saved = await saveToDragonfly(`${params.key}: ${params.value}`, 'explicit', {
          title: params.key, category: 'explicit_memory'
        });
        return {
          content: [{ type: 'text',
            text: saved ? `已记住：${params.key}（DragonflyDB）` : `已记住：${params.key}`
          }]
        };
      }
    });

    // 工具 2: search_memories - 语义检索
    api.registerTool({
      name: 'search_memories',
      description: '语义检索记忆',
      parameters: Type.Object({
        query: Type.String({ description: '搜索查询' }),
        limit: Type.Optional(Type.Number({ description: '返回数量限制', default: 5 }))
      }),
      async execute(_id: string, params: { query: string; limit?: number }) {
        const limit = params.limit || 5;
        const results = await semanticSearch(params.query, limit);
        
        const text = results.length > 0
          ? `找到 ${results.length} 条相关记忆：\n\n` + results.map((m: any, i: number) => {
              const dist = m._distance !== undefined ? ` (相似度：${(1 - m._distance).toFixed(3)})` : '';
              if (m.title) return `${i+1}. [${m.category || ''}] **${m.title}**${dist}\n   ${(m.content || '').slice(0, 200)}`;
              return `${i+1}. ${(m.content || '').slice(0, 200)}`;
            }).join('\n\n')
          : '未找到相关记忆';
        return { content: [{ type: 'text', text }] };
      }
    });

    // 工具 3: memory_stats - 系统统计
    api.registerTool({
      name: 'memory_stats',
      description: '查看记忆系统统计',
      parameters: Type.Object({}),
      async execute() {
        let stats = '🧠 DragonMem 统计\n\n';
        
        if (dragonflyClient) {
          try {
            const dbsize = await dragonflyClient.dbSize();
            stats += `DragonflyDB 键数：${dbsize}\n`;
            
            const info = await dragonflyClient.info('memory');
            stats += `内存使用：${info.used_memory_human || 'N/A'}\n`;
          } catch (e) {
            stats += `统计失败：${(e as Error).message}\n`;
          }
        }
        
        return { content: [{ type: 'text', text: stats }] };
      }
    });

    // 工具 4: pattern_completion - 模式完成
    api.registerTool({
      name: 'pattern_completion',
      description: '模式完成（PageRank 图扩散）- 根据线索回忆完整记忆簇',
      parameters: Type.Object({
        query: Type.String({ description: '搜索查询/线索' }),
        agent_id: Type.Optional(Type.String({ description: '智能体 ID', default: 'main' })),
        top_k: Type.Optional(Type.Number({ description: '返回数量', default: 10 }))
      }),
      async execute(_id: string, params: any) {
        try {
          const resp = await fetch(`${config.dragonflyUrl?.replace('redis://', 'http://') || 'http://127.0.0.1:9722'}/pattern_completion`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              query: params.query,
              agent_id: params.agent_id || 'main',
              top_k: params.top_k || 10
            })
          });
          const data = await resp.json();
          const results = data.results || [];
          
          const text = results.length > 0
            ? `🧠 模式完成：找到 ${results.length} 条相关记忆\n\n` +
              results.map((r: any, i: number) => `${i+1}. [hop=${r.hop||0}] ${(r.content||'').slice(0,150)}...`).join('\n')
            : '未找到相关记忆';
          return { content: [{ type: 'text', text }] };
        } catch (e) {
          return { content: [{ type: 'text', text: `❌ 失败：${(e as Error).message}` }] };
        }
      }
    });

    // 工具 5: cluster_activation - 聚类激活
    api.registerTool({
      name: 'cluster_activation',
      description: '聚类激活（Louvain 社区发现）- 激活整个记忆簇',
      parameters: Type.Object({
        action: Type.Optional(Type.String({ description: '操作', default: 'activate' })),
        seed_memory_id: Type.Optional(Type.String({ description: '种子记忆 ID' })),
        agent_id: Type.Optional(Type.String({ description: '智能体 ID', default: 'main' }))
      }),
      async execute(_id: string, params: any) {
        try {
          const resp = await fetch(`${config.dragonflyUrl?.replace('redis://', 'http://') || 'http://127.0.0.1:9722'}/cluster_activation`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params)
          });
          const data = await resp.json();
          const results = data.results || [];
          
          const text = results.length > 0
            ? `🧠 聚类激活：找到 ${results.length} 条相关记忆\n\n` +
              results.map((r: any, i: number) => `${i+1}. ${(r.content||'').slice(0,150)}...`).join('\n')
            : '未找到相关记忆';
          return { content: [{ type: 'text', text }] };
        } catch (e) {
          return { content: [{ type: 'text', text: `❌ 失败：${(e as Error).message}` }] };
        }
      }
    });

    // 工具 6: multi_hop_search - 多跳检索
    api.registerTool({
      name: 'multi_hop_search',
      description: '多跳检索（BFS 图遍历）- A→B→C 链式联想',
      parameters: Type.Object({
        query: Type.String({ description: '搜索查询' }),
        hops: Type.Optional(Type.Number({ description: '跳数', default: 2 })),
        limit: Type.Optional(Type.Number({ description: '返回数量', default: 10 })),
        agent_id: Type.Optional(Type.String({ description: '智能体 ID', default: 'main' }))
      }),
      async execute(_id: string, params: any) {
        try {
          const resp = await fetch(`${config.dragonflyUrl?.replace('redis://', 'http://') || 'http://127.0.0.1:9722'}/multi_hop_search`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params)
          });
          const data = await resp.json();
          const results = data.results || [];
          
          const text = results.length > 0
            ? `🧠 多跳检索 (${params.hops||2}跳)：找到 ${results.length} 条相关记忆\n\n` +
              results.map((r: any, i: number) => `${i+1}. [hop=${r.hop||0}] ${(r.content||'').slice(0,150)}...`).join('\n')
            : '未找到相关记忆';
          return { content: [{ type: 'text', text }] };
        } catch (e) {
          return { content: [{ type: 'text', text: `❌ 失败：${(e as Error).message}` }] };
        }
      }
    });

    // 工具 7: consolidate_memories - 记忆巩固
    api.registerTool({
      name: 'consolidate_memories',
      description: '记忆巩固 - 从 episodes 提取高频主题生成 semantic 记忆',
      parameters: Type.Object({
        agent_id: Type.Optional(Type.String({ description: '智能体 ID', default: 'main' })),
        min_count: Type.Optional(Type.Number({ description: '最小 episode 数量', default: 10 }))
      }),
      async execute(_id: string, params: any) {
        try {
          const resp = await fetch(`${config.dragonflyUrl?.replace('redis://', 'http://') || 'http://127.0.0.1:9722'}/consolidate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params)
          });
          const data = await resp.json();
          
          const text = `🧠 记忆巩固完成\n` +
            `- 分析 episodes: ${data.episodes_analyzed || 0}条\n` +
            `- 提取主题：${data.themes_extracted || 0}个\n` +
            `- 新建 concepts: ${data.concepts_created || 0}个`;
          return { content: [{ type: 'text', text }] };
        } catch (e) {
          return { content: [{ type: 'text', text: `❌ 失败：${(e as Error).message}` }] };
        }
      }
    });

    debugLog('DragonMem plugin registered');
  },
});

// ===== 辅助函数 =====

function shouldSaveMessage(content: string, role: string): boolean {
  if (SKIP_SAVE_PATTERNS.some(p => content.includes(p))) return false;
  return true;
}

async function saveToDragonfly(content: string, type: string, metadata: any = {}): Promise<boolean> {
  try {
    if (!dragonflyClient) return false;
    
    const key = `memory:${metadata.agent_id || 'main'}:${Date.now()}:${Math.random().toString(36).slice(2, 8)}`;
    const data = {
      content,
      type,
      created_at: Date.now(),
      ...metadata
    };
    
    await dragonflyClient.hSet(key, data);
    return true;
  } catch (e) {
    debugLog(`❌ saveToDragonfly error: ${(e as Error).message}`);
    return false;
  }
}

async function semanticSearch(query: string, limit: number = 3): Promise<any[]> {
  try {
    if (!dragonflyClient) return [];
    
    // DragonflyDB 向量搜索（使用 FT.SEARCH）
    // TODO: 实现向量索引和搜索
    // 当前使用简单关键词匹配作为占位符
    
    const keys = await dragonflyClient.keys('memory:*');
    const results: any[] = [];
    
    for (const key of keys.slice(0, limit * 2)) {
      const data = await dragonflyClient.hGetAll(key);
      if (data && data.content && data.content.includes(query.slice(0, 10))) {
        results.push({
          id: key,
          content: data.content,
          type: data.type,
          _distance: 0.5 // 占位符
        });
      }
    }
    
    return results.slice(0, limit);
  } catch (e) {
    debugLog(`❌ semanticSearch error: ${(e as Error).message}`);
    return [];
  }
}
