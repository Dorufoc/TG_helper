/**
 * QuestionAnalysis 组件 - 答案解析组件
 * 负责展示 Markdown 格式的答案解析
 */
const QuestionAnalysis = {
    name: 'QuestionAnalysis',
    template: `
        <div v-if="show && analysis" class="analysis">
            <h3>答案解析：</h3>
            <div class="analysis-content" v-html="renderedAnalysis"></div>
        </div>
    `,
    props: {
        analysis: {
            type: String,
            default: ''
        },
        show: {
            type: Boolean,
            default: false
        }
    },
    computed: {
        renderedAnalysis() {
            return this.renderMarkdown(this.analysis);
        }
    },
    methods: {
        renderMarkdown(text) {
            if (!text) return '';

            const escapedText = this.escapeHtmlTagsInMarkdown(text);

            if (typeof marked !== 'undefined' && marked.parse) {
                const rawHtml = marked.parse(escapedText);
                if (typeof DOMPurify !== 'undefined') {
                    return DOMPurify.sanitize(rawHtml);
                }
                return rawHtml;
            }

            return this.escapeHtml(escapedText);
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
                } else {
                    return part.content.replace(/<([a-zA-Z][a-zA-Z0-9-]*)>/g, '&lt;$1&gt;')
                                       .replace(/<\/([a-zA-Z][a-zA-Z0-9-]*)>/g, '&lt;/$1&gt;');
                }
            }).join('');
        },

        escapeHtml(text) {
            if (!text) return '';
            return text
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;');
        }
    }
};

window.QuestionAnalysis = QuestionAnalysis;
