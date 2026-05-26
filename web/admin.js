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
let authManager = null;

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

const DEFAULT_SETTINGS = {
    account: {
        default_role: 'guest',
        auth_timeout_minutes: 1
    },
    ai_providers: {
        openai: {
            base_url: 'https://api.openai.com',
            api_key: '',
            model_id: 'gpt-4o',
            max_tokens: 4096
        },
        anthropic: {
            base_url: 'https://api.anthropic.com',
            api_key: '',
            model_id: 'claude-3-5-sonnet-latest',
            max_tokens: 4096
        }
    },
    ai_agents: {
        question_analysis: {
            name: '题目解析 Agent',
            provider: 'openai',
            model_id: '',
            temperature: 0.7,
            max_tokens: 500,
            system_prompt: ''
        }
    }
};

const AI_PROVIDER_META = {
    openai: {
        label: 'OpenAI',
        description: '适合通用对话与推理任务'
    },
    anthropic: {
        label: 'Anthropic',
        description: '适合长上下文与稳健生成'
    }
};

function deepClone(value) {
    return JSON.parse(JSON.stringify(value));
}

function mergeWithDefaults(defaults, source) {
    if (!defaults || typeof defaults !== 'object' || Array.isArray(defaults)) {
        return source ?? defaults;
    }
    const output = {};
    const safeSource = source && typeof source === 'object' && !Array.isArray(source) ? source : {};
    Object.keys(defaults).forEach((key) => {
        output[key] = mergeWithDefaults(defaults[key], safeSource[key]);
    });
    Object.keys(safeSource).forEach((key) => {
        if (!(key in output)) {
            output[key] = safeSource[key];
        }
    });
    return output;
}

function normalizeSettings(rawSettings) {
    if (!rawSettings || typeof rawSettings !== 'object') {
        return mergeWithDefaults(DEFAULT_SETTINGS, {});
    }
    const merged = mergeWithDefaults(DEFAULT_SETTINGS, rawSettings);
    if (typeof merged.ai_agents?.question_analysis?.temperature !== 'number') {
        merged.ai_agents.question_analysis.temperature = 0.7;
    }
    return merged;
}

