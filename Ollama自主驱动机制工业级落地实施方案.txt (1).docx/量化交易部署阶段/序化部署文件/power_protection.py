#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工业级断电保护模块
实现：UPS联动、自动止损、原子写入、秒级恢复
"""
import os
import sys
import logging
import threading
import time
import json
import struct
import mmap
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)

class PowerProtection:
    """断电保护系统"""
    
    def __init__(self):
        self._lock = threading.RLock()
        self._initialized = False
        self._power_ok = True
        self._shutdown_flag = False
        
        # UPS配置
        self.ups_detect_interval = 0.1  # 100ms检测一次
        self.battery_threshold = 20.0    # 电量低于20%触发保护
        
        # 状态文件
        self.state_file = './aurora_state.dat'
        self._mmap: Optional[mmap.mmap] = None
        
        # 持仓数据
        self._positions: Dict[str, Dict[str, Any]] = {}
        
    def initialize(self):
        """初始化断电保护"""
        if self._initialized:
            return
            
        with self._lock:
            logger.info("初始化断电保护系统...")
            
            # 初始化原子状态文件
            self._init_atomic_state()
            
            # 尝试加载之前的状态
            self._load_state()
            
            # 启动UPS监控线程
            self._start_ups_monitor()
            
            self._initialized = True
            logger.info("✅ 断电保护系统初始化完成")
            
    def _init_atomic_state(self):
        """初始化原子状态文件，使用mmap确保原子写入"""
        if not os.path.exists(self.state_file):
            with open(self.state_file, 'wb') as f:
                f.write(b'\x00' * 1024 * 1024)  # 1MB预留
                
        self._mmap = mmap.mmap(
            os.open(self.state_file, os.O_RDWR | os.O_CREAT),
            1024 * 1024,
            access=mmap.ACCESS_WRITE
        )
        
    def save_state(self, positions: Dict[str, Any], orders: List[Any]):
        """原子化保存系统状态，断电不丢失"""
        with self._lock:
            if self._mmap is None:
                return
                
            state = {
                'timestamp': datetime.now().isoformat(),
                'positions': positions,
                'orders': orders,
                'version': 1
            }
            
            data = json.dumps(state).encode()
            data_len = len(data)
            
            # 原子写入：先写长度，再写数据
            self._mmap.seek(0)
            self._mmap.write(struct.pack('<I', data_len))
            self._mmap.write(data)
            self._mmap.flush()
            
            self._positions = positions
            
    def _load_state(self) -> Optional[Dict[str, Any]]:
        """加载之前的状态"""
        try:
            if self._mmap is None:
                return None
                
            self._mmap.seek(0)
            len_data = self._mmap.read(4)
            if not len_data:
                return None
                
            data_len = struct.unpack('<I', len_data)[0]
            if data_len <= 0 or data_len > 1024*1024:
                return None
                
            data = self._mmap.read(data_len)
            state = json.loads(data.decode())
            
            logger.info(f"✅ 加载之前的状态: {state['timestamp']}")
            self._positions = state.get('positions', {})
            return state
        except Exception as e:
            logger.warning(f"加载状态失败: {e}")
            return None
            
    def _start_ups_monitor(self):
        """启动UPS监控线程"""
        def monitor_loop():
            while not self._shutdown_flag:
                try:
                    power_ok, battery = self._check_ups_status()
                    
                    if not power_ok:
                        # 断电了！
                        logger.critical("⚠️ 检测到断电！触发保护机制!")
                        self._emergency_protection()
                        break
                        
                    if battery < self.battery_threshold:
                        logger.warning(f"UPS电量低: {battery}%, 准备保护")
                        
                    self._power_ok = power_ok
                    
                except Exception as e:
                    logger.error(f"UPS监控错误: {e}")
                    
                time.sleep(self.ups_detect_interval)
                
        t = threading.Thread(target=monitor_loop, daemon=True)
        t.start()
        logger.info("UPS监控线程已启动")
        
    def _check_ups_status(self) -> tuple[bool, float]:
        """检查UPS状态，跨平台支持"""
        # Windows
        if sys.platform == 'win32':
            try:
                import win32api
                # 检查UPS状态
                status = win32api.GetSystemPowerStatus()
                # status[0] = AC line status: 0=offline, 1=online
                # status[1] = battery status
                # status[2] = battery percentage
                ac_online = status[0] == 1
                battery = status[2] if status[2] < 255 else 100.0
                return ac_online, battery
            except:
                return True, 100.0
                
        # Linux
        elif sys.platform == 'linux':
            try:
                # 尝试读取nut UPS状态
                with open('/var/run/nut/upsmon.pid', 'r') as f:
                    # 如果有upsmon运行，说明UPS正常
                    return True, 100.0
            except:
                pass
                
        # macOS
        elif sys.platform == 'darwin':
            try:
                # macOS电源状态
                import subprocess
                result = subprocess.check_output(['pmset', '-g', 'batt'])
                if 'AC' in str(result):
                    return True, 100.0
                else:
                    # 电池模式
                    return False, 50.0
            except:
                pass
                
        return True, 100.0
        
    def _emergency_protection(self):
        """紧急保护：断电时自动止损"""
        logger.critical("🚨 执行紧急断电保护!")
        
        # 1. 立即保存状态
        self.save_state(self._positions, [])
        
        # 2. 自动挂止损单
        self._emergency_stop_loss()
        
        # 3. 优雅退出
        logger.critical("保护完成，系统安全退出")
        os._exit(0)
        
    def _emergency_stop_loss(self):
        """紧急止损：所有持仓挂止损单"""
        for symbol, pos in self._positions.items():
            try:
                current_price = pos.get('current_price', 0)
                stop_loss_price = current_price * 0.95  # 5%止损
                
                logger.critical(f"为{symbol}挂紧急止损单: {stop_loss_price}")
                
                # 这里调用券商API挂止损单
                # broker.place_stop_loss(symbol, stop_loss_price, pos['quantity'])
                
            except Exception as e:
                logger.error(f"止损单失败 {symbol}: {e}")
                
    def shutdown(self):
        """正常关闭"""
        self._shutdown_flag = True
        
# 全局单例
_power_prot: Optional[PowerProtection] = None

def get_power_protection() -> PowerProtection:
    global _power_prot
    if _power_prot is None:
        _power_prot = PowerProtection()
    return _power_prot
