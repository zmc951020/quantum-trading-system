/**
 * 全局状态管理器 - 港大Vibe-Trading前端
 * 
 * 功能：
 *   1. 全局状态管理（单例模式）
 *   2. 发布/订阅事件系统
 *   3. 状态持久化（localStorage）
 *   4. 状态变更通知
 * 
 * 设计依据：审计报告D4维度 - 全局状态管理
 */
const StateManager = (function() {
    'use strict';
    
    // 私有状态
    let _state = {
        marketRegime: 'range',
        activeStrategies: [],
        selectedStock: null,
        selectedStrategy: null,
        alertCount: 0,
        taskProgress: {},
        poolStatus: {},
        lastUpdate: null,
    };
    
    // 从localStorage恢复
    try {
        const saved = localStorage.getItem('qs_state');
        if (saved) {
            _state = Object.assign(_state, JSON.parse(saved));
        }
    } catch(e) {}
    
    const _listeners = {};
    
    function _notify(key, oldVal, newVal) {
        const handlers = _listeners[key] || [];
        const allHandlers = _listeners['*'] || [];
        handlers.concat(allHandlers).forEach(fn => {
            try { fn(newVal, oldVal, key); } catch(e) { console.error('State listener error:', e); }
        });
    }
    
    function _save() {
        try {
            localStorage.setItem('qs_state', JSON.stringify(_state));
        } catch(e) {}
    }
    
    return {
        get(key) {
            return key ? _state[key] : {..._state};
        },
        
        set(key, value) {
            const oldVal = _state[key];
            _state[key] = value;
            _state.lastUpdate = new Date().toISOString();
            _notify(key, oldVal, value);
            _save();
        },
        
        update(partial) {
            Object.keys(partial).forEach(k => {
                const oldVal = _state[k];
                _state[k] = partial[k];
                _notify(k, oldVal, partial[k]);
            });
            _state.lastUpdate = new Date().toISOString();
            _save();
        },
        
        on(key, fn) {
            if (!_listeners[key]) _listeners[key] = [];
            _listeners[key].push(fn);
            return () => {
                const idx = _listeners[key].indexOf(fn);
                if (idx >= 0) _listeners[key].splice(idx, 1);
            };
        },
        
        reset() {
            _state = { marketRegime: 'range', activeStrategies: [], selectedStock: null, selectedStrategy: null, alertCount: 0, taskProgress: {}, poolStatus: {}, lastUpdate: null };
            _save();
        },
        
        getSnapshot() {
            return JSON.parse(JSON.stringify(_state));
        }
    };
})();

// 导出到全局
if (typeof window !== 'undefined') {
    window.StateManager = StateManager;
}