createApp({
    components: {
        Md3Select: window.Md3Select
    },
    data() {
        return {
            isLoggedIn: false,
            username: '',
            isAdmin: false,
            isDarkMode: false,
            activeTab: 'users',
            drawerOpen: true,
            isMobile: false,
            loginForm: {
                username: '',
                password: '',
                captcha: ''
            },
            loginLoading: false,
            loginError: '',
            captchaUrl: '/api/captcha?t=' + Date.now(),
            users: [],
            notification: null,
            confirmModal: {
                show: false,
                title: '',
                message: '',
                onConfirm: () => {}
            },
            changePasswordModal: {
                show: false,
                username: '',
                newPassword: '',
                confirmPassword: ''
            },
            questionBankList: [],
            showUploadModal: false,
            showRenameModalFlag: false,
            isDragOver: false,
            dragCounter: 0,
            selectedUploadFile: null,
            uploadProgress: 0,
            renameForm: {
                oldName: '',
                newName: '',
                oldFilename: ''
            },
            activeAiProvider: 'openai',
            savingSettings: false,
            settings: deepClone(DEFAULT_SETTINGS)
        };
    },
    computed: {
        activeUsers() {
            return this.users.filter(u => u.role !== 'banned').length;
        },
        bannedUsers() {
            return this.users.filter(u => u.role === 'banned').length;
        },
        adminUsers() {
            return this.users.filter(u => u.role === 'admin').length;
        },
        guestUsers() {
            return this.users.filter(u => u.role === 'guest').length;
        },
        analysisAgent() {
            return this.settings.ai_agents.question_analysis;
        },
        analysisProviderMeta() {
            return AI_PROVIDER_META[this.analysisAgent.provider] || AI_PROVIDER_META.openai;
        },
        getThumbPosition() {
            const positions = {
                'openai': '4px',
                'anthropic': '50%'
            };
            return positions[this.activeAiProvider] || positions.openai;
        }
    },
    async created() {
        const savedTheme = localStorage.getItem('theme');
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        if (savedTheme === 'dark' || (!savedTheme && prefersDark)) {
            this.isDarkMode = true;
            document.body.classList.add('dark-mode');
        }
        this.isMobile = window.innerWidth < 768;
        this.drawerOpen = !this.isMobile;
        window.addEventListener('resize', () => {
            this.isMobile = window.innerWidth < 768;
        });
        await this.checkLoginStatus();
        if (this.isAdmin) {
            await this.loadQuestionBankList();
            await this.loadSettings();
        }
    },
    beforeUnmount() {
        if (authManager) {
            authManager.disconnect();
            authManager = null;
        }
    },
    methods: {
        formatPassword(password) {
            /* 格式化密码显示，截断长哈希值 */
            if (!password || password.length <= 12) {
                return password;
            }
            return password.substring(0, 8) + '...' + password.substring(password.length - 4);
        },
        formatLastLogin(lastLogin) {
            /* 格式化上次登录时间显示 */
            if (!lastLogin || lastLogin === '从未登录') {
                return '从未登录';
            }
            try {
                const date = new Date(lastLogin);
                if (isNaN(date.getTime())) {
                    return lastLogin;
                }
                const year = date.getFullYear();
                const month = String(date.getMonth() + 1).padStart(2, '0');
                const day = String(date.getDate()).padStart(2, '0');
                const hours = String(date.getHours()).padStart(2, '0');
                const minutes = String(date.getMinutes()).padStart(2, '0');
                return `${year}-${month}-${day} ${hours}:${minutes}`;
            } catch (e) {
                return lastLogin;
            }
        },
        toggleDrawer() {
            this.drawerOpen = !this.drawerOpen;
        },
        switchTab(tab) {
            this.activeTab = tab;
            if (this.isMobile) {
                this.drawerOpen = false;
            }
        },
        getTabTitle() {
            const titles = {
                users: '用户管理',
                question_bank: '题库管理',
                settings: '系统设置'
            };
            return titles[this.activeTab] || '管理后台';
        },
        getTabSubtitle() {
            const subtitles = {
                users: '管理系统用户、角色和权限',
                question_bank: '上传、管理和维护题库文件',
                settings: '配置账号系统、AI 服务商与内部 Agent'
            };
            return subtitles[this.activeTab] || '';
        },
        getProviderLabel(provider) {
            return AI_PROVIDER_META[provider]?.label || provider;
        },
        toggleDarkMode() {
            this.isDarkMode = !this.isDarkMode;
            if (this.isDarkMode) {
                document.body.classList.add('dark-mode');
                localStorage.setItem('theme', 'dark');
            } else {
                document.body.classList.remove('dark-mode');
                localStorage.setItem('theme', 'light');
            }
        },
        async checkLoginStatus() {
            try {
                const response = await apiFetch('/api/check_login');
                const data = await response.json();
                if (data.logged_in) {
                    this.isLoggedIn = true;
                    this.username = data.username;
                    this.isAdmin = data.role === 'admin';
                    setLoggedInUsername(data.username);
                    this.startAuthManager();
                    if (this.isAdmin) {
                        await this.loadUsers();
                    }
                }
            } catch (error) {
                console.error('检查登录状态失败:', error);
            }
        },
        startAuthManager() {
            if (authManager) {
                authManager.disconnect();
            }
            authManager = new AuthManager({
                onSessionInvalidated: (data) => {
                    console.warn('会话已失效:', data.reason);
                    this.forceLogout();
                },
                onConnected: () => {
                    console.log('实时认证连接已建立');
                },
                onDisconnected: () => {
                    console.log('实时认证连接已断开');
                }
            });
            authManager.connect();
        },
        forceLogout() {
            if (authManager) {
                authManager.disconnect();
                authManager = null;
            }
            this.isLoggedIn = false;
            this.isAdmin = false;
            this.username = '';
            setLoggedInUsername(null);
            this.users = [];
            this.showNotification('会话已失效，请重新登录', 'error');
        },
        refreshCaptcha() {
            this.captchaUrl = '/api/captcha?t=' + Date.now();
        },
        async handleLogin() {
            if (!this.loginForm.username || !this.loginForm.password) {
                this.loginError = '请输入用户名和密码';
                return;
            }
            this.loginLoading = true;
            this.loginError = '';
            try {
                const response = await apiFetch('/api/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: this.loginForm.username,
                        password: this.loginForm.password,
                        captcha: this.loginForm.captcha
                    })
                });
                const data = await response.json();
                if (data.success) {
                    this.isLoggedIn = true;
                    this.username = data.username;
                    this.isAdmin = data.role === 'admin';
                    setLoggedInUsername(data.username);
                    this.startAuthManager();
                    if (this.isAdmin) {
                        await this.loadUsers();
                    }
                } else {
                    this.loginError = data.message;
                    this.refreshCaptcha();
                }
            } catch (error) {
                this.loginError = '登录失败，请稍后重试';
            } finally {
                this.loginLoading = false;
            }
        },
        async handleLogout() {
            try {
                await apiFetch('/api/logout', { method: 'POST' });
            } catch (error) {
                console.error('登出失败:', error);
            }
            this.forceLogout();
            this.loginForm = { username: '', password: '', captcha: '' };
            this.loginError = '';
            this.refreshCaptcha();
        },
        async loadUsers() {
            try {
                const response = await apiFetch('/api/admin/users');
                const data = await response.json();
                if (data.success) {
                    this.users = data.users.map(user => ({
                        ...user,
                        showPassword: false
                    }));
                }
            } catch (error) {
                this.showNotification('加载用户列表失败', 'error');
            }
        },
        async updateRole(user) {
            if (user.role === 'banned') {
                this.confirmModal = {
                    show: true,
                    title: '确认封禁',
                    message: `确定要封禁用户 ${user.username} 吗？该用户将无法登录和使用答题功能。`,
                    onConfirm: async (confirmed) => {
                        this.confirmModal.show = false;
                        if (!confirmed) {
                            user.role = user._prevRole;
                            return;
                        }
                        try {
                            const response = await apiFetch(`/api/admin/users/${user.username}/role`, {
                                method: 'PUT',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ role: user.role })
                            });
                            const data = await response.json();
                            if (data.success) {
                                this.showNotification(`用户 ${user.username} 已封禁`, 'success');
                            } else {
                                user.role = user._prevRole;
                                this.showNotification(data.message, 'error');
                            }
                        } catch (error) {
                            user.role = user._prevRole;
                            this.showNotification('操作失败', 'error');
                        }
                    }
                };
                return;
            }

            if (user._prevRole === 'banned') {
                try {
                    const response = await apiFetch(`/api/admin/users/${user.username}/role`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ role: user.role })
                    });
                    const data = await response.json();
                    if (data.success) {
                        this.showNotification(`用户 ${user.username} 已解封`, 'success');
                    } else {
                        user.role = user._prevRole;
                        this.showNotification(data.message, 'error');
                    }
                } catch (error) {
                    user.role = user._prevRole;
                    this.showNotification('操作失败', 'error');
                }
                return;
            }

            try {
                const response = await apiFetch(`/api/admin/users/${user.username}/role`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ role: user.role })
                });
                const data = await response.json();
                if (data.success) {
                    this.showNotification('角色修改成功', 'success');
                } else {
                    user.role = user._prevRole;
                    this.showNotification(data.message, 'error');
                }
            } catch (error) {
                user.role = user._prevRole;
                this.showNotification('修改失败', 'error');
            }
        },
        async resetInvitationCode(username) {
            this.confirmModal = {
                show: true,
                title: '重置邀请码',
                message: `确定要重置用户 ${username} 的邀请码吗？旧邀请码将失效。`,
                onConfirm: async (confirmed) => {
                    this.confirmModal.show = false;
                    if (confirmed) {
                        try {
                            const response = await apiFetch(`/api/admin/users/${username}/invitation_code`, {
                                method: 'PUT'
                            });
                            const data = await response.json();
                            if (data.success) {
                                this.showNotification(`邀请码已重置为新码: ${data.new_code}`, 'success');
                                await this.loadUsers();
                            } else {
                                this.showNotification(data.message, 'error');
                            }
                        } catch (error) {
                            this.showNotification('操作失败', 'error');
                        }
                    }
                }
            };
        },
        showChangePasswordModal(username) {
            this.changePasswordModal = {
                show: true,
                username: username,
                newPassword: '',
                confirmPassword: ''
            };
        },
        async handleChangePassword() {
            if (!this.changePasswordModal.newPassword || this.changePasswordModal.newPassword.length < 6) {
                this.showNotification('密码长度不能少于6个字符', 'error');
                return;
            }
            if (this.changePasswordModal.newPassword !== this.changePasswordModal.confirmPassword) {
                this.showNotification('两次输入的密码不一致', 'error');
                return;
            }
            try {
                const response = await apiFetch(`/api/admin/users/${this.changePasswordModal.username}/password`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ password: this.changePasswordModal.newPassword })
                });
                const data = await response.json();
                if (data.success) {
                    this.showNotification('密码修改成功', 'success');
                    this.changePasswordModal.show = false;
                } else {
                    this.showNotification(data.message, 'error');
                }
            } catch (error) {
                this.showNotification('修改失败', 'error');
            }
        },
        showNotification(message, type = 'info') {
            this.notification = { message, type };
            setTimeout(() => { this.notification = null; }, 3000);
        },
        async loadQuestionBankList() {
            try {
                const response = await apiFetch('/api/admin/question_bank/list');
                const data = await response.json();
                if (data.success) {
                    this.questionBankList = data.files;
                    this.showNotification(`加载题库列表成功，共 ${data.files.length} 个题库`, 'info');
                } else {
                    this.showNotification(data.message, 'error');
                }
            } catch (error) {
                console.error('加载题库列表失败:', error);
                this.showNotification('加载题库列表失败', 'error');
            }
        },
        formatFileSize(bytes) {
            if (bytes === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        },
        showRenameModal(file) {
            this.renameForm = {
                oldName: file.display_name,
                newName: file.display_name,
                oldFilename: file.filename
            };
            this.showRenameModalFlag = true;
        },
        async handleRename() {
            if (!this.renameForm.newName.trim()) {
                this.showNotification('新名称不能为空', 'error');
                return;
            }
            try {
                const response = await apiFetch('/api/admin/question_bank/rename', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        old_name: this.renameForm.oldFilename,
                        new_name: this.renameForm.newName.trim()
                    })
                });
                const data = await response.json();
                if (data.success) {
                    this.showNotification(data.message, 'success');
                    this.showRenameModalFlag = false;
                    await this.loadQuestionBankList();
                } else {
                    this.showNotification(data.message, 'error');
                }
            } catch (error) {
                console.error('重命名失败:', error);
                this.showNotification('重命名失败', 'error');
            }
        },
        confirmDeleteFile(file) {
            this.confirmModal = {
                show: true,
                title: '确认删除',
                message: `确定要删除题库 "${file.display_name}" 吗？此操作不可撤销。`,
                onConfirm: async (confirmed) => {
                    this.confirmModal.show = false;
                    if (confirmed) {
                        try {
                            const response = await apiFetch('/api/admin/question_bank/delete', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ filename: file.filename })
                            });
                            const data = await response.json();
                            if (data.success) {
                                this.showNotification(data.message, 'success');
                                await this.loadQuestionBankList();
                            } else {
                                this.showNotification(data.message, 'error');
                            }
                        } catch (error) {
                            console.error('删除失败:', error);
                            this.showNotification('删除失败', 'error');
                        }
                    }
                }
            };
        },
        handleDragOver(e) {
            e.preventDefault();
        },
        handleDragEnter(e) {
            e.preventDefault();
            this.dragCounter++;
            this.isDragOver = true;
        },
        handleDragLeave(e) {
            this.dragCounter--;
            if (this.dragCounter === 0) {
                this.isDragOver = false;
            }
        },
        handleFileDrop(e) {
            this.isDragOver = false;
            this.dragCounter = 0;
            const files = e.dataTransfer.files;
            if (files && files.length > 0) {
                const file = files[0];
                if (!file.name.endsWith('.json')) {
                    this.showNotification('仅支持JSON格式的题库文件', 'error');
                    return;
                }
                this.selectedUploadFile = file;
            }
        },
        triggerFileInput() {
            this.$refs.fileInput.click();
        },
        handleFileSelect(e) {
            const files = e.target.files;
            if (files && files.length > 0) {
                this.selectedUploadFile = files[0];
            }
        },
        async handleUpload() {
            if (!this.selectedUploadFile) {
                this.showNotification('请选择要上传的文件', 'error');
                return;
            }

            const formData = new FormData();
            formData.append('file', this.selectedUploadFile);

            this.uploadProgress = 0;

            try {
                const xhr = new XMLHttpRequest();
                
                xhr.upload.addEventListener('progress', (e) => {
                    if (e.lengthComputable) {
                        this.uploadProgress = Math.round((e.loaded / e.total) * 100);
                    }
                });

                const promise = new Promise((resolve, reject) => {
                    xhr.onload = () => {
                        if (xhr.status >= 200 && xhr.status < 300) {
                            resolve(JSON.parse(xhr.responseText));
                        } else {
                            try {
                                const errorData = JSON.parse(xhr.responseText);
                                reject(new Error(errorData.message || '上传失败'));
                            } catch {
                                reject(new Error('上传失败'));
                            }
                        }
                    };
                    xhr.onerror = () => reject(new Error('网络错误'));
                });

                xhr.open('POST', '/api/admin/question_bank/upload');
                xhr.setRequestHeader('X-User-Identity', CURRENT_USERNAME || 'unknown');
                xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
                xhr.send(formData);

                this.uploadProgress = 99;

                const data = await promise;
                if (data.success) {
                    this.showNotification(data.message, 'success');
                    this.closeUploadModal();
                    await this.loadQuestionBankList();
                } else {
                    this.showNotification(data.message, 'error');
                    this.uploadProgress = 0;
                }
            } catch (error) {
                console.error('上传失败:', error);
                this.showNotification(error.message || '上传失败', 'error');
                this.uploadProgress = 0;
            }
        },
        closeUploadModal() {
            this.showUploadModal = false;
            this.selectedUploadFile = null;
            this.uploadProgress = 0;
            this.isDragOver = false;
            this.dragCounter = 0;
            if (this.$refs.fileInput) {
                this.$refs.fileInput.value = '';
            }
        },
        async loadSettings() {
            try {
                const response = await apiFetch('/api/admin/settings');
                const data = await response.json();
                if (data.success) {
                    this.settings = normalizeSettings(data.settings);
                    this.activeAiProvider = this.settings.ai_providers[this.activeAiProvider]
                        ? this.activeAiProvider
                        : (this.analysisAgent.provider || 'openai');
                } else {
                    this.showNotification('加载设置失败', 'error');
                }
            } catch (error) {
                console.error('加载设置失败:', error);
                this.showNotification('加载设置失败', 'error');
            }
        },
        async saveSettings() {
            if (!this.settings.account.auth_timeout_minutes || this.settings.account.auth_timeout_minutes < 1) {
                this.showNotification('鉴权超时时间必须至少为1分钟', 'error');
                return;
            }

            try {
                this.savingSettings = true;
                
                const providersToSave = Object.keys(this.settings.ai_providers || {});
                let hasApiKeyToUpdate = false;
                
                for (const provider of providersToSave) {
                    if (this.settings.ai_providers[provider]?.api_key && this.settings.ai_providers[provider].api_key.trim()) {
                        hasApiKeyToUpdate = true;
                        break;
                    }
                }

                let encryptedPayload = {};
                
                if (hasApiKeyToUpdate) {
                    const response = await apiFetch('/api/admin/deepseek/encryption_key');
                    const data = await response.json();
                    if (data.success) {
                        for (const provider of providersToSave) {
                            const apiKey = this.settings.ai_providers[provider].api_key;
                            if (apiKey && apiKey.trim()) {
                                const encryptedApiKey = ApiEncryption.encryptApiKey(apiKey, data.public_key);
                                encryptedPayload[`encrypted_api_key_${provider}`] = encryptedApiKey;
                                this.settings.ai_providers[provider].api_key = '';
                            }
                        }
                        encryptedPayload.key_token = data.key_token;
                    } else {
                        this.showNotification('获取加密密钥失败', 'error');
                        this.savingSettings = false;
                        return;
                    }
                }

                const savePayload = {
                    settings: deepClone(normalizeSettings(this.settings)),
                    ...encryptedPayload
                };

                const response = await apiFetch('/api/admin/settings', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(savePayload)
                });
                const data = await response.json();
                if (data.success) {
                    this.showNotification('设置保存成功', 'success');
                    if (data.settings) {
                        this.settings = data.settings;
                    } else {
                        await this.loadSettings();
                    }
                } else {
                    this.showNotification(data.message || '保存设置失败', 'error');
                }
            } catch (error) {
                console.error('保存设置失败:', error);
                this.showNotification('保存设置失败', 'error');
            } finally {
                this.savingSettings = false;
            }
        },
        async openQuestionBankEditor(file) {
            window.location.href = `/editor?filename=${encodeURIComponent(file.filename)}`;
        },

    }
}).mount('#app');
