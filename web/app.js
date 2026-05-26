const { createApp } = Vue;

const APP_TEMPLATE = `
<!-- 通知提示 -->
<toast-notification
    :message="notification?.message"
    :type="notification?.type"
    :show="notification !== null"
/>

<!-- 维护/游客提示 -->
<maintenance-modal
    :show="showMaintenanceModal"
    title="网站走丢了"
    message="网站已永久关停"
    error-hint="err:404notfind"
/>

<!-- 游客提示 -->
<maintenance-modal
    :show="showGuestAlert"
    title="出错了"
    message="您已与服务器断开连接，请检查网络设置"
    error-hint="239648423968-err"
/>

<!-- 确认弹窗 -->
<confirm-modal
    :show="confirmModal.show"
    :title="confirmModal.title"
    :message="confirmModal.message"
    @confirm="confirmModal.callback(true)"
    @cancel="confirmModal.callback(false)"
/>

<!-- 登录弹窗 -->
<login-modal
    :show="showLoginModal"
    :auth-mode="authMode"
    :auth-form="authForm"
    :auth-loading="authLoading"
    :auth-error="authError"
    :captcha-url="captchaUrl"
    @login="handleLogin"
    @register="handleRegister"
    @switch-mode="authMode = $event"
    @refresh-captcha="refreshCaptcha"
/>

<!-- 顶栏 -->
<top-bar
    v-if="step === 'answer'"
    :is-logged-in="isLoggedIn"
    :current-user="currentUser"
    :progress="progress"
    :current-index="currentIndex"
    :total-questions="totalQuestions"
    :is-dark-mode="isDarkMode"
    @logout="handleLogout"
    @toggle-dark-mode="toggleDarkMode"
    @toggle-answer-sheet="toggleAnswerSheet"
/>

<!-- 加载页面：题库选择 -->
<question-bank-list
    v-if="step === 'load'"
    :available-files="availableFiles"
    :file-path="filePath"
    :is-logged-in="isLoggedIn"
    :wrong-books="wrongBooks"
    :show-wrong-books="showWrongBooks"
    :stats="stats"
    :error="error"
    :user-role="userRole"
    @select-file="selectFile"
    @load-questions="loadQuestions"
    @toggle-wrong-books="toggleWrongBooks"
    @load-wrong-book="loadWrongBookForPractice"
    @delete-wrong-book="deleteWrongBook"
    @go-to-extract="step = 'extract'"
    @logout="handleLogout"
/>

<!-- 抽取题目页面 -->
<question-extractor
    v-if="step === 'extract'"
    :available-types="availableTypes"
    :stats="stats"
    :type-counts="typeCounts"
    :total-selected-questions="totalSelectedQuestions"
    :study-mode="studyMode"
    :auto-show-answer="autoShowAnswer"
    :shuffle-options="shuffleOptions"
    :error="error"
    @extract-questions="extractQuestions"
    @toggle-study-mode="studyMode = !studyMode"
    @toggle-auto-show-answer="autoShowAnswer = !autoShowAnswer"
    @toggle-shuffle-options="shuffleOptions = !shuffleOptions"
/>

<!-- 答题页面 -->
<div v-if="step === 'answer'" class="container">
    <!-- 进度条 -->
    <progress-bar
        :progress="progress"
        :current-index="currentIndex"
        :total="totalQuestions"
    />

    <!-- 题目卡片 -->
    <div class="question-swipe-zone">
        <question-card
            :question="currentQuestion"
            :current-index="currentIndex"
            :total-questions="totalQuestions"
            :is-answer-viewed="isAnswerViewed"
            :study-mode="studyMode"
            :user-answer="userAnswer"
            :correct-answer="correctAnswer"
            :question-transition-name="questionTransitionName"
            :question-render-key="questionRenderKey"
            :auto-show-answer="autoShowAnswer"
            @select-option="selectOption($event.option, $event.index)"
            @submit-answer="submitAnswer"
            @auto-save-answer="autoSaveAnswer"
            @touch-start="onQuestionTouchStart"
            @touch-move="onQuestionTouchMove"
            @touch-end="onQuestionTouchEnd"
            @touch-cancel="onQuestionTouchCancel"
        />
        <div class="question-swipe-hint">
            <span :class="{ 'disabled': !canGoPrev }"></span>
            <span :class="{ 'disabled': !canGoNext }"></span>
        </div>
    </div>

    <!-- 导航按钮 -->
    <div class="navigation">
        <div class="nav-left">
            <button @click="prevQuestion" class="btn btn-secondary nav-btn" :disabled="!canGoPrev">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="15 18 9 12 15 6"/>
                </svg>
            </button>
        </div>
        <div class="nav-center">
            <button @click="viewAnswer" class="btn btn-info" v-if="!isAnswerViewed && !studyMode">查看答案</button>
            <button
                v-if="studyMode"
                @click="showConfirm('确认返回', '当前进度不会保存，下次启动顺序将重新打乱', (confirmed) => { if(confirmed) restart(); } )"
                class="btn btn-primary"
            >
                返回主页面
            </button>
            <button
                v-else
                @click="submitExam"
                class="btn btn-danger"
            >
                提交考试
            </button>
        </div>
        <div class="nav-right">
            <button @click="nextQuestion" class="btn btn-secondary nav-btn" :disabled="!canGoNext">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="9 18 15 12 9 6"/>
                </svg>
            </button>
        </div>
    </div>

    <!-- 统计信息 -->
    <div class="stats-summary">
        <div class="stats-item">
            <span class="stats-label">累计正确：</span>
            <span class="stats-value correct">{{ totalCorrect }}</span>
        </div>
        <div class="stats-item">
            <span class="stats-label">累计错误：</span>
            <span class="stats-value wrong">{{ totalWrong }}</span>
        </div>
    </div>
</div>

<!-- 答题卡 -->
<answer-sheet
    :show="answerSheet.show"
    :questions="answerSheet.questions"
    :current-index="currentIndex"
    @close="answerSheet.show = false"
    @jump-to-question="jumpToQuestion"
/>

<!-- 成绩页面 -->
<result-page
    v-if="step === 'result'"
    :result="result"
    :study-mode="studyMode"
    @restart="restart"
    @generate-wrong-book="generateWrongQuestionsBook"
/>
`;

