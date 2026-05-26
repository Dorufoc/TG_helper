/**
 * AuthManager - 基于 SSE + 心跳的认证管理器
 *
 * 替代原有的客户端轮询机制，使用 Server-Sent Events 实时推送会话状态变更
 * 配合定期心跳保持会话活跃
 */

class AuthManager {
    constructor(options = {}) {
        this.eventSource = null;
        this.heartbeatInterval = null;
        this.reconnectTimer = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = options.maxReconnectAttempts || 10;
        this.heartbeatIntervalMs = options.heartbeatIntervalMs || 60000; // 默认60秒心跳
        this.reconnectDelayMs = options.reconnectDelayMs || 3000; // 重连延迟3秒
        this.onSessionInvalidated = options.onSessionInvalidated || (() => {});
        this.onConnected = options.onConnected || (() => {});
        this.onDisconnected = options.onDisconnected || (() => {});
        this.isConnected = false;
        this.isPageVisible = true;
        this.isDestroyed = false;
        this.visibilityHandler = null;
        this.beforeUnloadHandler = null;
        this.lastErrorTime = 0;
        this.errorCount = 0;
    }

    /**
     * 建立 SSE 连接并启动心跳
     */
    connect() {
        if (this.eventSource || this.isDestroyed) {
            return;
        }

        // 监听页面可见性变化，避免后台页面频繁重连
        this.setupVisibilityHandler();

        // 监听页面卸载，清理连接
        this.setupBeforeUnloadHandler();

        try {
            this.eventSource = new EventSource('/api/events');

            this.eventSource.addEventListener('connected', (e) => {
                if (this.isDestroyed) return;
                try {
                    const data = JSON.parse(e.data);
                    console.log('[AuthManager] SSE 连接已建立:', data.username);
                    this.isConnected = true;
                    this.reconnectAttempts = 0;
                    this.errorCount = 0;
                    this.startHeartbeat();
                    this.onConnected(data);
                } catch (error) {
                    console.error('[AuthManager] 解析连接数据失败:', error);
                }
            });

            this.eventSource.addEventListener('session_invalidated', (e) => {
                if (this.isDestroyed) return;
                try {
                    const data = JSON.parse(e.data);
                    console.warn('[AuthManager] 会话已失效:', data.reason);
                    this.isConnected = false;
                    this.stopHeartbeat();
                    this.onSessionInvalidated(data);
                    this.cleanupEventSource();
                } catch (error) {
                    console.error('[AuthManager] 解析会话失效数据失败:', error);
                }
            });

            this.eventSource.addEventListener('heartbeat', () => {
                // 服务端心跳保活，无需特别处理
            });

            this.eventSource.onerror = (error) => {
                // 如果实例已销毁，完全忽略错误
                if (this.isDestroyed) {
                    return;
                }

                // 如果页面在后台，静默处理
                if (!this.isPageVisible) {
                    this.scheduleReconnect(30000);
                    return;
                }

                // 清理当前的 EventSource
                this.cleanupEventSource();

                // 限制错误日志频率，避免刷屏
                const now = Date.now();
                if (now - this.lastErrorTime > 5000) {
                    this.errorCount = 0;
                }
                this.lastErrorTime = now;
                this.errorCount++;

                // 只有前几次错误才输出日志
                if (this.errorCount <= 2 && this.isConnected) {
                    console.log('[AuthManager] 连接中断，正在重连...');
                }

                this.isConnected = false;
                this.stopHeartbeat();
                this.onDisconnected();
                this.scheduleReconnect();
            };
        } catch (error) {
            if (!this.isDestroyed) {
                console.error('[AuthManager] 创建 EventSource 失败:', error);
                this.scheduleReconnect();
            }
        }
    }

    /**
     * 清理 EventSource，不触发错误回调
     */
    cleanupEventSource() {
        if (this.eventSource) {
            // 先移除错误处理器，避免关闭时触发错误回调
            this.eventSource.onerror = null;
            this.eventSource.close();
            this.eventSource = null;
        }
    }

