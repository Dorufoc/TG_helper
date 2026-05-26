/**
 * API密钥加密工具（前端）
 *
 * 安全机制：
 * - 使用AES-256-GCM算法将明文API密钥加密
 * - 加密后立即清空明文
 * - 与后端api_encryptor.py配合使用
 */
const ApiEncryption = {
    /**
     * 加密API密钥
     *
     * 算法说明：
     * - 将publicKey解码为AES-256-GCM密钥
     * - 生成随机12字节IV
     * - 使用AES-256-GCM加密数据
     * - 将IV + ciphertext + auth_tag拼接后Base64编码
     *
     * @param {string} apiKey - 明文API密钥
     * @param {string} publicKey - Base64编码的AES密钥
     * @returns {Promise<string>} Base64编码的加密数据
     */
    async encryptApiKey(apiKey, publicKey) {
        const keyBytes = Uint8Array.from(atob(publicKey), c => c.charCodeAt(0));
        const iv = crypto.getRandomValues(new Uint8Array(12));
        const encoder = new TextEncoder();
        const plaintext = encoder.encode(apiKey);

        const cryptoKey = await crypto.subtle.importKey(
            'raw',
            keyBytes,
            { name: 'AES-GCM', length: 256 },
            false,
            ['encrypt']
        );

        const ciphertext = await crypto.subtle.encrypt(
            { name: 'AES-GCM', iv: iv },
            cryptoKey,
            plaintext
        );

        // ciphertext 包含 auth_tag（最后16字节）
        const encrypted = new Uint8Array(iv.length + ciphertext.byteLength);
        encrypted.set(iv);
        encrypted.set(new Uint8Array(ciphertext), iv.length);

        return btoa(String.fromCharCode(...encrypted));
    },

    /**
     * 清空字符串（安全销毁）
     *
     * @param {object} obj - 包含字符串的对象
     * @param {string} key - 要清空的键名
     */
    secureClear(obj, key) {
        if (obj && obj[key]) {
            obj[key] = '';
            if (typeof window !== 'undefined' && window.gc) {
                window.gc();
            }
        }
    }
};
