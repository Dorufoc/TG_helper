/**
 * QuestionCard 组件 - 题目卡片容器
 * 负责展示题目头部、图片、内容，并组合使用子组件
 */
const QuestionCard = {
    name: 'QuestionCard',
    template: `
        <Transition :name="questionTransitionName">
            <div
                v-if="question"
                :key="questionRenderKey"
                class="question"
                @touchstart.passive="handleTouchStart"
                @touchmove.passive="handleTouchMove"
                @touchend="handleTouchEnd"
                @touchcancel="handleTouchCancel"
            >
                <!-- 题目头部 -->
                <div class="question-header">
                    <h2>题目 {{ currentIndex + 1 }}</h2>
                    <span class="question-type">{{ question.type }}</span>
                </div>

                <!-- 题目图片 -->
                <div v-if="question.image" class="question-image-container">
                    <img
                        :src="getQuestionImageUrl(question.image)"
                        alt="题目图片"
                        class="question-image"
                        @error="handleImageError"
                        @load="handleImageLoad"
                    >
                </div>

                <!-- 题目内容 -->
                <div class="question-content">{{ question.content }}</div>

                <!-- 选择题选项（判断、单选、多选） -->
                <QuestionOptions
                    v-if="question.options && question.options.length > 0"
                    :question="question"
                    :userAnswer="userAnswer"
                    :correctAnswer="correctAnswer"
                    :isAnswerViewed="isAnswerViewed"
                    :studyMode="studyMode"
                    :autoShowAnswer="autoShowAnswer"
                    @selectOption="$emit('selectOption', $event.option, $event.index)"
                    @submitAnswer="$emit('submitAnswer')"
                />

                <!-- 输入题（填空、简答、释义、论述、编程） -->
                <QuestionInput
                    v-else-if="isInputType(question.type)"
                    :question="question"
                    :userAnswer="userAnswer"
                    :correctAnswer="correctAnswer"
                    :isAnswerViewed="isAnswerViewed"
                    :studyMode="studyMode"
                    @updateAnswer="$emit('updateAnswer', $event)"
                    @submitAnswer="$emit('submitAnswer')"
                    @autoSaveAnswer="$emit('autoSaveAnswer')"
                />

                <!-- 答案解析 -->
                <QuestionAnalysis
                    v-if="isAnswerViewed && question.analysis"
                    :analysis="question.analysis"
                    :show="isAnswerViewed"
                />
            </div>
        </Transition>
    `,
    components: {
        QuestionOptions: window.QuestionOptions,
        QuestionInput: window.QuestionInput,
        QuestionAnalysis: window.QuestionAnalysis
    },
    props: {
        question: {
            type: Object,
            default: null
        },
        currentIndex: {
            type: Number,
            default: 0
        },
        totalQuestions: {
            type: Number,
            default: 0
        },
        isAnswerViewed: {
            type: Boolean,
            default: false
        },
        studyMode: {
            type: Boolean,
            default: false
        },
        userAnswer: {
            type: Array,
            default: () => []
        },
        correctAnswer: {
            type: Array,
            default: () => []
        },
        questionTransitionName: {
            type: String,
            default: 'question-slide-next'
        },
        questionRenderKey: {
            type: Number,
            default: 0
        },
        autoShowAnswer: {
            type: Boolean,
            default: false
        }
    },
    emits: [
        'selectOption',
        'submitAnswer',
        'viewAnswer',
        'prevQuestion',
        'nextQuestion',
        'touchStart',
        'touchMove',
        'touchEnd',
        'touchCancel',
        'updateAnswer',
        'autoSaveAnswer'
    ],
    methods: {
        isInputType(type) {
            return ['填空题', '简答题', '释义题', '论述题', '编程题'].includes(type);
        },

        getQuestionImageUrl(imagePath) {
            if (!imagePath) return '';
            if (imagePath.startsWith('http://') || imagePath.startsWith('https://') || imagePath.startsWith('data:')) {
                return imagePath;
            }
            let normalizedPath = imagePath.replace(/\\/g, '/');
            if (normalizedPath.startsWith('/')) {
                normalizedPath = normalizedPath.substring(1);
            }
            return `/api/question_image/${normalizedPath}`;
        },

        handleImageError(event) {
            const container = event.target.closest('.question-image-container');
            if (container) {
                container.style.display = 'none';
            }
        },

        handleImageLoad(event) {
            const container = event.target.closest('.question-image-container');
            if (container) {
                container.style.display = 'flex';
            }
        },

        handleTouchStart(event) {
            this.$emit('touchStart', event);
        },

        handleTouchMove(event) {
            this.$emit('touchMove', event);
        },

        handleTouchEnd(event) {
            this.$emit('touchEnd', event);
        },

        handleTouchCancel(event) {
            this.$emit('touchCancel', event);
        }
    }
};
window.QuestionCard = QuestionCard;