    /**
     * 设置页面可见性监听
     */
    setupVisibilityHandler() {
        if (this.visibilityHandler) {
            document.removeEventListener('visibilitychange', this.visibilityHandler);
        }

        this.visibilityHandler = () => {
            const wasVisible = this.isPageVisible;
            this.isPageVisible = !document.hidden;

            // 页面从后台回到前台，且当前未连接
            if (this.isPageVisible && !wasVisible && !this.isConnected && !this.eventSource && !this.isDestroyed) {
                console.log('[AuthManager] 页面回到前台，恢复连接');
                this.reconnectAttempts = 0;
                this.errorCount = 0;
                this.connect();
            }
        };

        document.addEventListener('visibilitychange', this.visibilityHandler);
    }

    /**
     * 设置页面卸载监听
     */
    setupBeforeUnloadHandler() {
        if (this.beforeUnloadHandler) {
            window.removeEventListener('beforeunload', this.beforeUnloadHandler);
        }

        this.beforeUnloadHandler = () => {
            this.isDestroyed = true;
            this.cleanup();
        };

        window.addEventListener('beforeunload', this.beforeUnloadHandler);
    }

    /**
     * 断开 SSE 连接并停止心跳
     */
    disconnect() {
        this.cleanup();
    }

    /**
     * 清理所有资源
     */
    cleanup() {
        this.stopHeartbeat();
        this.stopReconnectTimer();
        this.cleanupEventSource();
        this.isConnected = false;
    }

    /**
     * 完全销毁，清理所有资源和监听器
     */
    destroy() {
        this.isDestroyed = true;
        this.cleanup();

        if (this.visibilityHandler) {
            document.removeEventListener('visibilitychange', this.visibilityHandler);
            this.visibilityHandler = null;
        }

        if (this.beforeUnloadHandler) {
            window.removeEventListener('beforeunload', this.beforeUnloadHandler);
            this.beforeUnloadHandler = null;
        }
    }

    /**
     * 启动定期心跳
     */
    startHeartbeat() {
        this.stopHeartbeat();
        this.heartbeatInterval = setInterval(async () => {
            if (!this.isPageVisible || this.isDestroyed) {
                return;
            }
            await this.sendHeartbeat();
        }, this.heartbeatIntervalMs);
    }

    /**
     * 停止心跳
     */
    stopHeartbeat() {
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
            this.heartbeatInterval = null;
        }
    }

    /**
     * 发送心跳请求
     */
    async sendHeartbeat() {
        if (!this.isConnected || this.isDestroyed) return;

        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 5000);

            const response = await fetch('/api/heartbeat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
                signal: controller.signal
            });

            clearTimeout(timeoutId);

            if (!response.ok) {
                return;
            }

            const data = await response.json();
            if (!data.valid) {
                console.warn('[AuthManager] 会话已失效:', data.reason);
                this.disconnect();
                this.onSessionInvalidated({ reason: data.reason });
            }
        } catch (error) {
            // 忽略取消请求的错误和销毁后的错误
            if (error.name === 'AbortError' || this.isDestroyed) {
                return;
            }
            // 心跳错误不输出日志，避免刷屏
        }
    }

    /**
     * 计划重连
     * @param {number} [customDelay] - 自定义延迟时间（毫秒）
     */
    scheduleReconnect(customDelay) {
        if (this.isDestroyed || this.reconnectTimer) {
            return;
        }

        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.log('[AuthManager] 已达到最大重连次数');
            return;
        }

        this.reconnectAttempts++;

        // 使用自定义延迟或指数退避
        const delay = customDelay || Math.min(
            this.reconnectDelayMs * Math.pow(2, this.reconnectAttempts - 1),
            30000 // 最大30秒
        );

        this.reconnectTimer = setTimeout(() => {
            this.reconnectTimer = null;
            if (!this.isDestroyed) {
                this.connect();
            }
        }, delay);
    }

    /**
     * 停止重连定时器
     */
    stopReconnectTimer() {
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
    }
}

// 导出
if (typeof window !== 'undefined') {
    window.AuthManager = AuthManager;
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = { AuthManager };
}
