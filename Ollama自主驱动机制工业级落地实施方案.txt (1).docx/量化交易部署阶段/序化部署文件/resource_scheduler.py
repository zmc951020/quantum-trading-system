#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
硬件资源智能调度器
实现：CPU核心绑定、GPU显存隔离、内存自动GC、关键时刻资源抢占
兼容Windows/Linux/macOS
"""
import os
import sys
import psutil
import logging
import threading
import time
from typing import Optional, List
try:
    import pynvml
    NVML_AVAILABLE = True
except ImportError:
    NVML_AVAILABLE = False

logger = logging.getLogger(__name__)

class ResourceScheduler:
    """硬件资源智能调度器"""
    
    def __init__(self):
        self._lock = threading.RLock()
        self._initialized = False
        self._critical_mode = False
        
        # CPU 核心配置
        self._trade_core: Optional[int] = None
        self._background_cores: List[int] = []
        
        # GPU 配置
        self._gpu_device: int = 0
        self._vllm_reserved_mem: int = 0  # 预留显存 MB
        self._train_max_mem: int = 0      # 训练最大可用 MB
        
        # 内存配置
        self._memory_threshold: float = 0.85  # 85% 触发GC
        
        self._init_hardware_info()
        
    def _init_hardware_info(self):
        """初始化硬件信息"""
        cpu_count = psutil.cpu_count(logical=False) or 8
        logical_count = psutil.cpu_count(logical=True) or 16
        
        # 自动分配核心：最后一个大核给交易，前面的给后台
        if logical_count >= 8:
            self._trade_core = logical_count - 1  # 最后一个逻辑核
            self._background_cores = list(range(0, logical_count - 1))
        else:
            self._trade_core = 0
            self._background_cores = list(range(1, logical_count))
            
        logger.info(f"CPU核心分配: 交易核={self._trade_core}, 后台核={self._background_cores}")
        
        # GPU 初始化
        if NVML_AVAILABLE:
            try:
                pynvml.nvmlInit()
                device_count = pynvml.nvmlDeviceGetCount()
                if device_count > 0:
                    self._gpu_device = 0
                    handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                    mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                    total_mem = mem_info.total // 1024 // 1024  # MB
                    
                    # VLLM预留60%显存
                    self._vllm_reserved_mem = int(total_mem * 0.6)
                    self._train_max_mem = total_mem - self._vllm_reserved_mem
                    
                    logger.info(f"GPU显存分配: VLLM预留={self._vllm_reserved_mem}MB, 训练最大={self._train_max_mem}MB")
            except Exception as e:
                logger.warning(f"GPU初始化失败: {e}")
                NVML_AVAILABLE = False
                
    def bind_trade_thread(self):
        """将当前线程绑定到交易专用核心"""
        if self._trade_core is None:
            return
            
        try:
            p = psutil.Process()
            if sys.platform == 'win32':
                # Windows
                p.cpu_affinity([self._trade_core])
            else:
                # Linux/macOS
                os.sched_setaffinity(0, [self._trade_core])
                
            # 设置最高优先级
            p.nice(-20)
            logger.info(f"交易线程已绑定到核心 {self._trade_core}, 优先级最高")
        except Exception as e:
            logger.warning(f"CPU核心绑定失败: {e}")
            
    def bind_background_thread(self):
        """将当前线程绑定到后台核心"""
        if not self._background_cores:
            return
            
        try:
            p = psutil.Process()
            if sys.platform == 'win32':
                p.cpu_affinity(self._background_cores)
            else:
                os.sched_setaffinity(0, self._background_cores)
                
            # 设置低优先级
            p.nice(10)
            logger.debug(f"后台线程已绑定到核心 {self._background_cores}")
        except Exception as e:
            logger.warning(f"后台核心绑定失败: {e}")
            
    def check_gpu_memory(self) -> bool:
        """检查GPU显存是否足够"""
        if not NVML_AVAILABLE:
            return True
            
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(self._gpu_device)
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            used_mem = mem_info.used // 1024 // 1024
            
            # 如果训练用的显存超过限制，返回False
            train_used = used_mem - self._vllm_reserved_mem
            if train_used > self._train_max_mem:
                logger.warning(f"GPU显存不足: 已用{train_used}MB, 限制{self._train_max_mem}MB")
                return False
                
            return True
        except Exception as e:
            logger.warning(f"GPU显存检查失败: {e}")
            return True
            
    def check_memory(self) -> bool:
        """检查内存，触发GC"""
        mem = psutil.virtual_memory()
        usage = mem.percent / 100.0
        
        if usage > self._memory_threshold:
            logger.warning(f"内存使用率过高: {usage:.1%}, 触发GC")
            import gc
            gc.collect()
            return False
            
        return True
        
    def enter_critical_mode(self):
        """进入关键模式：暂停所有后台任务，全力保障交易"""
        with self._lock:
            if self._critical_mode:
                return
            self._critical_mode = True
            
        logger.warning("⚠️ 进入关键行情模式，暂停后台任务，全力保障交易!")
        
        # 暂停后台线程
        self._pause_background_tasks()
        
        # 触发GC释放内存
        self.check_memory()
        
    def exit_critical_mode(self):
        """退出关键模式，恢复后台任务"""
        with self._lock:
            if not self._critical_mode:
                return
            self._critical_mode = False
            
        logger.info("退出关键行情模式，恢复后台任务")
        self._resume_background_tasks()
        
    def _pause_background_tasks(self):
        """暂停后台任务"""
        # 暂停训练、回测等非关键任务
        for proc in psutil.process_iter():
            try:
                if proc.name() in ['python', 'python3']:
                    # 检查是否是后台进程
                    cmdline = proc.cmdline()
                    if any(x in str(cmdline) for x in ['train', 'backtest', 'ml']):
                        proc.suspend()
                        logger.debug(f"暂停后台进程: {proc.pid}")
            except:
                pass
                
    def _resume_background_tasks(self):
        """恢复后台任务"""
        for proc in psutil.process_iter():
            try:
                if proc.status() == psutil.STATUS_STOPPED:
                    proc.resume()
                    logger.debug(f"恢复后台进程: {proc.pid}")
            except:
                pass
                
    def start_monitor(self):
        """启动资源监控线程"""
        def monitor_loop():
            while True:
                try:
                    self.check_memory()
                    self.check_gpu_memory()
                    
                    # 检查是否有行情波动，自动进入关键模式
                    # 这里会被策略引擎触发
                    
                except Exception as e:
                    logger.error(f"资源监控错误: {e}")
                    
                time.sleep(1)
                
        t = threading.Thread(target=monitor_loop, daemon=True)
        t.start()
        logger.info("资源监控线程已启动")
        
# 全局单例
_scheduler: Optional[ResourceScheduler] = None

def get_scheduler() -> ResourceScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = ResourceScheduler()
    return _scheduler
