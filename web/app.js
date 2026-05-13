const { createApp } = Vue;

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
            isDarkMode: false // 深色模式
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
        }
    },
    async created() {
        // 加载可用的题库文件列表
        await this.loadAvailableFiles();
        
        // 检查本地存储的深色模式偏好
        const savedDarkMode = localStorage.getItem('darkMode');
        if (savedDarkMode === 'true') {
            this.isDarkMode = true;
            document.body.classList.add('dark-mode');
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
                const response = await fetch('/api/available_files');
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
        
        async loadQuestions() {
            /* 加载题库 */
            this.error = '';
            try {
                const response = await fetch('/api/load_questions', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ file_path: this.filePath })
                });
                
                const data = await response.json();
                if (data.success) {
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
                
                const response = await fetch('/api/extract_questions', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        total_count: this.totalSelectedQuestions,
                        type_ratios: filteredCounts // 这里使用type_ratios参数名保持兼容
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
                const response = await fetch(`/api/questions/${this.currentIndex}/view_answer`, {
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
            if (this.currentIndex > 0) {
                this.currentIndex--;
                this.loadCurrentQuestion();
            }
        },
        
        nextQuestion() {
            if (this.currentIndex < this.totalQuestions - 1) {
                this.currentIndex++;
                this.loadCurrentQuestion();
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
            this.currentIndex = index;
            this.loadCurrentQuestion();
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
        
        selectMultipleOption(value, optionIndex) {
            /* 多选按钮选择并自动保存 */
            if (!this.isAnswerViewed && !this.studyMode) {
                const index = this.userAnswer.indexOf(value);
                if (index === -1) {
                    this.userAnswer.push(value);
                } else {
                    this.userAnswer.splice(index, 1);
                }
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
            /* 生成错题本：将错题序号和作答内容发送到后端，由后端根据完整题库反推错题集 */
            if (!this.result || !this.result.wrong_questions || this.result.wrong_questions.length === 0) {
                this.showNotification('没有错题可以生成错题本', 'info');
                return;
            }
            
            try {
                // 收集错题序号和对应作答内容
                const wrongQuestionData = {
                    wrong_indices: this.result.wrong_questions.map(q => q.id), // 错题序号
                    user_answers: {} // 对应作答内容
                };
                
                // 填充用户作答内容
                this.result.wrong_questions.forEach(q => {
                    wrongQuestionData.user_answers[q.id] = q.user_answer;
                });
                
                // 发送请求到后端，生成错题集
                const response = await fetch('/api/generate_wrong_book', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(wrongQuestionData)
                });
                
                const data = await response.json();
                if (data.success) {
                    this.showNotification('错题本已成功生成并保存', 'success');
                } else {
                    this.showNotification(`生成错题本失败: ${data.message}`, 'error');
                }
            } catch (error) {
                console.error(`生成错题本失败: ${error.message}`);
                this.showNotification('生成错题本失败', 'error');
            }
        }
    }
}).mount('#app');