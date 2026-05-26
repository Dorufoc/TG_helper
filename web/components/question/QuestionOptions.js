/**
 * QuestionOptions 组件 - 选项组件（支持单选、多选、判断）
 * 负责展示判断题、单选题、多选题的选项
 */
const QuestionOptions = {
    name: 'QuestionOptions',
    template: `
        <div class="options">
            <!-- 判断题 -->
            <div v-if="question.type === '判断题'">
                <div
                    v-for="(option, index) in question.options"
                    :key="index"
                    class="option-item"
                    @click="handleSelectOption(option, index)"
                >
                    <input
                        type="radio"
                        :id="'option-' + index"
                        :value="option"
                        v-model="localAnswer"
                        :disabled="isAnswerViewed || studyMode"
                    >
                    <label
                        :for="'option-' + index"
                        :class="{
                            'correct': isAnswerViewed && correctAnswer.includes(option),
                            'incorrect': isAnswerViewed && userAnswer.includes(option) && !correctAnswer.includes(option)
                        }"
                    >
                        {{ option }}
                    </label>
                </div>
            </div>

            <!-- 单选题 -->
            <div v-else-if="question.type === '单选题'">
                <div
                    v-for="(option, index) in question.options"
                    :key="index"
                    class="option-item"
                    @click="handleSelectOption(getOptionLetter(index), index)"
                >
                    <input
                        type="radio"
                        :id="'option-' + index"
                        :value="getOptionLetter(index)"
                        v-model="localAnswer"
                        :disabled="isAnswerViewed || studyMode"
                    >
                    <label
                        :for="'option-' + index"
                        :class="{
                            'correct': isAnswerViewed && correctAnswer.includes(getOptionLetter(index)),
                            'incorrect': isAnswerViewed && userAnswer.includes(getOptionLetter(index)) && !correctAnswer.includes(getOptionLetter(index))
                        }"
                    >
                        {{ getOptionLetter(index) }}. {{ option }}
                    </label>
                </div>
            </div>

            <!-- 多选题 -->
            <div v-else-if="question.type === '多选题'">
                <div
                    v-for="(option, index) in question.options"
                    :key="index"
                    class="option-item"
                >
                    <input
                        type="checkbox"
                        :id="'option-' + index"
                        :value="getOptionLetter(index)"
                        v-model="localAnswer"
                        @change="handleMultipleAnswerChange"
                        :disabled="isAnswerViewed || studyMode"
                    >
                    <label
                        :for="'option-' + index"
                        :class="{
                            'correct': isAnswerViewed && correctAnswer.includes(getOptionLetter(index)),
                            'incorrect': isAnswerViewed && userAnswer.includes(getOptionLetter(index)) && !correctAnswer.includes(getOptionLetter(index))
                        }"
                    >
                        {{ getOptionLetter(index) }}. {{ option }}
                    </label>
                </div>
                <!-- 多选题提交按钮 -->
                <div v-if="!isAnswerViewed && !studyMode" class="submit-answer-section">
                    <button @click="handleSubmitAnswer" class="btn btn-primary">确定</button>
                </div>
            </div>
        </div>
    `,
    props: {
        question: {
            type: Object,
            required: true
        },
        userAnswer: {
            type: Array,
            default: () => []
        },
        correctAnswer: {
            type: Array,
            default: () => []
        },
        isAnswerViewed: {
            type: Boolean,
            default: false
        },
        studyMode: {
            type: Boolean,
            default: false
        },
        autoShowAnswer: {
            type: Boolean,
            default: false
        }
    },
    emits: ['selectOption', 'submitAnswer'],
    computed: {
        localAnswer: {
            get() {
                if (this.question.type === '多选题') {
                    return this.userAnswer;
                }
                return this.userAnswer[0] || '';
            },
            set(value) {
                if (this.question.type === '多选题') {
                    return;
                }
                this.$emit('selectOption', { option: value, index: this.getOptionIndex(value) });
            }
        }
    },
    methods: {
        getOptionLetter(index) {
            return String.fromCharCode(65 + index);
        },

        getOptionIndex(value) {
            if (/^[A-Z]$/.test(value)) {
                return value.charCodeAt(0) - 65;
            }
            const idx = this.question.options.indexOf(value);
            return idx >= 0 ? idx : 0;
        },

        handleSelectOption(value, index) {
            if (this.isAnswerViewed || this.studyMode) {
                return;
            }

            this.$emit('selectOption', { option: value, index: index });

            if (this.autoShowAnswer && !this.isAnswerViewed) {
                this.$emit('submitAnswer');
            }
        },

        handleMultipleAnswerChange() {
            if (!this.isAnswerViewed && !this.studyMode) {
                this.$emit('selectOption', { option: this.userAnswer, index: -1 });
            }
        },

        handleSubmitAnswer() {
            this.$emit('submitAnswer');
        }
    }
};

window.QuestionOptions = QuestionOptions;
