const { createApp } = Vue;

function _getCookie(name) {
    const match = document.cookie.match(new RegExp('(?:^|; )' + name.replace(/([.$?*|{}()\[\]\\\/+^])/g, '\\$1') + '=([^;]*)'));
    return match ? decodeURIComponent(match[1]) : null;
}

function _setCookie(name, value, maxAgeDays) {
    let cookie = name + '=' + encodeURIComponent(value) + '; path=/; SameSite=Lax';
    if (location.protocol === 'https:') {
        cookie += '; Secure';
    }
    if (maxAgeDays) {
        cookie += '; max-age=' + (maxAgeDays * 86400);
    }
    document.cookie = cookie;
}

function generateDeviceId() {
    let deviceId = _getCookie('deviceId');
    if (!deviceId) {
        deviceId = localStorage.getItem('deviceId');
        if (deviceId) {
            _setCookie('deviceId', deviceId, 365);
            localStorage.removeItem('deviceId');
        } else {
            deviceId = 'dev-' + Math.random().toString(36).substring(2, 10) + Date.now().toString(36);
            _setCookie('deviceId', deviceId, 365);
        }
    }
    return deviceId;
}

const DEVICE_ID = generateDeviceId();
let CURRENT_USERNAME = null;

function setLoggedInUsername(username) {
    CURRENT_USERNAME = username;
}

function getAuthHeaders() {
    let userIdentity;
    if (CURRENT_USERNAME) {
        userIdentity = CURRENT_USERNAME;
    } else {
        userIdentity = `unknown-${DEVICE_ID}`;
    }
    return {
        'X-User-Identity': userIdentity,
        'X-Requested-With': 'XMLHttpRequest'
    };
}

async function apiFetch(url, options = {}) {
    const authHeaders = getAuthHeaders();
    const mergedHeaders = {
        ...authHeaders,
        ...(options.headers || {})
    };
    const response = await fetch(url, {
        ...options,
        headers: mergedHeaders
    });
    return response;
}

function deepClone(value) {
    return JSON.parse(JSON.stringify(value));
}

createApp({
    data() {
        return {
            isLoggedIn: false,
            isAdmin: false,
            loading: true,
            notification: null,
            confirmModal: {
                show: false,
                title: '',
                message: '',
                onConfirm: () => {}
            },
            editor: {
                filename: '',
                display_name: '',
                questions: [],
                stats: {},
                undoStack: [],
                redoStack: [],
                saving: false,
                aiLoading: false,
                aiLoadingIndex: -1
            }
        };
    },
    async created() {
        await this.checkLoginStatus();
    },
    methods: {
        showNotification(message, type = 'info') {
            this.notification = { message, type };
            setTimeout(() => { this.notification = null; }, 3000);
        },

        async checkLoginStatus() {
            try {
                const response = await apiFetch('/api/check_login');
                const data = await response.json();
                if (data.logged_in) {
                    this.isLoggedIn = true;
                    this.isAdmin = data.role === 'admin';
                    setLoggedInUsername(data.username);
                    
                    if (!this.isAdmin) {
                        this.showNotification('需要管理员权限', 'error');
                        setTimeout(() => {
                            window.location.href = '/admin';
                        }, 2000);
                        return;
                    }

                    await this.loadQuestionBank();
                } else {
                    this.loading = false;
                    this.showNotification('请先登录', 'error');
                }
            } catch (error) {
                console.error('检查登录状态失败:', error);
                this.loading = false;
            }
        },

        async loadQuestionBank() {
            const urlParams = new URLSearchParams(window.location.search);
            const filename = urlParams.get('filename');
            
            if (!filename) {
                this.showNotification('未指定题库文件', 'error');
                this.loading = false;
                setTimeout(() => {
                    window.location.href = '/admin';
                }, 2000);
                return;
            }

            try {
                const response = await apiFetch('/api/admin/question_bank/content?filename=' + encodeURIComponent(filename));
                const data = await response.json();
                if (data.success) {
                    this.editor = {
                        filename: data.filename,
                        display_name: data.display_name || filename,
                        questions: deepClone(data.questions),
                        stats: data.stats || {},
                        undoStack: [],
                        redoStack: [],
                        saving: false,
                        aiLoading: false,
                        aiLoadingIndex: -1
                    };
                    this.loading = false;
                    this.showNotification('题库加载成功，共 ' + data.total + ' 道题目', 'info');
                } else {
                    this.loading = false;
                    this.showNotification(data.message || '加载题库失败', 'error');
                    setTimeout(() => {
                        window.location.href = '/admin';
                    }, 2000);
                }
            } catch (error) {
                console.error('加载题库内容失败:', error);
                this.loading = false;
                this.showNotification('加载题库内容失败', 'error');
            }
        },

        onQuestionUpdate(index, updatedQuestion) {
            const prevState = deepClone(this.editor.questions[index]);
            this.editor.questions[index] = updatedQuestion;
            this.editor.undoStack.push({ type: 'question_update', index, prevState });
            this.editor.redoStack = [];
            this._recomputeStats();
        },

        editorUndo() {
            if (this.editor.undoStack.length === 0) return;
            const action = this.editor.undoStack.pop();
            if (action.type === 'question_update') {
                const currentState = deepClone(this.editor.questions[action.index]);
                this.editor.questions[action.index] = action.prevState;
                this.editor.redoStack.push({ type: 'question_update', index: action.index, prevState: currentState });
            }
            this._recomputeStats();
        },

        editorRedo() {
            if (this.editor.redoStack.length === 0) return;
            const action = this.editor.redoStack.pop();
            if (action.type === 'question_update') {
                const currentState = deepClone(this.editor.questions[action.index]);
                this.editor.questions[action.index] = action.prevState;
                this.editor.undoStack.push({ type: 'question_update', index: action.index, prevState: currentState });
            }
            this._recomputeStats();
        },

        async saveQuestionBank() {
            if (!this.editor.filename) return;
            try {
                this.editor.saving = true;
                const response = await apiFetch('/api/admin/question_bank/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        filename: this.editor.filename,
                        questions: deepClone(this.editor.questions)
                    })
                });
                const data = await response.json();
                if (data.success) {
                    this.editor.undoStack = [];
                    this.editor.redoStack = [];
                    this.showNotification('题库保存成功', 'success');
                } else {
                    this.showNotification(data.message || '保存失败', 'error');
                }
            } catch (error) {
                console.error('保存题库失败:', error);
                this.showNotification('保存题库失败', 'error');
            } finally {
                this.editor.saving = false;
            }
        },

        onAiStart(index) {
            this.editor.aiLoading = true;
            this.editor.aiLoadingIndex = index;
        },

        onAiDone() {
            this.editor.aiLoading = false;
            this.editor.aiLoadingIndex = -1;
        },

        onAiError(message) {
            this.editor.aiLoading = false;
            this.editor.aiLoadingIndex = -1;
            this.showNotification(message || 'AI调用失败', 'error');
        },

        _recomputeStats() {
            const stats = {};
            for (const q of this.editor.questions) {
                const type = q.type || '未知';
                stats[type] = (stats[type] || 0) + 1;
            }
            this.editor.stats = stats;
        }
    }
}).component('QuestionEditor', QuestionEditor).mount('#app');
