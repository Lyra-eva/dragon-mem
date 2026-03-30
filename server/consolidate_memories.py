#!/usr/bin/env python3
"""
记忆巩固 Cron Job
从 episodes 提取高频主题 → 生成 concepts

用法:
    python3 consolidate_cron.py           # 正常执行（检查间隔）
    python3 consolidate_cron.py --force   # 强制执行
"""

import json
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

# 配置
EMBEDDING_URL = "http://127.0.0.1:9721"
LANCEDB_PATH = "/Users/lx/.openclaw/workspace/cognition/memory/lancedb"
STATE_FILE = "/Users/lx/.openclaw/workspace/cognition/memory/.consolidate_state.json"
MIN_EPISODES = 10
CONSOLIDATE_INTERVAL_HOURS = 6
MIN_THEME_COUNT = 3  # 主题出现 >= 3 次才巩固

def load_state():
    """加载巩固状态"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {"last_consolidate": None, "total_concepts": 0}

def save_state(state):
    """保存巩固状态"""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def search_lancedb(query, table, limit=50):
    """搜索 LanceDB 表"""
    import requests
    try:
        resp = requests.post(
            f"{EMBEDDING_URL}/search",
            json={"query": query, "table": table, "limit": limit},
            timeout=30
        )
        if resp.ok:
            return resp.json().get("results", [])
    except Exception as e:
        print(f"搜索失败：{e}")
    return []

def save_to_lancedb(table, content, metadata):
    """保存到 LanceDB"""
    import requests
    try:
        resp = requests.post(
            f"{EMBEDDING_URL}/save",
            json={
                "table": table,
                "content": content,
                "metadata": metadata
            },
            timeout=30
        )
        return resp.ok
    except Exception as e:
        print(f"保存失败：{e}")
    return False

def extract_themes(episodes, min_count=MIN_THEME_COUNT):
    """从 episodes 提取高频主题"""
    # 简单关键词提取（词频统计）
    all_content = ' '.join([e.get('content', '') for e in episodes])
    
    # 分词（简单按标点和空格分割）
    import re
    words = re.split(r'[\s,，。！？、；：""''（）\[\]{}]+', all_content)
    words = [w for w in words if len(w) >= 2 and len(w) <= 20]
    
    # 词频统计
    freq = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    
    # 过滤高频词
    themes = [
        (word, count) 
        for word, count in freq.items() 
        if count >= min_count
    ]
    themes.sort(key=lambda x: x[1], reverse=True)
    
    return themes[:10]  # 返回 top 10

def consolidate(force=False):
    """执行记忆巩固"""
    print(f"[{datetime.now().isoformat()}] 开始记忆巩固")
    
    # 1. 加载状态
    state = load_state()
    now = datetime.now()
    
    # 2. 检查间隔
    if not force and state.get("last_consolidate"):
        last = datetime.fromisoformat(state["last_consolidate"])
        if now - last < timedelta(hours=CONSOLIDATE_INTERVAL_HOURS):
            remaining = CONSOLIDATE_INTERVAL_HOURS - (now - last).total_seconds() / 3600
            print(f"距离下次巩固还有 {remaining:.1f} 小时")
            return {"status": "skipped", "reason": "interval"}
    
    # 3. 获取 episodes
    episodes = search_lancedb("对话记忆", "episodes", limit=50)
    print(f"获取到 {len(episodes)} 条 episodes")
    
    if len(episodes) < MIN_EPISODES:
        print(f"episodes 仅 {len(episodes)} 条，不足 {MIN_EPISODES} 条，跳过巩固")
        return {"status": "skipped", "reason": "insufficient_episodes"}
    
    # 4. 提取主题
    themes = extract_themes(episodes)
    print(f"发现 {len(themes)} 个高频主题")
    
    if not themes:
        state["last_consolidate"] = now.isoformat()
        save_state(state)
        return {"status": "completed", "themes_found": 0, "concepts_created": 0}
    
    # 5. 为每个主题创建 concept
    created = 0
    for theme, count in themes:
        # 检查是否已存在
        existing = search_lancedb(theme, "concepts", limit=1)
        if existing and len(existing) > 0 and existing[0].get('_distance', 1.0) < 0.3:
            print(f"  跳过：{theme} (已存在)")
            continue
        
        # 从相关 episodes 中提取上下文
        related = [e for e in episodes if theme in e.get('content', '')][:3]
        context = ' | '.join([e['content'][:100] for e in related])
        
        # 创建 concept
        success = save_to_lancedb(
            "concepts",
            f"{theme}: {context}",
            {
                "title": f"对话主题：{theme}",
                "category": "consolidated",
                "tags": json.dumps(["auto_consolidated", "from_episodes"]),
                "quality_score": min(0.5 + count * 0.05, 0.9),
            }
        )
        
        if success:
            created += 1
            print(f"  创建：{theme}({count}次)")
    
    # 6. 更新状态
    state["last_consolidate"] = now.isoformat()
    state["total_concepts"] = state.get("total_concepts", 0) + created
    save_state(state)
    
    result = {
        "status": "completed",
        "episodes_analyzed": len(episodes),
        "themes_found": len(themes),
        "concepts_created": created,
        "themes": [f"{t}({c}次)" for t, c in themes]
    }
    
    print(f"巩固完成：{result}")
    return result

if __name__ == "__main__":
    force = "--force" in sys.argv
    result = consolidate(force)
    
    # 输出 JSON 结果（便于 cron 记录）
    print(json.dumps(result, ensure_ascii=False, indent=2))
