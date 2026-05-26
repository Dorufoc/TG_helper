/**
 * 题目导航混入模块 (navigation-mixin)
 * 
 * 提供题目加载、切换导航、答题卡、触摸手势、键盘事件等功能。
 * 
 * 需要的 data 属性（宿主 Vue 实例必须提供）：
 *   - currentIndex {Number} - 当前题目索引
 *   - totalQuestions {Number} - 总题目数
 *   - localQuestions {Array} - 本地存储的所有题目
 *   - localAnswers {Object} - 本地存储的用户答案，以索引为键
 *   - localViewedAnswers {Object} - 本地存储的已查看答案状态，以索引为键
 *   - currentQuestion {Object|null} - 当前题目对象
 *   - userAnswer {Array} - 当前题目的用户答案
 *   - correctAnswer {Array} - 当前题目的正确答案
 *   - isAnswerViewed {Boolean} - 是否已查看答案
 *   - studyMode {Boolean} - 是否为背题模式
 *   - error {String} - 错误信息
 *   - answerSheet {Object} - 答题卡状态 { show, questions, typeOrder }
 *   - questionTransitionName {String} - 题目切换动画名称
 *   - questionRenderKey {Number} - 题目渲染 key
 *   - touchGesture {Object} - 触摸手势状态 { startX, startY, deltaX, deltaY, active }
 *   - step {String} - 当前步骤 ('load', 'extract', 'answer', 'result')
 * 
 * 依赖的宿主方法：
 *   - showNotification(message, type) - 显示通知提示
 *   - viewAnswer() - 查看答案（在背题模式下使用，通常与 answer-mixin 一起使用）
 *   - initUserAnswer() - 初始化用户答案（在背题模式下使用）
 *   - loadCurrentQuestion() - 加载当前题目（与本 mixin 中的同名方法相同）
 * 
 * 依赖的全局函数：
 *   - apiFetch(url, options) - 统一的请求方法
 * 
 * 使用方式：
 *   Vue.createApp({
 *     mixins: [navigationMixin, answerMixin],
 *     // ...
 *   })
 */

const navigationMixin = {
    computed: {
        /**
         * 是否可以上一题
         * 当前索引大于 0 时可以上一题
         * @returns {Boolean}
         */
        canGoPrev() {
            return this.currentIndex > 0;
        },

        /**
         * 是否可以下一题
         * 当前索引小于总题目数减 1 时可以下一题
         * @returns {Boolean}
         */
        canGoNext() {
            return this.currentIndex < this.totalQuestions - 1;
        }
    },

    methods: {
        /**
         * 从本地加载当前题目
         * 根据 currentIndex 从 localQuestions 中获取题目数据，并恢复用户答案和已查看状态
         * 对于填空题/简答题等，根据正确答案数量初始化答案数组
         * 如果是背题模式且未查看答案，自动查看答案
         */
        loadCurrentQuestion() {
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

        /**
         * 获取正确答案（API 调用）
         * 通过后端 API 获取当前题目的正确答案和解析
         * 注意：此方法需要全局函数 apiFetch 可用
         */
        async fetchCorrectAnswer() {
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

        /**
         * 查看答案（本地）
         * 从本地题目数据中获取正确答案并显示，更新已查看答案状态
         */
        viewAnswer() {
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

        /**
         * 上一题
         * 调用 navigateToQuestion 切换到上一题
         */
        prevQuestion() {
            this.navigateToQuestion(this.currentIndex - 1, 'prev');
        },

        /**
         * 下一题
         * 调用 navigateToQuestion 切换到下一题
         */
        nextQuestion() {
            this.navigateToQuestion(this.currentIndex + 1, 'next');
        },

        /**
         * 统一导航到指定题目
         * 处理题目切换的动画方向和状态更新，复用于按钮/答题卡/滑动等所有导航入口
         * 
         * @param {Number} targetIndex - 目标题目索引
         * @param {String} direction - 导航方向 ('prev' 或 'next')，用于确定动画效果
         */
        navigateToQuestion(targetIndex, direction = 'next') {
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

        /**
         * 跳转到指定题目（从答题卡）
         * 关闭答题卡后跳转到目标题目，自动判断方向
         * 
         * @param {Number} index - 目标题目索引
         */
        jumpToQuestion(index) {
            this.answerSheet.show = false;
            const direction = index >= this.currentIndex ? 'next' : 'prev';
            this.navigateToQuestion(index, direction);
        },

        /**
         * 触摸开始事件处理
         * 记录触摸起始位置，过滤交互元素和代码预览区域的触摸
         * 
         * @param {TouchEvent} event - 触摸事件对象
         */
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

        /**
         * 触摸移动事件处理
         * 计算触摸偏移量（deltaX, deltaY）
         * 
         * @param {TouchEvent} event - 触摸事件对象
         */
        onQuestionTouchMove(event) {
            if (!this.touchGesture.active || !event.touches || event.touches.length !== 1) {
                return;
            }

            const touch = event.touches[0];
            this.touchGesture.deltaX = touch.clientX - this.touchGesture.startX;
            this.touchGesture.deltaY = touch.clientY - this.touchGesture.startY;
        },

        /**
         * 触摸结束事件处理
         * 判断是否为有效水平滑动（超过最小距离且水平位移大于垂直位移），触发切题
         */
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

        /**
         * 触摸取消事件处理
         * 重置触摸手势状态
         */
        onQuestionTouchCancel() {
            this.touchGesture.active = false;
        },

        /**
         * 键盘事件处理（左右方向键、数字键选选项）
         * 监听左右方向键切换题目，数字键 1-9 映射到选项 A-I
         * 在答题页面且焦点不在交互元素内时响应
         * 
         * @param {KeyboardEvent} event - 键盘事件对象
         */
        handleKeyboard(event) {
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

        /**
         * 通过数字键选择选项
         * 将数字键 1-9 映射到选项，支持判断题、单选题、多选题
         * 
         * @param {Number} optionIndex - 选项索引（0 开始）
         */
        selectOptionByKey(optionIndex) {
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

        /**
         * 获取答题卡卡片 CSS 类名
         * 根据题目是否已作答、已查看、当前选中状态返回对应的 CSS 类名数组
         * 
         * @param {Object} question - 答题卡题目对象 { is_answered, is_viewed, index }
         * @returns {Array<String>} CSS 类名数组
         */
        getCardClasses(question) {
            const classes = [];
            if (question.is_answered) classes.push('answered');
            if (question.is_viewed) classes.push('viewed');
            // 当前题目高亮
            if (question.index === this.currentIndex) classes.push('current');
            return classes;
        },

        /**
         * 加载答题卡数据
         * 从本地题目数据中构建答题卡，按题型分组并编号
         */
        loadAnswerSheet() {
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

        /**
         * 显示/隐藏答题卡
         * 切换答题卡的可见状态，显示时自动加载答题卡数据
         */
        toggleAnswerSheet() {
            if (this.answerSheet.show) {
                this.answerSheet.show = false;
            } else {
                this.loadAnswerSheet();
                this.answerSheet.show = true;
            }
        }
    }
};

// CDN 格式导出（适配 Vue 3 全局构建）
if (typeof window !== 'undefined') {
    window.navigationMixin = navigationMixin;
}

// ES Module 导出
if (typeof module !== 'undefined' && module.exports) {
    module.exports = navigationMixin;
}
