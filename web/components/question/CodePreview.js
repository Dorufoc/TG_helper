/**
 * CodePreview 组件 - 代码预览组件（编程题专用）
 * 负责展示代码高亮、行号、复制功能
 */
const CodePreview = {
    name: 'CodePreview',
    template: `
        <div class="code-answer">
            <h3 v-if="title">{{ title }}</h3>
            <div class="code-preview-wrapper">
                <div v-if="code && code.trim()" class="code-preview">
                    <!-- 代码头部 -->
                    <div class="code-header">
                        <div class="code-language">
                            <span>{{ getCodeLanguageIcon(language) }}</span>
                            <span>{{ language }}</span>
                        </div>
                        <div class="code-actions">
                            <button v-if="showCopyButton" @click="handleCopyCode" class="btn code-btn">复制代码</button>
                        </div>
                    </div>
                    <!-- 代码容器 -->
                    <div class="code-container">
                        <!-- 行号 -->
                        <div v-if="showLineNumbers" class="line-numbers">
                            <span v-for="(line, lineIndex) in codeLines" :key="lineIndex" class="line-number">{{ lineIndex + 1 }}</span>
                        </div>
                        <!-- 代码内容 -->
                        <div class="code-content" v-html="highlightedCode"></div>
                    </div>
                </div>
            </div>
        </div>
    `,
    props: {
        code: {
            type: String,
            default: ''
        },
        language: {
            type: String,
            default: 'javascript'
        },
        showLineNumbers: {
            type: Boolean,
            default: true
        },
        showCopyButton: {
            type: Boolean,
            default: true
        },
        title: {
            type: String,
            default: ''
        }
    },
    emits: ['copyCode'],
    computed: {
        codeLines() {
            return this.code ? this.code.split('\n') : [];
        },
        highlightedCode() {
            return this.highlightCode(this.code, this.language);
        }
    },
    methods: {
        highlightCode(code, language) {
            if (!code) return '';

            // 使用全局的 SyntaxHighlighter 进行高亮
            if (typeof SyntaxHighlighter !== 'undefined' && SyntaxHighlighter.highlightSimple) {
                return SyntaxHighlighter.highlightSimple(code, language);
            }

            // 降级方案：直接返回转义后的代码
            return this.escapeHtml(code);
        },

        escapeHtml(text) {
            if (!text) return '';
            return text
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;');
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

        handleCopyCode() {
            this.$emit('copyCode', this.code);

            // 组件内部也提供复制功能
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(this.code).then(() => {
                    if (this.$parent && this.$parent.showNotification) {
                        this.$parent.showNotification('代码已复制到剪贴板', 'success');
                    }
                }).catch(() => {
                    this.fallbackCopy();
                });
            } else {
                this.fallbackCopy();
            }
        },

        fallbackCopy() {
            const textarea = document.createElement('textarea');
            textarea.value = this.code;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.select();
            try {
                document.execCommand('copy');
                if (this.$parent && this.$parent.showNotification) {
                    this.$parent.showNotification('代码已复制到剪贴板', 'success');
                }
            } catch (err) {
                if (this.$parent && this.$parent.showNotification) {
                    this.$parent.showNotification('复制失败，请手动复制', 'error');
                }
            }
            document.body.removeChild(textarea);
        }
    }
};

window.CodePreview = CodePreview;
