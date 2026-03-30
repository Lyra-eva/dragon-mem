#!/usr/bin/env python3
"""
DragonMem Server - DragonflyDB Unified Memory System
龙记忆服务器 - 一体化存储系统

使用 DragonflyDB 单一数据库实现：
- KV 存储（L0-L2 缓存）
- 向量搜索（L3-L4 长期记忆）
- 多智能体隔离
"""

import json
import os
import logging
import time
from typing import Dict, Any, List
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

# Config
PORT = 9722  # 使用不同端口，避免与 CortexMem 冲突
DRAGONFLY_URL = os.getenv('DRAGONFLY_URL', 'redis://localhost:6379')
LOG_PATH = os.path.expanduser('~/.openclaw/dragonmem/logs/dragon_server.log')

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(message)s',
    handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Metrics
request_count = 0
error_count = 0
start_time = datetime.now()

# DragonflyDB 客户端
dragonfly_client = None

def get_dragonfly_client():
    """获取 DragonflyDB 客户端"""
    global dragonfly_client
    if dragonfly_client is None:
        try:
            import redis
            dragonfly_client = redis.Redis.from_url(DRAGONFLY_URL, decode_responses=True)
            dragonfly_client.ping()
            logger.info('DragonflyDB connected')
        except Exception as e:
            logger.error(f'DragonflyDB connection error: {e}')
            dragonfly_client = None
    return dragonfly_client

# 向量索引配置
VECTOR_INDEX_CONFIG = {
    'index_name': 'idx:dragonmem',
    'prefix': 'memory:',
    'vector_dim': 512,
    'distance_metric': 'COSINE'
}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        logger.info(f"{self.address_string()} - {format % args}")

    def _json_response(self, data: Dict, status: int = 200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_GET(self):
        global request_count, error_count
        request_count += 1

        if self.path == '/health':
            self._handle_health()
        elif self.path == '/stats':
            self._handle_stats()
        else:
            self._json_response({'error': 'Not found'}, 404)

    def do_POST(self):
        global request_count, error_count
        request_count += 1

        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        
        try:
            data = json.loads(body) if body else {}
        except:
            data = {}

        if self.path == '/save':
            self._handle_save(data)
        elif self.path == '/search':
            self._handle_search(data)
        elif self.path == '/create_index':
            self._handle_create_index()
        else:
            self._json_response({'error': 'Not found'}, 404)

    def _handle_health(self):
        """健康检查"""
        client = get_dragonfly_client()
        
        health = {
            'status': 'ok' if client else 'degraded',
            'dragonfly': 'connected' if client else 'disconnected',
            'uptime': str(datetime.now() - start_time),
            'requests': request_count,
            'errors': error_count
        }
        
        if client:
            try:
                info = client.info('memory')
                health['memory_used'] = info.get('used_memory_human', 'N/A')
                health['keys_count'] = client.dbsize()
            except:
                pass
        
        self._json_response(health)

    def _handle_stats(self):
        """系统统计"""
        client = get_dragonfly_client()
        
        if not client:
            self._json_response({'error': 'DragonflyDB not connected'}, 503)
            return
        
        try:
            stats = {
                'total_keys': client.dbsize(),
                'memory_used': client.info('memory').get('used_memory_human', 'N/A'),
                'uptime': str(datetime.now() - start_time),
                'requests': request_count
            }
            self._json_response(stats)
        except Exception as e:
            self._json_response({'error': str(e)}, 500)

    def _handle_save(self, data: Dict):
        """保存记忆"""
        client = get_dragonfly_client()
        
        if not client:
            self._json_response({'error': 'DragonflyDB not connected'}, 503)
            return
        
        try:
            content = data.get('content', '')
            agent_id = data.get('agent_id', 'main')
            mem_type = data.get('type', 'episodic')
            metadata = data.get('metadata', {})
            
            # 生成唯一键
            key = f"memory:{agent_id}:{int(time.time() * 1000)}"
            
            # 保存数据
            memory_data = {
                'content': content,
                'type': mem_type,
                'agent_id': agent_id,
                'created_at': int(time.time() * 1000),
                **metadata
            }
            
            client.hset(key, mapping=memory_data)
            
            logger.info(f"Saved memory: {key}")
            self._json_response({'status': 'saved', 'key': key})
            
        except Exception as e:
            logger.error(f"Save error: {e}")
            self._json_response({'error': str(e)}, 500)

    def _handle_search(self, data: Dict):
        """搜索记忆"""
        client = get_dragonfly_client()
        
        if not client:
            self._json_response({'error': 'DragonflyDB not connected'}, 503)
            return
        
        try:
            query = data.get('query', '')
            agent_id = data.get('agent_id', 'main')
            limit = data.get('limit', 5)
            
            # 简单关键词搜索（TODO: 实现向量搜索）
            pattern = f"memory:{agent_id}:*"
            keys = client.keys(pattern)[:limit * 2]
            
            results = []
            for key in keys:
                data = client.hgetall(key)
                if data and query.lower() in data.get('content', '').lower():
                    results.append({
                        'id': key,
                        'content': data.get('content'),
                        'type': data.get('type'),
                        'created_at': data.get('created_at'),
                        '_distance': 0.5  # 占位符
                    })
            
            results = results[:limit]
            self._json_response({'results': results, 'count': len(results)})
            
        except Exception as e:
            logger.error(f"Search error: {e}")
            self._json_response({'error': str(e)}, 500)

    def _handle_create_index(self):
        """创建向量索引"""
        client = get_dragonfly_client()
        
        if not client:
            self._json_response({'error': 'DragonflyDB not connected'}, 503)
            return
        
        try:
            # 使用 RediSearch 语法创建向量索引
            index_name = VECTOR_INDEX_CONFIG['index_name']
            
            # 检查索引是否已存在
            try:
                client.ft(index_name).info()
                self._json_response({'status': 'exists', 'index': index_name})
                return
            except:
                pass
            
            # 创建索引（需要 RediSearch 模块）
            from redis.commands.search.indexDefinition import IndexDefinition, IndexType
            from redis.commands.search.field import TextField, VectorField, TagField
            
            schema = (
                TextField(name='content'),
                TagField(name='type'),
                TagField(name='agent_id'),
                VectorField(
                    name='embedding',
                    algorithm='FLAT',
                    attributes={
                        'TYPE': 'FLOAT32',
                        'DIM': VECTOR_INDEX_CONFIG['vector_dim'],
                        'DISTANCE_METRIC': VECTOR_INDEX_CONFIG['distance_metric']
                    }
                )
            )
            
            definition = IndexDefinition(prefix=[VECTOR_INDEX_CONFIG['prefix']], index_type=IndexType.HASH)
            
            client.ft(index_name).create_index(schema, definition=definition)
            
            logger.info(f"Created index: {index_name}")
            self._json_response({'status': 'created', 'index': index_name})
            
        except Exception as e:
            logger.error(f"Create index error: {e}")
            self._json_response({'error': str(e)}, 500)

def main():
    """主函数"""
    # 确保日志目录存在
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    
    # 测试 DragonflyDB 连接
    client = get_dragonfly_client()
    if client:
        logger.info('DragonflyDB is ready')
    else:
        logger.warning('DragonflyDB not available, starting anyway')
    
    # 启动 HTTP 服务器
    server = HTTPServer(('127.0.0.1', PORT), Handler)
    logger.info(f'DragonMem Server started on port {PORT}')
    logger.info(f'Health: http://127.0.0.1:{PORT}/health')
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info('Shutting down...')
        server.shutdown()

if __name__ == '__main__':
    main()
