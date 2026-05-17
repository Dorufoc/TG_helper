/**
 * API密钥加密工具（前端）
 * 
 * 安全机制：
 * - 使用XOR算法将明文API密钥加密
 * - 加密后立即清空明文
 * - 与后端api_encryptor.py配合使用
 */
const ApiEncryption = {
    /**
     * 加密API密钥
     * 
     * 算法说明：
     * - 将publicKey解码为字节数组
     * - 将apiKey每个字符的Unicode码与publicKey对应字节XOR
     * - 将结果Base64编码
     * 
     * @param {string} apiKey - 明文API密钥
     * @param {string} publicKey - Base64编码的公钥
     * @returns {string} Base64编码的加密数据
     */
    encryptApiKey(apiKey, publicKey) {
        const keyBytes = Uint8Array.from(atob(publicKey), c => c.charCodeAt(0));
        const keyBytesArray = Array.from(keyBytes);
        const encryptedBytes = [];
        
        for (let i = 0; i < apiKey.length; i++) {
            const charCode = apiKey.charCodeAt(i);
            const keyByte = keyBytesArray[i % keyBytesArray.length];
            encryptedBytes.push(charCode ^ keyByte);
        }
        
        const encryptedStr = String.fromCharCode(...encryptedBytes);
        return btoa(encryptedStr);
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
