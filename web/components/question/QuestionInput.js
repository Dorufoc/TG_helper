/**
 * QuestionInput 组件 - 输入组件（填空、简答、释义、论述、编程题）
 * 负责展示填空题、简答题、释义题、论述题、编程题的输入框
 */
const QuestionInput = {
    name: 'QuestionInput',
    template: `
        <div class="input-answer">
            <!-- 填空题使用单行文本框 -->
            <template v-if="question.type === '填空题'">
                <div v-for="(answer, index) in userAnswer" :key="index" class="input-item">
                    <input
                        type="text"
                        v-model="userAnswer[index]"
                        :placeholder="'请输入第' + (index + 1) + '个空的答案'"
                        :disabled="isAnswerViewed || studyMode"
                        @input="handleAutoSaveAnswer"
                        @change="handleAutoSaveAnswer"
                    >
                </div>
            </template>

            <!-- 简答题/释义题/论述题/编程题使用多行文本框 -->
            <template v-else>
                <div v-for="(answer, index) in userAnswer" :key="index" class="input-item">
                    <textarea
                        v-model="userAnswer[index]"
                        :placeholder="'请输入第' + (index + 1) + '题的答案'"
                        :disabled="isAnswerViewed || studyMode"
                        @input="handleAutoSaveAnswer"
                        @change="handleAutoSaveAnswer"
                    ></textarea>
                </div>
            </template>

            <!-- 编程题代码预览框 -->
            <CodePreview
                v-if="question.type === '编程题' && isAnswerViewed && question.correct_answer && question.correct_answer.length > 0"
                v-for="(answer, index) in question.correct_answer"
                :key="'code-' + index"
                :code="normalizeCode(answer)"
                :language="detectLanguage(normalizeCode(answer))"
                :showLineNumbers="true"
                :showCopyButton="true"
                title="参考答案："
            />

            <!-- 填空题/简答题等提交按钮 -->
            <div v-if="!isAnswerViewed && !studyMode" class="submit-answer-section">
                <button @click="handleSubmitAnswer" class="btn btn-primary">确定</button>
            </div>

            <!-- 显示正确答案（非编程题） -->
            <div v-if="isAnswerViewed && question.type !== '编程题'" class="correct-answer">
                <h3>正确答案：</h3>
                <div v-for="(answer, index) in correctAnswer" :key="index" class="correct-answer-item">
                    {{ answer }}
                </div>
            </div>

            <!-- 显示正确答案（编程题的答案说明） -->
            <div v-if="isAnswerViewed && question.type === '编程题' && correctAnswer.length > 0" class="correct-answer">
                <h3>答案说明：</h3>
                <div v-for="(answer, index) in correctAnswer" :key="index" class="correct-answer-item">
                    {{ answer }}
                </div>
            </div>
        </div>
    `,
    components: {
        CodePreview: window.CodePreview
    },
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
        }
    },
    emits: ['updateAnswer', 'submitAnswer', 'autoSaveAnswer'],
    methods: {
        handleAutoSaveAnswer() {
            this.$emit('autoSaveAnswer');
        },

        handleSubmitAnswer() {
            const hasAnswer = this.userAnswer.length > 0 &&
                             this.userAnswer.some(ans => ans && ans.trim() !== '');

            if (!hasAnswer) {
                if (this.$parent && this.$parent.showNotification) {
                    this.$parent.showNotification('请先作答再提交', 'warning');
                }
                return;
            }

            this.$emit('submitAnswer');
        },

        normalizeCode(code) {
            if (!code) return '';
            return code.replace(/《/g, '<').replace(/》/g, '>');
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
        }
    }
};

window.QuestionInput = QuestionInput;
