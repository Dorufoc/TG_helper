const { createApp } = Vue;

createApp({
    components: {
        Md3Select: window.Md3Select
    },
    data() {
        return {
            // 用户状态
            isLoggedIn: false,
            username: '',
            isDarkMode: false,

            // 布局状态
            sidebarOpen: true,
            isMobile: false,

            // 知识库列表
            kbList: [],
            currentKb: null,

            // 标签页
            activeTab: 'chat',

            // 文档列表
            documents: [],

            // 对话
            messages: [],
            inputMessage: '',
            isStreaming: false,

            // 创建/编辑知识库
            showCreateModal: false,
            editingKb: null,
            saving: false,
            kbForm: {
                name: '',
                description: '',
                embedding_model: 'text-embedding-3-small'
            },

            // 嵌入模型选项
            embeddingModels: [
                { value: 'text-embedding-3-small', label: 'OpenAI text-embedding-3-small' },
                { value: 'text-embedding-3-large', label: 'OpenAI text-embedding-3-large' },
                { value: 'text-embedding-ada-002', label: 'OpenAI text-embedding-ada-002' }
            ],

            // 上传文档
            showUploadModal: false,
            selectedFiles: [],
            uploadProgress: 0,
            isDragOver: false,
            dragCounter: 0,

            // 通知
            notification: null,

            // 确认弹窗
            confirmModal: {
                show: false,
                title: '',
                message: '',
                onConfirm: () => {}
            },

            // 事件源（用于流式输出）
            eventSource: null
        };
    },

    async created() {
        // 初始化主题
        const savedTheme = localStorage.getItem('theme');
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        if (savedTheme === 'dark' || (!savedTheme && prefersDark)) {
            this.isDarkMode = true;
            document.body.classList.add('dark-mode');
        }

        // 响应式处理
        this.isMobile = window.innerWidth < 768;
        this.sidebarOpen = !this.isMobile;
        window.addEventListener('resize', () => {
            this.isMobile = window.innerWidth < 768;
        });

        // 检查登录状态
        await this.checkLoginStatus();

        // 如果已登录，加载知识库列表
        if (this.isLoggedIn) {
            await this.loadKnowledgeBases();
        }
    },

    beforeUnmount() {
        // 关闭事件源
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
    },

    methods: {
        // ==================== 用户认证 ====================
        async checkLoginStatus() {
            try {
                const response = await apiFetch('/api/check_login');
                const data = await response.json();
                if (data.logged_in) {
                    this.isLoggedIn = true;
                    this.username = data.username;
                    setLoggedInUsername(data.username);
                }
            } catch (error) {
                console.error('检查登录状态失败:', error);
            }
        },

        // ==================== 主题切换 ====================
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

        // ==================== 布局控制 ====================
        toggleSidebar() {
            this.sidebarOpen = !this.sidebarOpen;
        },

        // ==================== 知识库管理 ====================
        async loadKnowledgeBases() {
            try {
                const response = await apiFetch('/api/rag/knowledge-bases');
                const data = await response.json();
                if (data.success) {
                    this.kbList = data.knowledge_bases || [];
                } else {
                    this.showNotification(data.message || '加载知识库失败', 'error');
                }
            } catch (error) {
                console.error('加载知识库失败:', error);
                this.showNotification('加载知识库失败', 'error');
            }
        },

        selectKnowledgeBase(kb) {
            this.currentKb = kb;
            this.activeTab = 'chat';
            this.messages = [];
            this.loadDocuments();

            if (this.isMobile) {
                this.sidebarOpen = false;
            }
        },

        openCreateModal() {
            this.editingKb = null;
            this.kbForm = {
                name: '',
                description: '',
                embedding_model: 'text-embedding-3-small'
            };
            this.showCreateModal = true;
        },

        editKnowledgeBase(kb) {
            this.editingKb = kb;
            this.kbForm = {
                name: kb.name,
                description: kb.description || '',
                embedding_model: kb.embedding_model || 'text-embedding-3-small'
            };
            this.showCreateModal = true;
        },

        async saveKnowledgeBase() {
            if (!this.kbForm.name.trim()) {
                this.showNotification('请输入知识库名称', 'error');
                return;
            }

            this.saving = true;

            try {
                const url = this.editingKb
                    ? `/api/rag/knowledge-bases/${this.editingKb.id}`
                    : '/api/rag/knowledge-bases';

                const method = this.editingKb ? 'PUT' : 'POST';

                const response = await apiFetch(url, {
                    method: method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.kbForm)
                });

                const data = await response.json();

                if (data.success) {
                    this.showNotification(
                        this.editingKb ? '知识库更新成功' : '知识库创建成功',
                        'success'
                    );
                    this.showCreateModal = false;
                    await this.loadKnowledgeBases();

                    // 如果是编辑当前选中的知识库，更新当前知识库信息
                    if (this.editingKb && this.currentKb && this.currentKb.id === this.editingKb.id) {
                        this.currentKb = { ...this.currentKb, ...this.kbForm };
                    }

                    // 如果是新建，自动选中新创建的知识库
                    if (!this.editingKb && data.knowledge_base) {
                        this.selectKnowledgeBase(data.knowledge_base);
                    }
                } else {
                    this.showNotification(data.message || '保存失败', 'error');
                }
            } catch (error) {
                console.error('保存知识库失败:', error);
                this.showNotification('保存失败', 'error');
            } finally {
                this.saving = false;
            }
        },

        confirmDeleteKb(kb) {
            this.confirmModal = {
                show: true,
                title: '删除知识库',
                message: `确定要删除知识库 "${kb.name}" 吗？此操作将删除该知识库下的所有文档和数据，不可撤销。`,
                onConfirm: async (confirmed) => {
                    this.confirmModal.show = false;
                    if (confirmed) {
                        await this.deleteKnowledgeBase(kb);
                    }
                }
            };
        },

        async deleteKnowledgeBase(kb) {
            try {
                const response = await apiFetch(`/api/rag/knowledge-bases/${kb.id}`, {
                    method: 'DELETE'
                });

                const data = await response.json();

                if (data.success) {
                    this.showNotification('知识库删除成功', 'success');
                    await this.loadKnowledgeBases();

                    // 如果删除的是当前选中的知识库，清空当前选择
                    if (this.currentKb && this.currentKb.id === kb.id) {
                        this.currentKb = null;
                        this.messages = [];
                        this.documents = [];
                    }
                } else {
                    this.showNotification(data.message || '删除失败', 'error');
                }
            } catch (error) {
                console.error('删除知识库失败:', error);
                this.showNotification('删除失败', 'error');
            }
        },

        // ==================== 文档管理 ====================
        async loadDocuments() {
            if (!this.currentKb) return;

            try {
                const response = await apiFetch(`/api/rag/knowledge-bases/${this.currentKb.id}/documents`);
                const data = await response.json();

                if (data.success) {
                    this.documents = data.documents || [];
                } else {
                    this.showNotification(data.message || '加载文档失败', 'error');
                }
            } catch (error) {
                console.error('加载文档失败:', error);
                this.showNotification('加载文档失败', 'error');
            }
        },

        // 拖拽上传处理
        handleDragOver(e) {
            e.preventDefault();
        },

        handleDragEnter(e) {
            e.preventDefault();
            this.dragCounter++;
            this.isDragOver = true;
        },

        handleDragLeave(e) {
            e.preventDefault();
            this.dragCounter--;
            if (this.dragCounter === 0) {
                this.isDragOver = false;
            }
        },

        handleFileDrop(e) {
            this.isDragOver = false;
            this.dragCounter = 0;
            const files = Array.from(e.dataTransfer.files);
            this.processFiles(files);
        },

        triggerFileInput() {
            this.$refs.fileInput.click();
        },

        handleFileSelect(e) {
            const files = Array.from(e.target.files);
            this.processFiles(files);
        },

        processFiles(files) {
            const validExtensions = ['.pdf', '.txt', '.md', '.docx'];
            const validFiles = files.filter(file => {
                const ext = '.' + file.name.split('.').pop().toLowerCase();
                return validExtensions.includes(ext);
            });

            if (validFiles.length === 0) {
                this.showNotification('请选择有效的文档文件（PDF、TXT、MD、DOCX）', 'error');
                return;
            }

            this.selectedFiles = [...this.selectedFiles, ...validFiles];
        },

        async handleUpload() {
            if (this.selectedFiles.length === 0 || !this.currentKb) {
                return;
            }

            this.uploadProgress = 0;

            try {
                // 使用 XMLHttpRequest 以便跟踪上传进度
                const uploadPromises = this.selectedFiles.map(file => {
                    return new Promise((resolve, reject) => {
                        const formData = new FormData();
                        formData.append('file', file);

                        const xhr = new XMLHttpRequest();

                        xhr.upload.addEventListener('progress', (e) => {
                            if (e.lengthComputable) {
                                this.uploadProgress = Math.round((e.loaded / e.total) * 100);
                            }
                        });

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

                        xhr.open('POST', `/api/rag/knowledge-bases/${this.currentKb.id}/documents`);
                        xhr.setRequestHeader('X-User-Identity', this.username || 'unknown');
                        xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
                        xhr.send(formData);
                    });
                });

                const results = await Promise.all(uploadPromises);
                const allSuccess = results.every(r => r.success);

                if (allSuccess) {
                    this.showNotification(`成功上传 ${this.selectedFiles.length} 个文档`, 'success');
                    this.closeUploadModal();
                    await this.loadDocuments();
                    // 更新知识库信息
                    await this.loadKnowledgeBases();
                } else {
                    const failedCount = results.filter(r => !r.success).length;
                    this.showNotification(`${failedCount} 个文档上传失败`, 'error');
                }
            } catch (error) {
                console.error('上传失败:', error);
                this.showNotification(error.message || '上传失败', 'error');
            } finally {
                this.uploadProgress = 0;
            }
        },

        closeUploadModal() {
            this.showUploadModal = false;
            this.selectedFiles = [];
            this.uploadProgress = 0;
            this.isDragOver = false;
            this.dragCounter = 0;
            if (this.$refs.fileInput) {
                this.$refs.fileInput.value = '';
            }
        },

        confirmDeleteDoc(doc) {
            this.confirmModal = {
                show: true,
                title: '删除文档',
                message: `确定要删除文档 "${doc.filename}" 吗？此操作不可撤销。`,
                onConfirm: async (confirmed) => {
                    this.confirmModal.show = false;
                    if (confirmed) {
                        await this.deleteDocument(doc);
                    }
                }
            };
        },

        async deleteDocument(doc) {
            try {
                const response = await apiFetch(
                    `/api/rag/knowledge-bases/${this.currentKb.id}/documents/${doc.id}`,
                    { method: 'DELETE' }
                );

                const data = await response.json();

                if (data.success) {
                    this.showNotification('文档删除成功', 'success');
                    await this.loadDocuments();
                    await this.loadKnowledgeBases();
                } else {
                    this.showNotification(data.message || '删除失败', 'error');
                }
            } catch (error) {
                console.error('删除文档失败:', error);
                this.showNotification('删除失败', 'error');
            }
        },

        // ==================== RAG 对话 ====================
        async sendMessage() {
            if (!this.inputMessage.trim() || this.isStreaming || !this.currentKb) {
                return;
            }

            const userMessage = this.inputMessage.trim();
            this.inputMessage = '';
            this.autoResize();

            // 添加用户消息
            this.messages.push({
                role: 'user',
                content: userMessage
            });

            // 添加助手消息占位（用于流式输出）
            const assistantMessage = {
                role: 'assistant',
                content: '',
                citations: [],
                isStreaming: true
            };
            this.messages.push(assistantMessage);
            this.isStreaming = true;

            // 滚动到底部
            this.$nextTick(() => {
                this.scrollToBottom();
            });

            try {
                // 使用 EventSource 进行流式输出
                const encodedQuery = encodeURIComponent(userMessage);
                const url = `/api/rag/knowledge-bases/${this.currentKb.id}/query/stream?query=${encodedQuery}`;

                this.eventSource = new EventSource(url);

                this.eventSource.onmessage = (event) => {
                    try {
                        const data = JSON.parse(event.data);

                        if (data.type === 'chunk') {
                            // 追加内容
                            assistantMessage.content += data.content;
                            this.$nextTick(() => {
                                this.scrollToBottom();
                            });
                        } else if (data.type === 'citations') {
                            // 接收引用来源
                            assistantMessage.citations = data.citations || [];
                        } else if (data.type === 'done') {
                            // 完成
                            assistantMessage.isStreaming = false;
                            this.isStreaming = false;
                            this.eventSource.close();
                            this.eventSource = null;
                        } else if (data.type === 'error') {
                            // 错误
                            assistantMessage.content += `\n\n[错误: ${data.message}]`;
                            assistantMessage.isStreaming = false;
                            this.isStreaming = false;
                            this.eventSource.close();
                            this.eventSource = null;
                            this.showNotification(data.message || '对话出错', 'error');
                        }
                    } catch (e) {
                        console.error('解析消息失败:', e);
                    }
                };

                this.eventSource.onerror = (error) => {
                    console.error('EventSource 错误:', error);
                    if (this.isStreaming) {
                        assistantMessage.isStreaming = false;
                        this.isStreaming = false;
                        assistantMessage.content += '\n\n[连接中断]';
                    }
                    if (this.eventSource) {
                        this.eventSource.close();
                        this.eventSource = null;
                    }
                };

            } catch (error) {
                console.error('发送消息失败:', error);
                assistantMessage.content = '发送消息失败，请稍后重试';
                assistantMessage.isStreaming = false;
                this.isStreaming = false;
                this.showNotification('发送消息失败', 'error');
            }
        },

        scrollToBottom() {
            const container = this.$refs.chatMessages;
            if (container) {
                container.scrollTop = container.scrollHeight;
            }
        },

        autoResize() {
            const textarea = this.$refs.inputArea;
            if (textarea) {
                textarea.style.height = 'auto';
                textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
            }
        },

        // ==================== 工具方法 ====================
        renderMarkdown(content) {
            if (!content) return '';
            if (typeof marked !== 'undefined') {
                const rawHtml = marked.parse(content);
                if (typeof DOMPurify !== 'undefined') {
                    return DOMPurify.sanitize(rawHtml);
                }
                return rawHtml;
            }
            return content.replace(/\n/g, '<br>');
        },

        formatFileSize(bytes) {
            if (bytes === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        },

        formatTime(timestamp) {
            if (!timestamp) return '';
            try {
                const date = new Date(timestamp);
                return date.toLocaleString('zh-CN', {
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit'
                });
            } catch (e) {
                return timestamp;
            }
        },

        getStatusText(status) {
            const statusMap = {
                'ready': '就绪',
                'processing': '处理中',
                'error': '错误',
                'pending': '等待中'
            };
            return statusMap[status] || status;
        },

        showNotification(message, type = 'info') {
            this.notification = { message, type };
            setTimeout(() => {
                this.notification = null;
            }, 3000);
        }
    }
}).mount('#app');
