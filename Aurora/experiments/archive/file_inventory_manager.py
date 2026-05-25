#!/usr/bin/env python3
import json, os
from typing import Dict, Optional
from datetime import datetime
from dataclasses import dataclass, field

@dataclass
class FileSnapshot:
    path: str
    exists: bool = True
    size: int = 0
    mtime: float = 0.0
    line_count: int = 0
    hash_md5: str = ''
    checked_at: float = 0.0

@dataclass
class HealthResult:
    key: str
    status: str
    message: str
    details: dict = field(default_factory=dict)

class FileInventoryManager:
    _instance = None
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._loaded = False
        return cls._instance

    def __init__(self):
        if self._loaded: return
        self._inventory = {}
        self._snapshots = {}
        self._load_inventory()
        self._loaded = True

    def _get_inventory_path(self):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Aurora_file_inventory.json')

    def _load_inventory(self):
        p = self._get_inventory_path()
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8') as f:
                self._inventory = json.load(f)

    def get_all_files(self): return self._inventory.get('files', {})
    def get_databases(self): return self._inventory.get('databases', {})
    def get_data_sources(self): return self._inventory.get('data_sources', [])
    def get_key_directories(self): return self._inventory.get('key_directories', [])

    def _resolve_path(self, rel):
        return os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), rel))

    def get_db_health(self):
        info = {}
        for k, v in self.get_databases().items():
            p = self._resolve_path(v['path'])
            e = {'key': k, 'path': v['path'], 'exists': os.path.exists(p)}
            if e['exists']:
                st = os.stat(p)
                e['size_mb'] = round(st.st_size/(1024*1024),1)
            info[k] = e
        return info

    def get_file_health_report(self):
        results = []
        for k, v in self.get_all_files().items():
            p = self._resolve_path(v['path'])
            if not os.path.exists(p):
                results.append({'key':k,'status':'critical','msg':'missing:'+v['path']})
            else:
                results.append({'key':k,'status':'healthy','msg':v.get('description','')+' - OK'})
        crit = sum(1 for r in results if r['status']=='critical')
        return {'overall':'critical' if crit else 'healthy','total':len(results),'criticals':crit,'details':results}

def get_inventory_manager():
    return FileInventoryManager()

if __name__ == '__main__':
    mgr = get_inventory_manager()
    r = mgr.get_file_health_report()
    print('Health:', r['overall'], ',', r['total'], 'files,', r['criticals'], 'critical')
    db = mgr.get_db_health()
    for k,v in db.items():
        print('  DB', k, ':', 'OK' if v['exists'] else 'MISSING', ',', v.get('size_mb','?'), 'MB')
    print('Self-test OK')
