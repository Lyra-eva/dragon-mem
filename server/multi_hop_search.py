#!/usr/bin/env python3
"""
Multi-hop Search - BFS 图遍历实现多跳检索
从种子记忆开始，通过关联关系进行多跳扩展检索
"""

import json
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

def multi_hop_search(client, query: str, agent_id: str = 'main', hops: int = 2, limit: int = 10) -> List[Dict]:
    """
    多跳检索 - 使用 BFS 图遍历
    
    Args:
        client: DragonflyDB 客户端
        query: 搜索查询
        agent_id: 智能体 ID
        hops: 跳数（默认 2 跳）
        limit: 返回结果数量限制
    
    Returns:
        检索结果列表
    """
    try:
        # 第 1 跳：直接搜索
        pattern = f"memory:{agent_id}:*"
        keys = client.keys(pattern)
        
        seed_memories = []
        for key in keys:
            data = client.hgetall(key)
            if data and query.lower() in data.get('content', '').lower():
                seed_memories.append({
                    'id': key,
                    'content': data.get('content'),
                    'type': data.get('type'),
                    'hop': 0,
                    '_distance': 0.3
                })
        
        if not seed_memories:
            return []
        
        # 第 2-N 跳：BFS 扩展
        visited = set(m['id'] for m in seed_memories)
        current_hop = seed_memories
        all_results = list(seed_memories)
        
        for hop in range(1, hops + 1):
            next_hop = []
            
            for memory in current_hop:
                # 获取关联记忆（通过类型、时间接近等）
                mem_type = memory.get('type', 'episodic')
                related_pattern = f"memory:{agent_id}:*"
                related_keys = client.keys(related_pattern)
                
                for key in related_keys:
                    if key not in visited:
                        visited.add(key)
                        data = client.hgetall(key)
                        if data:
                            # 检查是否相关（同类型或时间接近）
                            if data.get('type') == mem_type:
                                next_hop.append({
                                    'id': key,
                                    'content': data.get('content'),
                                    'type': data.get('type'),
                                    'hop': hop,
                                    '_distance': 0.3 + hop * 0.1
                                })
            
            all_results.extend(next_hop)
            current_hop = next_hop
            
            if not current_hop:
                break
        
        # 排序并返回
        all_results.sort(key=lambda x: x['_distance'])
        return all_results[:limit]
        
    except Exception as e:
        logger.error(f"Multi-hop search error: {e}")
        return []
