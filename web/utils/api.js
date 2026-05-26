/**
 * API 请求工具模块
 * 提供统一的HTTP请求方法，自动添加用户身份认证信息
 * 支持请求取消功能，避免组件卸载时的内存泄漏
 */

// 存储活跃的请求控制器，用于取消请求
const activeControllers = new Map();

/**
 * 生成唯一请求ID
 * @returns {string} 唯一ID
 */
function generateRequestId() {
    return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

/**
 * 获取带有用户身份信息的请求头
 * @returns {Object} 包含用户身份信息的请求头对象
 */
function getAuthHeaders() {
    let userIdentity;
    if (typeof CURRENT_USERNAME !== 'undefined' && CURRENT_USERNAME) {
        userIdentity = CURRENT_USERNAME;
    } else {
        userIdentity = `unknown-${typeof DEVICE_ID !== 'undefined' ? DEVICE_ID : 'unknown'}`;
    }

    return {
        'X-User-Identity': userIdentity,
        'X-Requested-With': 'XMLHttpRequest'
    };
}

/**
 * 统一的API请求方法，自动添加用户身份信息
 * @param {string} url - 请求URL
 * @param {Object} options - fetch请求选项
 * @param {AbortSignal} [options.signal] - 用于取消请求的AbortSignal
 * @returns {Promise<Response>} fetch响应对象
 */
async function apiFetch(url, options = {}) {
    const authHeaders = getAuthHeaders();
    const mergedHeaders = {
        ...authHeaders,
        ...(options.headers || {})
    };

    try {
        const response = await fetch(url, {
            ...options,
            headers: mergedHeaders,
            signal: options.signal
        });

        return response;
    } catch (error) {
        // 如果是取消请求导致的错误，静默处理
        if (error.name === 'AbortError') {
            console.log(`[apiFetch] 请求被取消: ${url}`);
            throw error;
        }
        throw error;
    }
}

/**
 * 创建可取消的API请求
 * @param {string} url - 请求URL
 * @param {Object} options - fetch请求选项
 * @returns {Object} 包含promise和cancel方法的对象
 */
function createCancellableFetch(url, options = {}) {
    const controller = new AbortController();
    const requestId = generateRequestId();

    // 存储控制器以便后续取消
    activeControllers.set(requestId, controller);

    const promise = apiFetch(url, {
        ...options,
        signal: controller.signal
    }).finally(() => {
        // 请求完成后移除控制器
        activeControllers.delete(requestId);
    });

    return {
        promise,
        cancel: () => {
            controller.abort();
            activeControllers.delete(requestId);
        },
        requestId
    };
}

/**
 * 取消所有活跃的请求
 * 适用于组件卸载时清理
 */
function cancelAllRequests() {
    activeControllers.forEach((controller, requestId) => {
        controller.abort();
        console.log(`[apiFetch] 取消请求: ${requestId}`);
    });
    activeControllers.clear();
}

/**
 * 取消指定请求
 * @param {string} requestId - 请求ID
 */
function cancelRequest(requestId) {
    const controller = activeControllers.get(requestId);
    if (controller) {
        controller.abort();
        activeControllers.delete(requestId);
    }
}

// 导出公共API
if (typeof window !== 'undefined') {
    window.apiFetch = apiFetch;
    window.createCancellableFetch = createCancellableFetch;
    window.cancelAllRequests = cancelAllRequests;
    window.cancelRequest = cancelRequest;
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        apiFetch,
        createCancellableFetch,
        cancelAllRequests,
        cancelRequest
    };
}
