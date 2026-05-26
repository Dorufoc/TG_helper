/**
 * 答案处理混入模块 (answer-mixin)
 * 
 * 提供答案初始化、保存、选择、提交和格式化等功能。
 * 
 * 需要的 data 属性（宿主 Vue 实例必须提供）：
 *   - currentQuestion {Object|null} - 当前题目对象
 *   - userAnswer {Array} - 当前题目的用户答案
 *   - isAnswerViewed {Boolean} - 是否已查看答案
 *   - correctAnswer {Array} - 当前题目的正确答案
 *   - localQuestions {Array} - 本地存储的所有题目
 *   - localAnswers {Object} - 本地存储的用户答案，以索引为键
 *   - currentIndex {Number} - 当前题目索引
 *   - autoShowAnswer {Boolean} - 是否选择后自动查看答案
 *   - studyMode {Boolean} - 是否为背题模式
 * 
 * 使用方式：
 *   Vue.createApp({
 *     mixins: [answerMixin],
 *     // ...
 *   })
 */

const answerMixin = {
    computed: {
        /**
         * 计算累计正确题数
         * 遍历所有已作答的题目，比对用户答案与正确答案
         * @returns {Number} 正确题数
         */
        totalCorrect() {
            let correct = 0;
            for (let i = 0; i < this.localQuestions.length; i++) {
                const question = this.localQuestions[i];
                const user_answer = this.localAnswers[i] || [];
                const correct_answer = question.correct_answer;
                
                // 只有当用户已经作答时才进行统计
                const is_answered = user_answer.length > 0 && user_answer.some(ans => ans && ans.trim() !== '');
                if (is_answered) {
                    let is_correct = false;
                    if (['单选题', '判断题', '多选题', '选择题'].includes(question.type)) {
                        is_correct = JSON.stringify(user_answer.sort()) === JSON.stringify(correct_answer.sort());
                    } else if (['填空题', '简答题', '释义题', '论述题', '编程题'].includes(question.type)) {
                        if (user_answer.length === correct_answer.length) {
                            let is_all_correct = true;
                            for (let j = 0; j < user_answer.length; j++) {
                                if (user_answer[j] && correct_answer[j] && user_answer[j].trim() !== correct_answer[j].trim()) {
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

        /**
         * 计算累计错误题数
         * 遍历所有已作答的题目，统计答案错误的题数
         * @returns {Number} 错误题数
         */
        totalWrong() {
            let wrong = 0;
            for (let i = 0; i < this.localQuestions.length; i++) {
                const question = this.localQuestions[i];
                const user_answer = this.localAnswers[i] || [];
                const correct_answer = question.correct_answer;

                // 只有当用户已经作答时才进行统计
                const is_answered = user_answer.length > 0 && user_answer.some(ans => ans && ans.trim() !== '');
                if (is_answered) {
                    let is_correct = false;
                    if (['单选题', '判断题', '多选题', '选择题'].includes(question.type)) {
                        is_correct = JSON.stringify(user_answer.sort()) === JSON.stringify(correct_answer.sort());
                    } else if (['填空题', '简答题', '释义题', '论述题', '编程题'].includes(question.type)) {
                        if (user_answer.length === correct_answer.length) {
                            let is_all_correct = true;
                            for (let j = 0; j < user_answer.length; j++) {
                                if (user_answer[j] && correct_answer[j] && user_answer[j].trim() !== correct_answer[j].trim()) {
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

    methods: {
        /**
         * 初始化当前题目的用户答案数组（根据题型）
         * 
         * 对于选择题类型（单选/多选/判断），初始化为空数组。
         * 对于填空/简答/释义/论述/编程题，根据正确答案数量初始化对应长度的空字符串数组。
         */
        initUserAnswer() {
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

        /**
         * 保存当前答案到本地存储
         * 将 userAnswer 数组的副本保存到 localAnswers 对应当前索引的位置
         * @private
         */
        _saveCurrentAnswer() {
            try {
                this.localAnswers[this.currentIndex] = [...this.userAnswer];
            } catch (error) {
                console.error(`自动保存答案失败: ${error.message}`);
            }
        },

        /**
         * 自动保存答案（用于填空题等输入事件）
         * 在非背题模式下调用 _saveCurrentAnswer 保存答案
         */
        autoSaveAnswer() {
            if (!this.studyMode) {
                this._saveCurrentAnswer();
            }
        },

        /**
         * 选择选项并保存
         * 用于单选按钮点击等选择操作，选择后自动保存答案
         * 如果开启了自动显示答案，选择后自动查看答案
         * 
         * @param {String} value - 选项值（如 'A', 'B', '正确' 等）
         * @param {Number} index - 选项索引
         */
        selectOption(value, index) {
            if (!this.isAnswerViewed && !this.studyMode) {
                this.userAnswer[0] = value;
                this._saveCurrentAnswer();

                // 如果开启了自动显示答案，选择后自动查看答案
                if (this.autoShowAnswer && !this.isAnswerViewed) {
                    this.viewAnswer();
                }
            }
        },

        /**
         * 提交答案并显示答案
         * 用于多选题、填空题等非单选题型，提交后查看答案
         * 会检查用户是否已作答，未作答则提示
         */
        submitAnswer() {
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

        /**
         * 处理多选题答案变化
         * 由 checkbox v-model 驱动，变更后统一保存答案
         */
        handleMultipleAnswerChange() {
            if (!this.isAnswerViewed && !this.studyMode) {
                this._saveCurrentAnswer();
            }
        },

        /**
         * 将索引转换为字母 (0=A, 1=B, 2=C, ...)
         * 
         * @param {Number} index - 选项索引（从 0 开始）
         * @returns {String} 对应的大写字母
         */
        getOptionLetter(index) {
            return String.fromCharCode(65 + index); // 65 是 'A' 的 ASCII 码
        },

        /**
         * 格式化答案显示
         * 将答案数组转换为逗号分隔的字符串，非数组则直接返回
         * 
         * @param {Array|String} answer - 答案（数组或字符串）
         * @returns {String} 格式化后的答案字符串
         */
        formatAnswer(answer) {
            if (Array.isArray(answer)) {
                return answer.join(', ');
            }
            return answer;
        },

        /**
         * 打乱题目选项并映射正确答案
         * 对题目的 options 数组进行 Fisher-Yates 洗牌，并同步更新正确答案中的字母映射
         * 
         * @param {Object} question - 题目对象，包含 options 和 correct_answer
         * @returns {Object} 打乱后的新题目对象
         */
        shuffleQuestionOptions(question) {
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

        /**
         * Fisher-Yates 洗牌算法
         * 原地打乱数组元素顺序，保证每个排列概率相等
         * 
         * @param {Array} array - 要打乱的数组
         * @returns {Array} 打乱后的数组（与原数组为同一引用）
         */
        shuffleArray(array) {
            for (let i = array.length - 1; i > 0; i--) {
                const j = Math.floor(Math.random() * (i + 1));
                [array[i], array[j]] = [array[j], array[i]];
            }
            return array;
        }
    }
};

// CDN 格式导出（适配 Vue 3 全局构建）
if (typeof window !== 'undefined') {
    window.answerMixin = answerMixin;
}

// ES Module 导出
if (typeof module !== 'undefined' && module.exports) {
    module.exports = answerMixin;
}
