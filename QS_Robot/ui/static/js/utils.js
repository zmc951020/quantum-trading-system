/**
 * QS Robot 前端工具库
 * 提供防抖、缓存、请求封装等通用功能
 */

// ============================================================
// 防抖函数 (Debounce)
// ============================================================
function debounce(fn, delay = 300) {
    let timer;
    return function (...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), delay);
    };
}

// ============================================================
// 节流函数 (Throttle)
// ============================================================
function throttle(fn, interval = 300) {
    let lastTime = 0;
    return function (...args) {
        const now = Date.now();
        if (now - lastTime >= interval) {
            lastTime = now;
            fn.apply(this, args);
        }
    };
}

// ============================================================
// 前端缓存 (localStorage based)
// ============================================================
const APICache = {
    _prefix: 'qs_cache_',
    _defaultTTL: 5 * 60 * 1000,  // 默认5分钟

    /**
     * 获取缓存
     * @param {string} key - 缓存键
     * @returns {*} 缓存值，过期返回 null
     */
    get(key) {
        try {
            const raw = localStorage.getItem(this._prefix + key);
            if (!raw) return null;
            const entry = JSON.parse(raw);
            if (Date.now() - entry.timestamp > (entry.ttl || this._defaultTTL)) {
                localStorage.removeItem(this._prefix + key);
                return null;
            }
            return entry.data;
        } catch (e) {
            return null;
        }
    },

    /**
     * 设置缓存
     * @param {string} key - 缓存键
     * @param {*} data - 缓存数据
     * @param {number} ttl - 过期时间(ms)，默认5分钟
     */
    set(key, data, ttl = null) {
        try {
            const entry = {
                data: data,
                timestamp: Date.now(),
                ttl: ttl || this._defaultTTL
            };
            localStorage.setItem(this._prefix + key, JSON.stringify(entry));
        } catch (e) {
            // localStorage 满了，清除过期条目
            this.clearExpired();
        }
    },

    /**
     * 清除过期缓存
     */
    clearExpired() {
        const keys = Object.keys(localStorage);
        for (const key of keys) {
            if (key.startsWith(this._prefix)) {
                try {
                    const entry = JSON.parse(localStorage.getItem(key));
                    if (Date.now() - entry.timestamp > (entry.ttl || this._defaultTTL)) {
                        localStorage.removeItem(key);
                    }
                } catch (e) {
                    localStorage.removeItem(key);
                }
            }
        }
    },

    /**
     * 清除所有缓存
     */
    clearAll() {
        const keys = Object.keys(localStorage);
        for (const key of keys) {
            if (key.startsWith(this._prefix)) {
                localStorage.removeItem(key);
            }
        }
    }
};

// ============================================================
// 带缓存的 fetch 请求
// ============================================================
async function cachedFetch(url, options = {}, cacheTTL = null) {
    const cacheKey = url + (options.body || '');
    const cached = APICache.get(cacheKey);
    if (cached !== null) {
        return cached;
    }
    try {
        const resp = await fetch(url, options);
        const data = await resp.json();
        APICache.set(cacheKey, data, cacheTTL);
        return data;
    } catch (e) {
        console.error('[cachedFetch] 请求失败:', url, e);
        throw e;
    }
}

// 自动清理过期缓存（每10分钟）
setInterval(() => APICache.clearExpired(), 10 * 60 * 1000);