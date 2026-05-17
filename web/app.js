const { createApp } = Vue;

function generateDeviceId() {
    /* 生成设备随机ID，存储在localStorage中以便持久化 */
    let deviceId = localStorage.getItem('deviceId');
    if (!deviceId) {
        deviceId = 'dev-' + Math.random().toString(36).substring(2, 10) + Date.now().toString(36);
        localStorage.setItem('deviceId', deviceId);
    }
    return deviceId;
}

const DEVICE_ID = generateDeviceId();
let CURRENT_USERNAME = null; // 全局用户名状态

function setLoggedInUsername(username) {
    /* 设置当前登录的用户名 */
    CURRENT_USERNAME = username;
}

function getAuthHeaders() {
    /* 获取带有用户身份信息的请求头 */
    let userIdentity;
    if (CURRENT_USERNAME) {
        userIdentity = CURRENT_USERNAME;
    } else {
        userIdentity = `unknown-${DEVICE_ID}`;
    }
    
    return {
        'X-User-Identity': userIdentity
    };
}

async function apiFetch(url, options = {}) {
    /* 统一的请求方法，自动添加用户身份信息 */
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

createApp({
    data() {
        return {
            step: 'load', // load, extract, answer, result
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
            correctAnswer: [], // 当前题目的正确答案
            isAnswerViewed: false,
            result: null,
            notification: null, // 悬浮提示
            confirmModal: { // 确认弹窗
                show: false,
                title: '',
                message: '',
                callback: () => {}
            },
            answerSheet: { // 答题卡
                show: false,
                questions: [], // 按题型分组的题目
                typeOrder: ['单选题', '多选题', '判断题', '填空题', '简答题', '释义题', '论述题', '编程题']
            },
            studyMode: false, // 背题模式
            autoShowAnswer: false, // 选择答案后自动显示答案
            shuffleOptions: false, // 选项乱序
            localQuestions: [], // 本地存储的题目数据
            localAnswers: {}, // 本地存储的用户答案
            localViewedAnswers: {}, // 本地存储的已查看答案状态
            isDarkMode: false, // 深色模式
            questionTransitionName: 'question-slide-next',
            questionRenderKey: 0,
            touchGesture: {
                startX: 0,
                startY: 0,
                deltaX: 0,
                deltaY: 0,
                active: false
            },
            // 登录/注册相关
            showLoginModal: true, // 显示登录弹窗
            authMode: 'login', // login 或 register
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
            showGuestAlert: false, // 游客提示弹窗
            userCheckTimer: null, // 用户验证定时器
            guestAlertShown: false, // 游客弹窗是否已显示过（单次会话）
            userCheckFailedCount: 0, // 用户验证失败次数
            userCheckAbortController: null, // 当前验证请求的AbortController
            // 错题本相关
            wrongBooks: [], // 用户的错题本列表
            showWrongBooks: false, // 是否展开错题本区域
            currentQuestionBankName: '' // 当前使用的题库名称
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
        },
        totalCorrect() {
            let correct = 0;
            for (let i = 0; i < this.localQuestions.length; i++) {
                const question = this.localQuestions[i];
                const user_answer = this.localAnswers[i] || [];
                const correct_answer = question.correct_answer;
                
                // 只有当用户已经作答时才进行统计
                const is_answered = user_answer.length > 0 && user_answer.some(ans => ans.trim() !== '');
                if (is_answered) {
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
                        correct++;
                    }
                }
            }
            return correct;
        },
        totalWrong() {
            let wrong = 0;
            for (let i = 0; i < this.localQuestions.length; i++) {
                const question = this.localQuestions[i];
                const user_answer = this.localAnswers[i] || [];
                const correct_answer = question.correct_answer;
                
                // 只有当用户已经作答时才进行统计
                const is_answered = user_answer.length > 0 && user_answer.some(ans => ans.trim() !== '');
                if (is_answered) {
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
                    
                    if (!is_correct) {
                        wrong++;
                    }
                }
            }
            return wrong;
        },
        canGoPrev() {
            return this.currentIndex > 0;
        },
        canGoNext() {
            return this.currentIndex < this.totalQuestions - 1;
        }
    },
    async created() {
        // 检查登录状态
        await this.checkLoginStatus();
        
        // 检测游客权限并显示维护弹窗
        this.checkGuestAccess();
        
        // 启动定时用户验证
        this.startUserCheck();
        
        // 加载可用的题库文件列表
        await this.loadAvailableFiles();
        
        // 如果已登录，加载错题本列表
        if (this.isLoggedIn) {
            await this.loadWrongBooks();
        }
        
        // 检查本地存储的深色模式偏好
        const savedDarkMode = localStorage.getItem('darkMode');
        if (savedDarkMode === 'true') {
            this.isDarkMode = true;
            document.body.classList.add('dark-mode');
        }
        
        // 注册全局键盘事件监听
        this._boundHandleKeyboard = this.handleKeyboard.bind(this);
        document.addEventListener('keydown', this._boundHandleKeyboard);
    },
    beforeDestroy() {
        // 清理定时器
        if (this.userCheckTimer) {
            clearInterval(this.userCheckTimer);
            this.userCheckTimer = null;
        }
        
        // 移除全局键盘事件监听
        if (this._boundHandleKeyboard) {
            document.removeEventListener('keydown', this._boundHandleKeyboard);
        }
    },
    methods: {
        selectFile(file) {
            /* 选择题库文件 */
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
            /* 显示悬浮提示 */
            this.notification = {
                message: message,
                type: type
            };
            
            // 3秒后自动隐藏
            setTimeout(() => {
                this.notification = null;
            }, 3000);
        },
        
        showConfirm(title, message, callback) {
            /* 显示确认弹窗 */
            this.confirmModal = {
                show: true,
                title: title,
                message: message,
                callback: (result) => {
                    this.confirmModal.show = false;
                    callback(result);
                }
            };
        },
        
        async loadAvailableFiles() {
            /* 加载可用的题库文件列表 */
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
            /* 加载用户的错题本列表 */
            if (!this.isLoggedIn) {
                return;
            }
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
            /* 切换错题本区域的展开/折叠状态 */
            this.showWrongBooks = !this.showWrongBooks;
            if (this.showWrongBooks && this.isLoggedIn) {
                this.loadWrongBooks();
            }
        },
        
        async loadWrongBookForPractice(fileName) {
            /* 加载错题本进行答题 */
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
        
        initUserAnswer() {
            /* 初始化当前题目的用户答案 */
            if (!this.currentQuestion) return;
            const type = this.currentQuestion.type;
            if (['单选题', '多选题', '判断题', '选择题'].includes(type)) {
                this.userAnswer = [];
            } else if (['填空题', '简答题', '释义题', '论述题', '编程题'].includes(type)) {
                const count = this.currentQuestion.correct_answer ? this.currentQuestion.correct_answer.length : 1;
                this.userAnswer = new Array(count).fill('');
            } else {
                this.userAnswer = [];
            }
            this.isAnswerViewed = false;
            this.correctAnswer = [];
        },
        
        async deleteWrongBook(fileName, bookTitle) {
            /* 删除错题本 */
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
                            // 刷新错题本列表
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
            /* 加载题库 */
            this.error = '';
            try {
                const response = await apiFetch('/api/load_questions', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
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
                    // 初始化题型数量为最大值
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
            /* 抽取题目 */
            this.error = '';
            try {
                // 验证输入
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
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        total_count: this.totalSelectedQuestions,
                        type_ratios: filteredCounts
                    })
                });
                
                const data = await response.json();
                if (data.success) {
                    let questions = data.questions; // 保存题目数据到本地

                    // 如果启用了选项乱序，对每个题目的选项进行打乱
                    if (this.shuffleOptions) {
                        questions = questions.map(q => this.shuffleQuestionOptions(q));
                    }

                    this.totalQuestions = data.questions_count;
                    this.localQuestions = questions;
                    this.localAnswers = {}; // 初始化本地答案存储
                    this.localViewedAnswers = {}; // 初始化本地已查看答案状态
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
        
        loadCurrentQuestion() {
            /* 从本地加载当前题目 */
            this.error = '';
            try {
                if (this.currentIndex >= 0 && this.currentIndex < this.localQuestions.length) {
                    this.currentQuestion = this.localQuestions[this.currentIndex];
                    this.userAnswer = this.localAnswers[this.currentIndex] || [];
                    this.isAnswerViewed = this.localViewedAnswers[this.currentIndex] || false;
                    
                    // 对于填空题/简答题/论述题/编程题，根据正确答案数量初始化答案数组
                    if (['填空题', '简答题', '释义题', '论述题', '编程题'].includes(this.currentQuestion.type)) {
                        const correctAnswerCount = this.currentQuestion.correct_answer ? this.currentQuestion.correct_answer.length : 1;
                        if (this.userAnswer.length === 0) {
                            // 如果没有答案，根据正确答案数量初始化空数组
                            this.userAnswer = Array(correctAnswerCount).fill('');
                        } else if (this.userAnswer.length < correctAnswerCount) {
                            // 如果答案数量少于正确答案数量，补充空答案
                            while (this.userAnswer.length < correctAnswerCount) {
                                this.userAnswer.push('');
                            }
                        }
                    }
                    // 对于单选题和判断题，如果没有答案，初始化空数组
                    if (['单选题', '判断题'].includes(this.currentQuestion.type) && this.userAnswer.length === 0) {
                        this.userAnswer = [''];
                    }
                    
                    // 如果已经查看过答案，获取正确答案
                    if (this.isAnswerViewed) {
                        this.correctAnswer = this.currentQuestion.correct_answer;
                    } else {
                        // 否则清空正确答案
                        this.correctAnswer = [];
                    }
                    
                    // 如果是背题模式，自动显示答案
                    if (this.studyMode && !this.isAnswerViewed) {
                        this.viewAnswer();
                    }
                } else {
                    this.error = '题目索引无效';
                }
            } catch (error) {
                this.error = `加载题目失败: ${error.message}`;
            }
        },
        
        async fetchCorrectAnswer() {
            /* 获取正确答案 */
            try {
                const response = await apiFetch(`/api/questions/${this.currentIndex}/view_answer`, {
                    method: 'POST'
                });
                
                const data = await response.json();
                if (data.success) {
                    this.correctAnswer = data.correct_answer;
                    // 只更新答案解析，不刷新整个题目
                    this.currentQuestion.analysis = data.analysis;
                }
            } catch (error) {
                console.error(`获取正确答案失败: ${error.message}`);
            }
        },
        

        
        viewAnswer() {
            /* 在本地查看答案 */
            this.error = '';
            try {
                if (this.currentIndex >= 0 && this.currentIndex < this.localQuestions.length) {
                    this.isAnswerViewed = true;
                    this.localViewedAnswers[this.currentIndex] = true; // 更新本地已查看答案状态
                    this.correctAnswer = this.currentQuestion.correct_answer; // 从本地题目中获取正确答案
                    this.showNotification('答案已显示', 'info');
                } else {
                    this.error = '题目索引无效';
                }
            } catch (error) {
                this.error = `查看答案失败: ${error.message}`;
            }
        },
        
        prevQuestion() {
            this.navigateToQuestion(this.currentIndex - 1, 'prev');
        },
        
        nextQuestion() {
            this.navigateToQuestion(this.currentIndex + 1, 'next');
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
            /* 在本地计算考试结果 */
            this.error = '';
            try {
                const total_questions = this.localQuestions.length;
                let correct_count = 0;
                const wrong_questions = [];
                
                for (let i = 0; i < total_questions; i++) {
                    const question = this.localQuestions[i];
                    const user_answer = this.localAnswers[i] || [];
                    const correct_answer = question.correct_answer;
                    
                    // 根据题型检查答案是否正确
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
                        // 收集错题信息
                        wrong_questions.push({
                            id: i + 1, // 错题序号
                            type: question.type,
                            content: question.content,
                            options: question.options || [],
                            user_answer: user_answer,
                            correct_answer: correct_answer,
                            analysis: question.analysis || ''
                        });
                    }
                }
                
                // 计算得分（满分100）
                const score = total_questions > 0 ? Math.round((correct_count / total_questions) * 100 * 10) / 10 : 0;
                
                this.result = {
                    success: true,
                    score: score,
                    correct_count: correct_count,
                    total_questions: total_questions,
                    wrong_questions: wrong_questions
                };
                
                this.step = 'result';
            } catch (error) {
                this.error = `提交失败: ${error.message}`;
            }
        },
        
        formatAnswer(answer) {
            /* 格式化答案显示 */
            if (Array.isArray(answer)) {
                return answer.join(', ');
            }
            return answer;
        },
        
        restart() {
            this.step = 'load';
            this.stats = null;
            this.error = '';
            this.result = null;
            this.availableTypes = [];
            this.typeCounts = {};
            this.loadAvailableFiles(); // 重新加载可用文件列表
        },
        

        
        // 答题卡相关方法
        loadAnswerSheet() {
            /* 从本地加载答题卡数据 */
            try {
                // 从本地题目数据中获取所有题目的基本信息
                const questions = [];
                for (let i = 0; i < this.localQuestions.length; i++) {
                    const question = this.localQuestions[i];
                    const userAnswer = this.localAnswers[i] || [];
                    const isViewed = this.localViewedAnswers[i] || false;
                    
                    questions.push({
                        index: i,
                        type: question.type,
                        is_answered: userAnswer.length > 0,
                        is_viewed: isViewed
                    });
                }
                
                // 按题型分组
                this.answerSheet.questions = [];
                let currentNumber = 1;
                
                this.answerSheet.typeOrder.forEach(type => {
                    const typeQuestions = questions.filter(q => q.type === type);
                    if (typeQuestions.length > 0) {
                        this.answerSheet.questions.push({
                            type: type,
                            questions: typeQuestions.map(q => ({
                                ...q,
                                displayNumber: currentNumber++
                            }))
                        });
                    }
                });
            } catch (error) {
                console.error(`加载答题卡失败: ${error.message}`);
                this.showNotification('加载答题卡失败', 'error');
            }
        },
        
        toggleAnswerSheet() {
            /* 显示/隐藏答题卡 */
            if (this.answerSheet.show) {
                this.answerSheet.show = false;
            } else {
                this.loadAnswerSheet();
                this.answerSheet.show = true;
            }
        },
        
        jumpToQuestion(index) {
            /* 跳转到指定题目 */
            this.answerSheet.show = false;
            const direction = index >= this.currentIndex ? 'next' : 'prev';
            this.navigateToQuestion(index, direction);
        },

        navigateToQuestion(targetIndex, direction = 'next') {
            /* 统一处理切题入口，复用按钮/答题卡/滑动动画 */
            if (targetIndex < 0 || targetIndex >= this.totalQuestions || targetIndex === this.currentIndex) {
                return;
            }

            this.questionTransitionName = direction === 'prev'
                ? 'question-slide-prev'
                : 'question-slide-next';
            this.currentIndex = targetIndex;
            this.questionRenderKey++;
            this.loadCurrentQuestion();
        },

        onQuestionTouchStart(event) {
            if (!event.touches || event.touches.length !== 1) {
                return;
            }

            const interactiveTarget = event.target.closest('input, textarea, button, label');
            const codePreviewTarget = event.target.closest('.code-preview, .code-container, .code-content, .line-numbers');
            if (interactiveTarget) {
                this.touchGesture.active = false;
                return;
            }
            if (codePreviewTarget) {
                this.touchGesture.active = false;
                return;
            }

            const touch = event.touches[0];
            this.touchGesture = {
                startX: touch.clientX,
                startY: touch.clientY,
                deltaX: 0,
                deltaY: 0,
                active: true
            };
        },

        onQuestionTouchMove(event) {
            if (!this.touchGesture.active || !event.touches || event.touches.length !== 1) {
                return;
            }

            const touch = event.touches[0];
            this.touchGesture.deltaX = touch.clientX - this.touchGesture.startX;
            this.touchGesture.deltaY = touch.clientY - this.touchGesture.startY;
        },

        onQuestionTouchEnd() {
            if (!this.touchGesture.active) {
                return;
            }

            const { deltaX, deltaY } = this.touchGesture;
            const absX = Math.abs(deltaX);
            const absY = Math.abs(deltaY);
            const minSwipeDistance = 70;

            this.touchGesture.active = false;

            if (absX < minSwipeDistance || absX <= absY) {
                return;
            }

            if (deltaX < 0) {
                this.nextQuestion();
            } else {
                this.prevQuestion();
            }
        },

        onQuestionTouchCancel() {
            this.touchGesture.active = false;
        },

        getCardClasses(question) {
            /* 获取题目卡片 CSS 类名 */
            const classes = [];
            if (question.is_answered) classes.push('answered');
            if (question.is_viewed) classes.push('viewed');
            // 当前题目高亮
            if (question.index === this.currentIndex) classes.push('current');
            return classes;
        },
        
        getOptionLetter(index) {
            /* 将选项索引转换为字母 (0=A, 1=B, 2=C, ...) */
            return String.fromCharCode(65 + index); // 65 是 'A' 的 ASCII 码
        },

        shuffleArray(array) {
            /* Fisher-Yates 洗牌算法，用于打乱数组 */
            for (let i = array.length - 1; i > 0; i--) {
                const j = Math.floor(Math.random() * (i + 1));
                [array[i], array[j]] = [array[j], array[i]];
            }
            return array;
        },

        shuffleQuestionOptions(question) {
            /* 对题目的选项进行打乱，并同步更新正确答案 */
            if (!question.options || question.options.length <= 1) {
                return question;
            }

            // 创建选项和原始索引的映射
            const optionsWithIndex = question.options.map((opt, idx) => ({
                text: opt,
                originalIndex: idx,
                letter: String.fromCharCode(65 + idx) // A, B, C, D...
            }));

            // 打乱选项
            const shuffledOptions = this.shuffleArray([...optionsWithIndex]);

            // 创建原始字母到新字母的映射
            const letterMap = {};
            shuffledOptions.forEach((opt, newIdx) => {
                letterMap[opt.letter] = String.fromCharCode(65 + newIdx);
            });

            // 更新正确答案中的字母
            const newCorrectAnswer = question.correct_answer.map(ans => {
                // 如果答案是大写字母（A, B, C, D...），进行映射转换
                if (/^[A-Z]$/.test(ans)) {
                    return letterMap[ans] || ans;
                }
                // 对于判断题，答案可能是"正确"/"错误"文本，保持不变
                return ans;
            });

            return {
                ...question,
                options: shuffledOptions.map(opt => opt.text),
                correct_answer: newCorrectAnswer
            };
        },

        selectOption(value, index) {
            /* 单选按钮选择并自动保存 */
            if (!this.isAnswerViewed && !this.studyMode) {
                this.userAnswer[0] = value;
                this._saveCurrentAnswer();

                // 如果开启了自动显示答案，选择后自动查看答案
                if (this.autoShowAnswer && !this.isAnswerViewed) {
                    this.viewAnswer();
                }
            }
        },
        
        submitAnswer() {
            /* 提交答案并显示答案（用于多选题、填空题等非单选题型） */
            this.error = '';
            try {
                if (this.currentIndex >= 0 && this.currentIndex < this.localQuestions.length) {
                    // 检查用户是否已作答
                    const hasAnswer = this.userAnswer.length > 0 && 
                                     this.userAnswer.some(ans => ans && ans.trim() !== '');
                    
                    if (!hasAnswer) {
                        this.showNotification('请先作答再提交', 'warning');
                        return;
                    }
                    
                    // 显示答案
                    this.viewAnswer();
                } else {
                    this.error = '题目索引无效';
                }
            } catch (error) {
                this.error = `提交答案失败: ${error.message}`;
            }
        },
        
        handleMultipleAnswerChange() {
            /* 多选题由 checkbox v-model 驱动，变更后统一保存 */
            if (!this.isAnswerViewed && !this.studyMode) {
                this._saveCurrentAnswer();
            }
        },
        
        _saveCurrentAnswer() {
            /* 自动保存当前答案到本地 */
            try {
                this.localAnswers[this.currentIndex] = [...this.userAnswer];
            } catch (error) {
                console.error(`自动保存答案失败: ${error.message}`);
            }
        },
        
        autoSaveAnswer() {
            /* 处理填空题/简答题/论述题/编程题的自动保存 */
            if (!this.studyMode) {
                this._saveCurrentAnswer();
            }
        },
        
        async generateWrongQuestionsBook() {
            /* 生成错题本：将完整错题数据发送到后端生成错题集 */
            if (!this.result || !this.result.wrong_questions || this.result.wrong_questions.length === 0) {
                this.showNotification('没有错题可以生成错题本', 'info');
                return;
            }
            
            try {
                // 直接发送完整的错题数据到后端
                const wrongQuestionData = {
                    wrong_questions: this.result.wrong_questions,
                    original_name: this.currentQuestionBankName || '错题本'
                };
                
                // 发送请求到后端，生成错题集
                const response = await apiFetch('/api/generate_wrong_book', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(wrongQuestionData)
                });
                
                const data = await response.json();
                if (data.success) {
                    this.showNotification('错题本已成功生成并保存', 'success');
                    // 重新加载错题本列表
                    await this.loadWrongBooks();
                } else {
                    this.showNotification(`生成错题本失败: ${data.message}`, 'error');
                }
            } catch (error) {
                console.error(`生成错题本失败: ${error.message}`);
                this.showNotification('生成错题本失败', 'error');
            }
        },
        
        // 代码高亮相关方法
         normalizeCode(code) {
             /* 标准化代码：将中文全角括号转换为标准尖括号 */
             if (!code) return '';
             return code.replace(/《/g, '<').replace(/》/g, '>');
         },
         
         highlightCode(code, language = 'javascript') {
             /* 使用 TextMate 规则进行语法高亮 */
             if (!code) return '';
             
             // 先标准化代码
             code = this.normalizeCode(code);
             
             // 使用 SyntaxHighlighter 进行高亮（同步版本）
             return SyntaxHighlighter.highlightSimple(code, language);
         },
        
        detectLanguage(content) {
            /* 检测代码语言 */
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
            /* 获取语言图标 */
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
            /* 复制代码到剪贴板 */
            // 先标准化代码
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
            /* 降级复制方法 */
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
            /* 将Markdown文本渲染为HTML */
            if (!text) return '';
            // 先转义HTML标签，防止<details>、<summary>等被解析为DOM元素
            // 但保留代码块中的HTML标签
            const escapedText = this.escapeHtmlTagsInMarkdown(text);
            // 使用marked.js进行Markdown渲染
            return marked.parse(escapedText);
        },

        escapeHtmlTagsInMarkdown(text) {
            /* 转义Markdown中的HTML标签，但保留代码块内的内容 */
            // 分割代码块和普通文本
            const parts = [];
            const codeBlockRegex = /(```[\s\S]*?```|`[^`]*`)/g;
            let lastIndex = 0;
            let match;

            while ((match = codeBlockRegex.exec(text)) !== null) {
                // 添加代码块前的普通文本
                if (match.index > lastIndex) {
                    parts.push({
                        type: 'text',
                        content: text.substring(lastIndex, match.index)
                    });
                }
                // 添加代码块
                parts.push({
                    type: 'code',
                    content: match[0]
                });
                lastIndex = match.index + match[0].length;
            }

            // 添加剩余文本
            if (lastIndex < text.length) {
                parts.push({
                    type: 'text',
                    content: text.substring(lastIndex)
                });
            }

            // 处理每个部分
            return parts.map(part => {
                if (part.type === 'code') {
                    // 代码块保持原样
                    return part.content;
                } else {
                    // 普通文本中，将 <tag> 格式转换为 &lt;tag&gt;
                    // 匹配类似 <collection>、<if>、<details> 等标签格式
                    return part.content.replace(/<([a-zA-Z][a-zA-Z0-9-]*)>/g, '&lt;$1&gt;')
                                       .replace(/<\/([a-zA-Z][a-zA-Z0-9-]*)>/g, '&lt;/$1&gt;');
                }
            }).join('');
        },

        // ==================== 登录/注册相关方法 ====================

        async checkLoginStatus() {
            /* 检查登录状态 */
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
                } else {
                    this.isLoggedIn = false;
                    this.currentUser = null;
                    this.userRole = 'user';
                    this.showLoginModal = true;
                    this.showMaintenanceModal = false;
                    setLoggedInUsername(null);
                    this.refreshCaptcha();
                    // 加载记住的用户名和密码
                    this.loadRememberedCredentials();
                }
            } catch (error) {
                console.error('检查登录状态失败:', error);
                this.showLoginModal = true;
                this.showMaintenanceModal = false;
                this.refreshCaptcha();
                // 加载记住的用户名和密码
                this.loadRememberedCredentials();
            }
        },
        async checkBannedStatus() {
            /* 检查当前用户是否被封禁 */
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
            /* 刷新验证码 */
            this.captchaUrl = '/api/captcha?t=' + Date.now();
            this.authForm.captcha = '';
        },

        loadRememberedCredentials() {
            /* 加载记住的用户名和密码 */
            try {
                const remembered = localStorage.getItem('rememberedUser');
                if (remembered) {
                    const user = JSON.parse(remembered);
                    this.authForm.username = user.username || '';
                    this.authForm.password = user.password || '';
                    this.authForm.rememberPassword = true;
                }
            } catch (error) {
                console.error('加载记住的凭据失败:', error);
            }
        },

        resetAuthForm() {
            /* 重置登录/注册表单 */
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
            /* 处理登录 */
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
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        username: this.authForm.username,
                        password: this.authForm.password,
                        captcha: this.authForm.captcha
                    })
                });

                const data = await response.json();
                if (data.success) {
                    // 保存或清除记住的密码
                    if (this.authForm.rememberPassword) {
                        localStorage.setItem('rememberedUser', JSON.stringify({
                            username: this.authForm.username,
                            password: this.authForm.password
                        }));
                    } else {
                        localStorage.removeItem('rememberedUser');
                    }

                    this.isLoggedIn = true;
                    this.currentUser = data.username;
                    this.userRole = data.role || 'user';
                    this.showLoginModal = false;
                    this.showMaintenanceModal = (this.userRole === 'guest');
                    setLoggedInUsername(data.username);
                    this.showNotification('登录成功，欢迎 ' + data.username, 'success');
                    this.resetAuthForm();
                    // 重新加载题库文件列表
                    await this.loadAvailableFiles();
                    // 加载错题本列表
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
            /* 处理注册 */
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
            if (!this.authForm.inviteCode) {
                this.authError = '请输入邀请码';
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
                    headers: {
                        'Content-Type': 'application/json'
                    },
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
                    // 注册成功后切换到登录模式
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
            /* 处理登出 */
            // 清理定时器
            if (this.userCheckTimer) {
                clearInterval(this.userCheckTimer);
                this.userCheckTimer = null;
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
                // 登出时不清除记住的密码，保留用户的勾选状态
            } catch (error) {
                console.error('退出登录失败:', error);
            }
        },

        checkGuestAccess() {
            /* 检测游客权限并显示维护弹窗 */
            if (this.isLoggedIn && this.userRole === 'guest') {
                this.showMaintenanceModal = true;
            }
        },

        startUserCheck() {
            /* 启动定时用户验证 */
            if (this.userCheckTimer) {
                clearInterval(this.userCheckTimer);
            }
            
            // 每分钟（60000毫秒）验证一次用户状态
            this.userCheckTimer = setInterval(async () => {
                if (!this.isLoggedIn) {
                    return;
                }
                
                await this.verifyUserStatus();
            }, 60000);
        },

        async verifyUserStatus() {
            /* 验证用户状态（带30秒超时和重试机制） */
            try {
                // 如果已有验证请求在进行，先取消
                if (this.userCheckAbortController) {
                    this.userCheckAbortController.abort();
                }
                
                // 创建新的AbortController
                this.userCheckAbortController = new AbortController();
                const signal = this.userCheckAbortController.signal;
                
                // 设置30秒超时
                const timeoutId = setTimeout(() => {
                    this.userCheckAbortController.abort();
                }, 30000);
                
                const response = await apiFetch('/api/verify_user', { signal });
                
                // 清除超时定时器
                clearTimeout(timeoutId);
                this.userCheckAbortController = null;
                
                // 重置失败计数（成功响应）
                this.userCheckFailedCount = 0;
                
                // 如果返回401，说明会话失效
                if (response.status === 401) {
                    this.isLoggedIn = false;
                    this.currentUser = null;
                    this.userRole = 'user';
                    setLoggedInUsername(null);
                    this.showLoginModal = true;
                    this.showMaintenanceModal = true;
                    this.showNotification('登录已过期，请重新登录', 'error');
                    return;
                }
                
                const data = await response.json();
                
                if (data.success) {
                    if (!data.valid) {
                        // 用户不合法，清除会话
                        this.isLoggedIn = false;
                        this.currentUser = null;
                        this.userRole = 'user';
                        setLoggedInUsername(null);
                        this.showLoginModal = true;
                        this.showMaintenanceModal = true;
                        this.showNotification(data.message, 'error');
                    } else if (data.role === 'guest') {
                        // 游客身份，立即弹出提示
                        this.userRole = 'guest';
                        this.showGuestAlert = true;
                        this.showNotification('当前用户为游客账号', 'warning');
                    } else {
                        // 用户有效且不是游客
                        this.userRole = data.role;
                        this.showNotification(data.message, 'success');
                    }
                }
            } catch (error) {
                // 如果是主动取消的请求（新的验证请求开始了），不处理
                if (error.name === 'AbortError') {
                    return;
                }
                
                console.error('验证用户状态失败:', error);
                
                // 增加失败计数
                this.userCheckFailedCount++;
                
                // 如果第一次请求超时（失败计数为1），立即重试
                if (this.userCheckFailedCount === 1) {
                    console.log('用户验证超时，正在重试...');
                    // 短暂延迟后立即重试
                    setTimeout(() => {
                        this.verifyUserStatus();
                    }, 1000);
                } 
                // 如果第二次也超时（失败计数为2），弹出错误弹窗
                else if (this.userCheckFailedCount >= 2) {
                    this.userCheckFailedCount = 0;
                    this.isLoggedIn = false;
                    this.currentUser = null;
                    this.userRole = 'user';
                    this.showLoginModal = true;
                    this.showMaintenanceModal = true;
                    this.showNotification('用户验证超时，请检查网络连接', 'error');
                }
            }
        },

        handleKeyboard(event) {
            /* 处理全局键盘事件 */
            // 只有在答题页面才响应
            if (this.step !== 'answer') {
                return;
            }

            // 检查焦点是否在输入框、文本域、登录弹窗输入框等交互元素中
            const activeElement = document.activeElement;
            if (activeElement && (
                activeElement.tagName === 'INPUT' || 
                activeElement.tagName === 'TEXTAREA' || 
                activeElement.tagName === 'SELECT' ||
                activeElement.isContentEditable ||
                activeElement.closest('.modal') || // 在弹窗内不响应
                activeElement.closest('.answer-sheet-content') // 在答题卡内不响应
            )) {
                return;
            }

            const key = event.key;

            // 左右方向键切换题目
            if (key === 'ArrowLeft') {
                event.preventDefault();
                if (this.canGoPrev) {
                    this.prevQuestion();
                }
            } else if (key === 'ArrowRight') {
                event.preventDefault();
                if (this.canGoNext) {
                    this.nextQuestion();
                }
            }
            // 数字键映射到选项
            else if (/^[1-9]$/.test(key)) {
                event.preventDefault();
                const optionIndex = parseInt(key) - 1; // 1->A, 2->B, 3->C...
                this.selectOptionByKey(optionIndex);
            }
        },

        selectOptionByKey(optionIndex) {
            /* 通过数字键选择选项 */
            if (!this.currentQuestion || this.isAnswerViewed || this.studyMode) {
                return;
            }

            // 判断题：1->正确, 2->错误（如果存在对应选项）
            if (this.currentQuestion.type === '判断题') {
                if (optionIndex < this.currentQuestion.options.length) {
                    this.selectOption(this.currentQuestion.options[optionIndex], optionIndex);
                }
                return;
            }

            // 单选题、多选题：数字映射到选项字母
            if (['单选题', '多选题'].includes(this.currentQuestion.type)) {
                if (optionIndex < this.currentQuestion.options.length) {
                    const optionLetter = this.getOptionLetter(optionIndex);
                    if (this.currentQuestion.type === '单选题') {
                        this.selectOption(optionLetter, optionIndex);
                    } else {
                        // 多选题：切换选项的选中状态
                        const answerIndex = this.userAnswer.indexOf(optionLetter);
                        if (answerIndex === -1) {
                            this.userAnswer.push(optionLetter);
                        } else {
                            this.userAnswer.splice(answerIndex, 1);
                        }
                        this.handleMultipleAnswerChange();
                    }
                }
            }
        },
        
        getQuestionImageUrl(imagePath) {
            /* 获取题目图片的URL */
            if (!imagePath) return '';
            
            // 如果已经是完整URL，直接返回
            if (imagePath.startsWith('http://') || imagePath.startsWith('https://') || imagePath.startsWith('data:')) {
                return imagePath;
            }
            
            // 构建相对于paper_json/images目录的URL
            // 支持相对路径和绝对路径
            let normalizedPath = imagePath.replace(/\\/g, '/');
            if (normalizedPath.startsWith('/')) {
                normalizedPath = normalizedPath.substring(1);
            }
            
            return `/api/question_image/${normalizedPath}`;
        },
        
        handleImageError(event) {
            /* 处理图片加载失败 */
            console.warn('题目图片加载失败:', event.target.src);
            // 隐藏图片容器
            const container = event.target.closest('.question-image-container');
            if (container) {
                container.style.display = 'none';
            }
        },
        
        handleImageLoad(event) {
            /* 处理图片加载成功 */
            const container = event.target.closest('.question-image-container');
            if (container) {
                container.style.display = 'flex';
            }
        },
    }
}).mount('#app');