createApp({
    mixins: [answerMixin, navigationMixin],
    template: APP_TEMPLATE,

    data() {
        return {
            step: 'load',
            filePath: 'questions.json',
            availableFiles: [],
            stats: null,
            error: '',
            typeCounts: {},
            availableTypes: [],
            currentIndex: 0,
            totalQuestions: 0,
            currentQuestion: null,
            userAnswer: [],
            correctAnswer: [],
            isAnswerViewed: false,
            result: null,
            notification: null,
            confirmModal: {
                show: false,
                title: '',
                message: '',
                callback: () => {}
            },
            answerSheet: {
                show: false,
                questions: [],
                typeOrder: ['单选题', '多选题', '判断题', '填空题', '简答题', '释义题', '论述题', '编程题']
            },
            studyMode: false,
            autoShowAnswer: false,
            shuffleOptions: false,
            localQuestions: [],
            localAnswers: {},
            localViewedAnswers: {},
            isDarkMode: false,
            questionTransitionName: 'question-slide-next',
            questionRenderKey: 0,
            touchGesture: {
                startX: 0,
                startY: 0,
                deltaX: 0,
                deltaY: 0,
                active: false
            },
            showLoginModal: true,
            authMode: 'login',
            authForm: {
                username: '',
                password: '',
                confirmPassword: '',
                captcha: '',
                inviteCode: '',
                rememberPassword: false
            },
            authLoading: false,
            authError: '',
            captchaUrl: '/api/captcha?t=' + Date.now(),
            isLoggedIn: false,
            currentUser: null,
            userRole: 'user',
            showMaintenanceModal: true,
            showGuestAlert: false,
            authManager: null,
            guestAlertShown: false,
            userCheckFailedCount: 0,
            userCheckAbortController: null,
            wrongBooks: [],
            showWrongBooks: false,
            currentQuestionBankName: ''
        };
    },

    computed: {
        progress() {
            if (this.totalQuestions === 0) return 0;
            return ((this.currentIndex + 1) / this.totalQuestions) * 100;
        },
        totalSelectedQuestions() {
            let total = 0;
            for (const [type, count] of Object.entries(this.typeCounts)) {
                total += parseInt(count) || 0;
            }
            return total;
        }
    },

    provide() {
        return {
            appState: this,
            showNotification: this.showNotification,
            showConfirm: this.showConfirm
        };
    },

    async created() {
        await this.checkLoginStatus();
        this.checkGuestAccess();
        await this.loadAvailableFiles();
        if (this.isLoggedIn) {
            await this.loadWrongBooks();
            this.startAuthManager();
        }
        const savedDarkMode = localStorage.getItem('darkMode');
        if (savedDarkMode === 'true') {
            this.isDarkMode = true;
            document.body.classList.add('dark-mode');
        }
        this._boundHandleKeyboard = this.handleKeyboard.bind(this);
        document.addEventListener('keydown', this._boundHandleKeyboard);
    },

    beforeDestroy() {
        if (this.authManager) {
            this.authManager.disconnect();
            this.authManager = null;
        }
        if (this._boundHandleKeyboard) {
            document.removeEventListener('keydown', this._boundHandleKeyboard);
        }
    },

    methods: {
        selectFile(file) {
            this.filePath = file;
        },

        toggleDarkMode() {
            this.isDarkMode = !this.isDarkMode;
            if (this.isDarkMode) {
                document.body.classList.add('dark-mode');
                localStorage.setItem('darkMode', 'true');
            } else {
                document.body.classList.remove('dark-mode');
                localStorage.setItem('darkMode', 'false');
            }
        },

        showNotification(message, type = 'info') {
            this.notification = { message, type };
            setTimeout(() => {
                this.notification = null;
            }, 3000);
        },

        showConfirm(title, message, callback) {
            this.confirmModal = {
                show: true,
                title,
                message,
                callback: (result) => {
                    this.confirmModal.show = false;
                    callback(result);
                }
            };
        },

        async loadAvailableFiles() {
            this.error = '';
            try {
                const response = await apiFetch('/api/available_files');
                if (response.status === 401) {
                    this.showLoginModal = true;
                    this.refreshCaptcha();
                    return;
                }
                const data = await response.json();
                if (data.success) {
                    this.availableFiles = data.files;
                    if (this.availableFiles.length > 0) {
                        this.filePath = this.availableFiles[0];
                    }
                } else {
                    this.error = data.message;
                }
            } catch (error) {
                this.error = `获取文件列表失败: ${error.message}`;
            }
        },

        async loadWrongBooks() {
            if (!this.isLoggedIn) return;
            try {
                const response = await apiFetch('/api/available_wrong_books');
                if (response.status === 401) {
                    this.showLoginModal = true;
                    this.refreshCaptcha();
                    return;
                }
                const data = await response.json();
                if (data.success) {
                    this.wrongBooks = data.books;
                }
            } catch (error) {
                console.error('加载错题本列表失败:', error);
            }
        },

        toggleWrongBooks() {
            this.showWrongBooks = !this.showWrongBooks;
            if (this.showWrongBooks && this.isLoggedIn) {
                this.loadWrongBooks();
            }
        },

        async loadWrongBookForPractice(fileName) {
            try {
                const response = await apiFetch(`/api/load_wrong_book/${encodeURIComponent(fileName)}`);
                if (response.status === 401) {
                    this.showLoginModal = true;
                    this.refreshCaptcha();
                    return;
                }
                const data = await response.json();
                if (data.success) {
                    this.localQuestions = data.questions;
                    this.localAnswers = {};
                    this.localViewedAnswers = {};
                    this.currentIndex = 0;
                    this.totalQuestions = data.total_questions;
                    this.currentQuestion = this.localQuestions[0];
                    this.initUserAnswer();
                    this.step = 'answer';
                    this.showNotification(`已加载错题本: ${data.title}`, 'success');
                } else {
                    this.showNotification(`加载错题本失败: ${data.message}`, 'error');
                }
            } catch (error) {
                this.showNotification('加载错题本失败', 'error');
            }
        },

        async deleteWrongBook(fileName, bookTitle) {
            this.showConfirm(
                '确认删除',
                `确定要删除错题本「${bookTitle}」吗？删除后将无法恢复。`,
                async (confirmed) => {
                    if (!confirmed) return;
                    try {
                        const response = await apiFetch(`/api/delete_wrong_book/${encodeURIComponent(fileName)}`, {
                            method: 'POST'
                        });
                        if (response.status === 401) {
                            this.showLoginModal = true;
                            this.refreshCaptcha();
                            return;
                        }
                        const data = await response.json();
                        if (data.success) {
                            this.showNotification('错题本已删除', 'success');
                            await this.loadWrongBooks();
                        } else {
                            this.showNotification(`删除失败: ${data.message}`, 'error');
                        }
                    } catch (error) {
                        this.showNotification('删除失败', 'error');
                    }
                }
            );
        },

        async loadQuestions() {
            this.error = '';
            try {
                const response = await apiFetch('/api/load_questions', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ file_path: this.filePath })
                });

                if (response.status === 401) {
                    this.showLoginModal = true;
                    this.refreshCaptcha();
                    return;
                }

                const data = await response.json();
                if (data.success) {
                    this.currentQuestionBankName = this.filePath.replace('.json', '');
                    this.stats = {
                        total_questions: data.total_questions,
                        stats: data.stats
                    };
                    this.availableTypes = Object.keys(data.stats);
                    this.typeCounts = {};
                    this.availableTypes.forEach(type => {
                        this.typeCounts[type] = data.stats[type];
                    });
                    this.showNotification('题库加载成功', 'success');
                } else {
                    this.error = data.message;
                }
            } catch (error) {
                this.error = `加载失败: ${error.message}`;
            }
        },

        async extractQuestions() {
            this.error = '';
            try {
                const filteredCounts = {};
                for (const [type, count] of Object.entries(this.typeCounts)) {
                    const numCount = parseInt(count) || 0;
                    const maxCount = this.stats.stats[type];
                    if (numCount < 0) {
                        this.error = `${type}数量不能为负数`;
                        return;
                    }
                    if (numCount > maxCount) {
                        this.error = `${type}数量不能超过最大可用数量(${maxCount}题)`;
                        return;
                    }
                    if (numCount > 0) {
                        filteredCounts[type] = numCount;
                    }
                }

                if (Object.keys(filteredCounts).length === 0) {
                    this.error = '请至少选择一种题型';
                    return;
                }

                const response = await apiFetch('/api/extract_questions', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        total_count: this.totalSelectedQuestions,
                        type_ratios: filteredCounts
                    })
                });

                const data = await response.json();
                if (data.success) {
                    let questions = data.questions;
                    if (this.shuffleOptions) {
                        questions = questions.map(q => this.shuffleQuestionOptions(q));
                    }
                    this.totalQuestions = data.questions_count;
                    this.localQuestions = questions;
                    this.localAnswers = {};
                    this.localViewedAnswers = {};
                    this.step = 'answer';
                    this.currentIndex = 0;
                    this.questionTransitionName = 'question-slide-next';
                    this.questionRenderKey++;
                    this.loadCurrentQuestion();
                    this.showNotification('题目抽取成功', 'success');
                } else {
                    this.error = data.message;
                }
            } catch (error) {
                this.error = `抽取失败: ${error.message}`;
            }
        },

        submitExam() {
            this.showConfirm(
                '提交考试',
                '确定要提交考试吗？提交后将无法修改答案。',
                (confirmed) => {
                    this.confirmModal.show = false;
                    if (confirmed) {
                        this._submitExam();
                    }
                }
            );
        },

        _submitExam() {
            this.error = '';
            try {
                const total_questions = this.localQuestions.length;
                let correct_count = 0;
                const wrong_questions = [];

                for (let i = 0; i < total_questions; i++) {
                    const question = this.localQuestions[i];
                    const user_answer = this.localAnswers[i] || [];
                    const correct_answer = question.correct_answer;

                    let is_correct = false;
                    if (['单选题', '判断题', '多选题', '选择题'].includes(question.type)) {
                        is_correct = JSON.stringify(user_answer.sort()) === JSON.stringify(correct_answer.sort());
                    } else if (['填空题', '简答题', '释义题', '论述题', '编程题'].includes(question.type)) {
                        if (user_answer.length === correct_answer.length) {
                            let is_all_correct = true;
                            for (let j = 0; j < user_answer.length; j++) {
                                if (user_answer[j].trim() !== correct_answer[j].trim()) {
                                    is_all_correct = false;
                                    break;
                                }
                            }
                            is_correct = is_all_correct;
                        }
                    }

                    if (is_correct) {
                        correct_count++;
                    } else {
                        wrong_questions.push({
                            id: i + 1,
                            type: question.type,
                            content: question.content,
                            options: question.options || [],
                            user_answer: user_answer,
                            correct_answer: correct_answer,
                            analysis: question.analysis || ''
                        });
                    }
                }

                const score = total_questions > 0 ? Math.round((correct_count / total_questions) * 100 * 10) / 10 : 0;

                this.result = {
                    success: true,
                    score,
                    correct_count,
                    total_questions,
                    wrong_questions
                };

                this.step = 'result';
            } catch (error) {
                this.error = `提交失败: ${error.message}`;
            }
        },

        restart() {
            this.step = 'load';
            this.stats = null;
            this.error = '';
            this.result = null;
            this.availableTypes = [];
            this.typeCounts = {};
            this.loadAvailableFiles();
        },

        async generateWrongQuestionsBook() {
            if (!this.result || !this.result.wrong_questions || this.result.wrong_questions.length === 0) {
                this.showNotification('没有错题可以生成错题本', 'info');
                return;
            }

            try {
                const wrongQuestionData = {
                    wrong_questions: this.result.wrong_questions,
                    original_name: this.currentQuestionBankName || '错题本'
                };

                const response = await apiFetch('/api/generate_wrong_book', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(wrongQuestionData)
                });

                const data = await response.json();
                if (data.success) {
                    this.showNotification('错题本已成功生成并保存', 'success');
                    await this.loadWrongBooks();
                } else {
                    this.showNotification(`生成错题本失败: ${data.message}`, 'error');
                }
            } catch (error) {
                console.error(`生成错题本失败: ${error.message}`);
                this.showNotification('生成错题本失败', 'error');
            }
        },

        normalizeCode(code) {
            if (!code) return '';
            return code.replace(/《/g, '<').replace(/》/g, '>');
        },

        highlightCode(code, language = 'javascript') {
            if (!code) return '';
            code = this.normalizeCode(code);
            return SyntaxHighlighter.highlightSimple(code, language);
        },

        detectLanguage(content) {
            if (!content) return 'plaintext';
            const lowerContent = content.toLowerCase();

            if (lowerContent.includes('def ') || lowerContent.includes('import ') || lowerContent.includes('print(')) {
                return 'python';
            } else if (lowerContent.includes('function ') || lowerContent.includes('const ') || lowerContent.includes('let ')) {
                return 'javascript';
            } else if (lowerContent.includes('public class') || lowerContent.includes('private ') || lowerContent.includes('@controller') || lowerContent.includes('@requestmapping') || lowerContent.includes('system.out')) {
                return 'java';
            } else if (lowerContent.includes('#include') && (lowerContent.includes('printf') || lowerContent.includes('scanf'))) {
                return 'c';
            } else if (lowerContent.includes('#include') && (lowerContent.includes('std::') || lowerContent.includes('cout') || lowerContent.includes('cin'))) {
                return 'cpp';
            } else if (lowerContent.includes('<html') || lowerContent.includes('<!doctype') || lowerContent.includes('<div') || lowerContent.includes('<body') || lowerContent.includes('<form')) {
                return 'html';
            } else if (lowerContent.includes('{') && lowerContent.includes(':') && (lowerContent.includes('color') || lowerContent.includes('margin') || lowerContent.includes('padding'))) {
                return 'css';
            }

            return 'plaintext';
        },

        getCodeLanguageIcon(language) {
            const icons = {
                'python': '🐍',
                'javascript': '📜',
                'java': '☕',
                'c': '⚙️',
                'cpp': '⚙️',
                'html': '🌐',
                'css': '🎨',
                'plaintext': '📄'
            };
            return icons[language] || '📄';
        },

        copyCode(code) {
            code = this.normalizeCode(code);
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(code).then(() => {
                    this.showNotification('代码已复制到剪贴板', 'success');
                }).catch(() => {
                    this.fallbackCopy(code);
                });
            } else {
                this.fallbackCopy(code);
            }
        },

        fallbackCopy(code) {
            const textarea = document.createElement('textarea');
            textarea.value = code;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.select();
            try {
                document.execCommand('copy');
                this.showNotification('代码已复制到剪贴板', 'success');
            } catch (err) {
                this.showNotification('复制失败，请手动复制', 'error');
            }
            document.body.removeChild(textarea);
        },

        renderMarkdown(text) {
            if (!text) return '';
            const escapedText = this.escapeHtmlTagsInMarkdown(text);
            return marked.parse(escapedText);
        },

        escapeHtmlTagsInMarkdown(text) {
            const parts = [];
            const codeBlockRegex = /(```[\s\S]*?```|`[^`]*`)/g;
            let lastIndex = 0;
            let match;

            while ((match = codeBlockRegex.exec(text)) !== null) {
                if (match.index > lastIndex) {
                    parts.push({ type: 'text', content: text.substring(lastIndex, match.index) });
                }
                parts.push({ type: 'code', content: match[0] });
                lastIndex = match.index + match[0].length;
            }

            if (lastIndex < text.length) {
                parts.push({ type: 'text', content: text.substring(lastIndex) });
            }

            return parts.map(part => {
                if (part.type === 'code') {
                    return part.content;
                } else {
                    return part.content.replace(/<([a-zA-Z][a-zA-Z0-9-]*)>/g, '&lt;$1&gt;')
                                       .replace(/<\/([a-zA-Z][a-zA-Z0-9-]*)>/g, '&lt;/$1&gt;');
                }
            }).join('');
        },

        async checkLoginStatus() {
            try {
                const response = await apiFetch('/api/check_login');
                const data = await response.json();
                if (data.success && data.logged_in) {
                    this.isLoggedIn = true;
                    this.currentUser = data.username;
                    this.userRole = data.role || 'user';
                    this.showLoginModal = false;
                    this.showMaintenanceModal = (this.userRole === 'guest');
                    setLoggedInUsername(data.username);
                    this.startAuthManager();
                } else {
                    this.isLoggedIn = false;
                    this.currentUser = null;
                    this.userRole = 'user';
                    this.showLoginModal = true;
                    this.showMaintenanceModal = false;
                    setLoggedInUsername(null);
                    this.refreshCaptcha();
                    this.loadRememberedCredentials();
                }
            } catch (error) {
                console.error('检查登录状态失败:', error);
                this.showLoginModal = true;
                this.showMaintenanceModal = false;
                this.refreshCaptcha();
                this.loadRememberedCredentials();
            }
        },

        async checkBannedStatus() {
            try {
                const response = await apiFetch('/api/check_login');
                const data = await response.json();
                if (data.banned) {
                    this.showNotification('当前用户已被封禁，请退出账户重新登录', 'error');
                    await this.handleLogout();
                    return true;
                }
                return false;
            } catch (error) {
                return false;
            }
        },

        refreshCaptcha() {
            this.captchaUrl = '/api/captcha?t=' + Date.now();
            this.authForm.captcha = '';
        },

        loadRememberedCredentials() {
            try {
                const username = (typeof loadRememberedUser === 'function') ? loadRememberedUser() : '';
                if (username) {
                    this.authForm.username = username;
                    this.authForm.rememberPassword = true;
                }
            } catch (error) {
                console.error('加载记住的凭据失败:', error);
            }
        },

        resetAuthForm() {
            this.authForm = {
                username: this.authForm.username,
                password: '',
                confirmPassword: '',
                captcha: '',
                inviteCode: '',
                rememberPassword: this.authForm.rememberPassword
            };
            this.authError = '';
        },

        async handleLogin() {
            this.authError = '';

            if (!this.authForm.username) {
                this.authError = '请输入用户名';
                return;
            }
            if (!this.authForm.password) {
                this.authError = '请输入密码';
                return;
            }
            if (!this.authForm.captcha) {
                this.authError = '请输入验证码';
                return;
            }

            this.authLoading = true;
            try {
                const response = await apiFetch('/api/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: this.authForm.username,
                        password: this.authForm.password,
                        captcha: this.authForm.captcha
                    })
                });

                const data = await response.json();
                if (data.success) {
                    if (this.authForm.rememberPassword) {
                        if (typeof saveRememberedUser === 'function') {
                            saveRememberedUser(this.authForm.username);
                        }
                    } else {
                        if (typeof clearRememberedUser === 'function') {
                            clearRememberedUser();
                        }
                    }

                    this.isLoggedIn = true;
                    this.currentUser = data.username;
                    this.userRole = data.role || 'user';
                    this.showLoginModal = false;
                    this.showMaintenanceModal = (this.userRole === 'guest');
                    setLoggedInUsername(data.username);
                    this.startAuthManager();
                    this.showNotification('登录成功，欢迎 ' + data.username, 'success');
                    this.resetAuthForm();
                    await this.loadAvailableFiles();
                    await this.loadWrongBooks();
                } else {
                    this.authError = data.message;
                    this.refreshCaptcha();
                }
            } catch (error) {
                this.authError = '登录失败，请稍后重试';
                this.refreshCaptcha();
            } finally {
                this.authLoading = false;
            }
        },

        async handleRegister() {
            this.authError = '';

            if (!this.authForm.username) {
                this.authError = '请输入用户名';
                return;
            }
            if (this.authForm.username.length < 3 || this.authForm.username.length > 20) {
                this.authError = '用户名长度必须在3-20个字符之间';
                return;
            }
            if (!/^[a-zA-Z0-9]+$/.test(this.authForm.username)) {
                this.authError = '用户名只能包含字母和数字';
                return;
            }
            if (!this.authForm.password) {
                this.authError = '请输入密码';
                return;
            }
            if (this.authForm.password.length < 6) {
                this.authError = '密码长度不能少于6个字符';
                return;
            }
            if (this.authForm.password !== this.authForm.confirmPassword) {
                this.authError = '两次输入的密码不一致';
                return;
            }
            if (!this.authForm.captcha) {
                this.authError = '请输入验证码';
                return;
            }

            this.authLoading = true;
            try {
                const response = await apiFetch('/api/register', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: this.authForm.username,
                        password: this.authForm.password,
                        confirm_password: this.authForm.confirmPassword,
                        invite_code: this.authForm.inviteCode,
                        captcha: this.authForm.captcha
                    })
                });

                const data = await response.json();
                if (data.success) {
                    this.showNotification(data.message, 'success');
                    this.authMode = 'login';
                    this.resetAuthForm();
                    this.refreshCaptcha();
                } else {
                    this.authError = data.message;
                    this.showNotification(data.message, 'error');
                    this.refreshCaptcha();
                }
            } catch (error) {
                this.authError = '注册失败，请稍后重试';
                this.showNotification('注册失败，请稍后重试', 'error');
                this.refreshCaptcha();
            } finally {
                this.authLoading = false;
            }
        },

        async handleLogout() {
            if (this.authManager) {
                this.authManager.disconnect();
                this.authManager = null;
            }
            try {
                await apiFetch('/api/logout', { method: 'POST' });
                this.isLoggedIn = false;
                this.currentUser = null;
                this.userRole = 'user';
                setLoggedInUsername(null);
                this.showLoginModal = true;
                this.showMaintenanceModal = false;
                this.resetAuthForm();
                this.refreshCaptcha();
                this.step = 'load';
                this.showNotification('已退出登录', 'info');
            } catch (error) {
                console.error('退出登录失败:', error);
            }
        },

        startAuthManager() {
            if (this.authManager) {
                this.authManager.disconnect();
            }
            const self = this;
            this.authManager = new AuthManager({
                onSessionInvalidated: (data) => {
                    self.isLoggedIn = false;
                    self.currentUser = null;
                    self.userRole = 'user';
                    setLoggedInUsername(null);
                    self.showLoginModal = true;
                    self.showMaintenanceModal = true;
                    self.showNotification('会话已失效，请重新登录', 'error');
                    self.authManager = null;
                },
                onConnected: () => {
                    // SSE连接已建立
                },
                onDisconnected: () => {
                    // SSE连接已断开
                }
            });
            this.authManager.connect();
        },

        checkGuestAccess() {
            if (this.isLoggedIn && this.userRole === 'guest') {
                this.showMaintenanceModal = true;
            }
        },
    }
}).component('ToastNotification', ToastNotification)
  .component('ConfirmModal', ConfirmModal)
  .component('MaintenanceModal', MaintenanceModal)
  .component('LoginModal', LoginModal)
  .component('TopBar', TopBar)
  .component('ProgressBar', ProgressBar)
  .component('QuestionBankList', QuestionBankList)
  .component('QuestionExtractor', QuestionExtractor)
  .component('QuestionCard', QuestionCard)
  .component('QuestionOptions', QuestionOptions)
  .component('QuestionInput', QuestionInput)
  .component('CodePreview', CodePreview)
  .component('QuestionAnalysis', QuestionAnalysis)
  .component('WrongBookList', WrongBookList)
  .component('WrongBookItem', WrongBookItem)
  .component('AnswerSheet', AnswerSheet)
  .component('ResultPage', ResultPage)
  .mount('#app');
