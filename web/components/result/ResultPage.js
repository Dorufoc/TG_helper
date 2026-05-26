const ResultPage = {
    name: 'ResultPage',
    template: `
        <div class="container">
            <h1>考试成绩</h1>

            <!-- 成绩头部 -->
            <div class="result">
                <p class="score">得分：{{ result.score }}分</p>
                <p>正确题数：{{ result.correct_count }}/{{ result.total_questions }}</p>
                <button @click="$emit('restart')" class="btn btn-primary">重新开始</button>
                <button
                    @click="$emit('generateWrongBook')"
                    class="btn btn-secondary"
                    v-if="result.wrong_questions && result.wrong_questions.length > 0"
                >
                    生成错题本
                </button>
            </div>

            <!-- 错题集列表 -->
            <div v-if="result.wrong_questions && result.wrong_questions.length > 0" class="wrong-questions">
                <h2>错题集</h2>
                <div
                    v-for="(question, index) in result.wrong_questions"
                    :key="index"
                    class="wrong-question-item"
                >
                    <div class="question-header">
                        <h3>第{{ question.id }}题 ({{ question.type }})</h3>
                    </div>
                    <div class="question-content">{{ question.content }}</div>

                    <!-- 显示选项 -->
                    <div v-if="question.options && question.options.length > 0" class="options">
                        <div v-for="(option, optIndex) in question.options" :key="optIndex" class="option-item">
                            <label
                                :class="{
                                    'correct': getCorrectOptionClass(question, optIndex, option),
                                    'incorrect': getUserWrongOptionClass(question, optIndex, option)
                                }"
                            >
                                {{ getOptionLetter(optIndex) }}. {{ option }}
                            </label>
                        </div>
                    </div>

                    <!-- 显示答案 -->
                    <div class="answers">
                        <p><strong>您的答案：</strong>{{ formatAnswer(question.user_answer) }}</p>
                        <p><strong>正确答案：</strong>{{ formatAnswer(question.correct_answer) }}</p>
                    </div>

                    <!-- 答案解析 -->
                    <div v-if="question.analysis" class="analysis">
                        <h4>解析：</h4>
                        <div class="analysis-content" v-html="renderMarkdown(question.analysis)"></div>
                    </div>
                </div>
            </div>
        </div>
    `,
    props: {
        result: {
            type: Object,
            required: true
            // 期望结构: { score, correct_count, total_questions, wrong_questions: [{ id, type, content, options, user_answer, correct_answer, analysis }] }
        },
        studyMode: {
            type: Boolean,
            required: true
        }
    },
    emits: ['restart', 'generateWrongBook'],
    methods: {
        getOptionLetter(index) {
            return String.fromCharCode(65 + index);
        },
        formatAnswer(answer) {
            if (Array.isArray(answer)) {
                return answer.join(', ');
            }
            return answer;
        },
        getCorrectOptionClass(question, optIndex, option) {
            if (question.type === '判断题') {
                return question.correct_answer.includes(option);
            }
            return question.correct_answer.includes(this.getOptionLetter(optIndex));
        },
        getUserWrongOptionClass(question, optIndex, option) {
            if (question.type === '判断题') {
                return question.user_answer.includes(option) && !question.correct_answer.includes(option);
            }
            return question.user_answer.includes(this.getOptionLetter(optIndex)) &&
                   !question.correct_answer.includes(this.getOptionLetter(optIndex));
        },
        renderMarkdown(text) {
            if (!text) return '';
            const escapedText = this.escapeHtmlTagsInMarkdown(text);
            if (typeof marked !== 'undefined') {
                const rawHtml = marked.parse(escapedText);
                if (typeof DOMPurify !== 'undefined') {
                    return DOMPurify.sanitize(rawHtml);
                }
                return rawHtml;
            }
            return escapedText;
        },
        escapeHtmlTagsInMarkdown(text) {
            const parts = [];
            const codeBlockRegex = /(```[\s\S]*?```|`[^`]*`)/g;
            let lastIndex = 0;
            let match;

            while ((match = codeBlockRegex.exec(text)) !== null) {
                if (match.index > lastIndex) {
                    parts.push({
                        type: 'text',
                        content: text.substring(lastIndex, match.index)
                    });
                }
                parts.push({
                    type: 'code',
                    content: match[0]
                });
                lastIndex = match.index + match[0].length;
            }

            if (lastIndex < text.length) {
                parts.push({
                    type: 'text',
                    content: text.substring(lastIndex)
                });
            }

            return parts.map(part => {
                if (part.type === 'code') {
                    return part.content;
                }
                return part.content.replace(/<([a-zA-Z][a-zA-Z0-9-]*)>/g, '&lt;$1&gt;')
                                   .replace(/<\/([a-zA-Z][a-zA-Z0-9-]*)>/g, '&lt;/$1&gt;');
            }).join('');
        }
    }
};
window.ResultPage = ResultPage;
