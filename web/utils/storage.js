/**
 * 本地存储工具模块
 * 提供localStorage的读写封装，包括答案、暗色模式等功能
 * SEC-007: rememberedUser已迁移至auth.js使用Cookie存储
 */

// ==================== 答案存储 ====================

function saveAnswer(questionBankName, questionIndex, answer) {
    try {
        const key = `answers_${questionBankName}`;
        const savedAnswers = JSON.parse(localStorage.getItem(key) || '{}');
        savedAnswers[questionIndex] = answer;
        localStorage.setItem(key, JSON.stringify(savedAnswers));
    } catch (error) {
        console.error('保存答案失败:', error);
    }
}

function loadAnswers(questionBankName) {
    try {
        const key = `answers_${questionBankName}`;
        return JSON.parse(localStorage.getItem(key) || '{}');
    } catch (error) {
        console.error('加载答案失败:', error);
        return {};
    }
}

function clearAnswers(questionBankName) {
    try {
        const key = `answers_${questionBankName}`;
        localStorage.removeItem(key);
    } catch (error) {
        console.error('清除答案失败:', error);
    }
}

// ==================== 暗色模式 ====================

function saveDarkModePreference(isDark) {
    localStorage.setItem('darkMode', String(isDark));
}

function loadDarkModePreference() {
    const saved = localStorage.getItem('darkMode');
    return saved === 'true';
}

// ==================== 记住用户名 ====================

function saveRememberedCredentials(username) {
    if (typeof saveRememberedUser === 'function') {
        saveRememberedUser(username);
    }
}

function loadRememberedCredentials() {
    if (typeof loadRememberedUser === 'function') {
        const username = loadRememberedUser();
        return username ? { username } : null;
    }
    return null;
}

function clearRememberedCredentials() {
    if (typeof clearRememberedUser === 'function') {
        clearRememberedUser();
    }
}
