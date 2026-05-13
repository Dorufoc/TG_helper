// 基于 TextMate 规则的语法高亮引擎
// 从 syntax 目录加载 .tmLanguage.json 文件

const SyntaxHighlighter = {
    // 缓存已加载的语法规则
    grammars: {},
    
    // 加载语法规则
    async loadGrammar(language) {
        if (this.grammars[language]) {
            return this.grammars[language];
        }
        
        const grammarMap = {
            'java': 'java.tmLanguage.json',
            'javascript': 'JavaScript.tmLanguage.json',
            'python': 'MagicPython.tmLanguage.json',
            'c': 'c.tmLanguage.json',
            'cpp': 'cpp.tmLanguage.json',
            'html': 'html.tmLanguage.json',
            'css': 'css.tmLanguage.json',
            'sql': 'sql.tmLanguage.json'
        };
        
        const fileName = grammarMap[language];
        if (!fileName) {
            return null;
        }
        
        try {
            const response = await fetch(`/syntax/${fileName}`);
            const grammar = await response.json();
            this.grammars[language] = grammar;
            return grammar;
        } catch (error) {
            console.error(`加载语法文件失败: ${fileName}`, error);
            return null;
        }
    },
    
    // 从 TextMate 规则提取高亮模式
    extractPatterns(grammar) {
        if (!grammar || !grammar.repository) {
            return [];
        }
        
        const patterns = [];
        const repo = grammar.repository;
        
        // 提取关键字模式
        if (repo['keywords']) {
            patterns.push({ type: 'keyword', patterns: repo['keywords'] });
        }
        
        // 提取注释模式
        if (repo['comments']) {
            patterns.push({ type: 'comment', patterns: repo['comments'] });
        }
        
        // 提取字符串模式
        if (repo['strings']) {
            patterns.push({ type: 'string', patterns: repo['strings'] });
        }
        
        // 提取数字模式
        if (repo['constants']) {
            patterns.push({ type: 'number', patterns: repo['constants'] });
        }
        
        return patterns;
    },
    
    // 简化的语法高亮（基于关键词匹配）- 同步版本
    highlightSimple(code, language) {
        if (!code) return '';
        
        const languagePatterns = {
            java: {
                annotations: /@([A-Z][a-zA-Z]*)\b/g,
                keywords: /\b(abstract|assert|boolean|break|byte|case|catch|char|class|const|continue|default|do|double|else|enum|extends|final|finally|float|for|goto|if|implements|import|instanceof|int|interface|long|native|new|non-sealed|package|permits|private|protected|public|return|sealed|short|static|strictfp|super|switch|synchronized|this|throw|throws|transient|try|void|volatile|while|yield|true|false|null)\b/g,
                types: /\b(String|Integer|Double|Float|Boolean|Object|Class|Math|Arrays|Collections|List|ArrayList|Map|HashMap|Set|HashSet|Exception|RuntimeException|StringBuilder|StringBuffer|Scanner|BufferedReader|PrintWriter|Override|Deprecated|SuppressWarnings|Controller|Service|Repository|Component|Autowired|RequestMapping|ResponseBody|RequestBody|RequestParam|PathVariable|ModelAttribute|InitBinder|Valid|NotNull|NotEmpty|NotBlank|Size|Min|Max|Pattern|DecimalMin|DecimalMax|Digits|Past|Future|Email|URL)\b/g,
                numbers: /\b(\d+\.?\d*[fFdDlL]?)\b/g,
                strings: /"[^"]*"/g,
                comments: /(\/\/.*$|\/\*[\s\S]*?\*\/)/gm
            },
            javascript: {
                keywords: /\b(var|let|const|function|return|if|else|for|while|do|switch|case|break|continue|new|this|class|extends|super|import|export|from|default|try|catch|finally|throw|async|await|yield|typeof|instanceof|in|of|delete|void|null|undefined|NaN|Infinity|true|false)\b/g,
                builtins: /\b(console|document|window|Math|JSON|Array|Object|String|Number|Boolean|Date|RegExp|Map|Set|Promise|Symbol|Error|parseInt|parseFloat|setTimeout|setInterval|clearTimeout|clearInterval|alert|confirm|prompt|fetch|XMLHttpRequest)\b/g,
                functions: /\b([a-zA-Z_$][a-zA-Z0-9_$]*)\s*(?=\()/g,
                strings: /(["'`])(?:(?=(\\?))\2.)*?\1/g,
                comments: /(\/\/.*$|\/\*[\s\S]*?\*\/)/gm,
                numbers: /\b(\d+\.?\d*)\b/g
            },
            python: {
                keywords: /\b(def|class|if|elif|else|for|while|try|except|finally|with|as|import|from|return|yield|lambda|pass|break|continue|and|or|not|in|is|True|False|None|self|async|await|raise|del|global|nonlocal|assert)\b/g,
                builtins: /\b(print|len|range|int|str|float|list|dict|set|tuple|type|isinstance|input|open|map|filter|zip|enumerate|sorted|reversed|sum|min|max|abs|round|bool|super|property|staticmethod|classmethod)\b/g,
                strings: /("""[\s\S]*?"""|'''[\s\S]*?'''|"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/g,
                comments: /(#.*)$/gm,
                numbers: /\b(\d+\.?\d*)\b/g,
                decorators: /(@\w+)/g
            },
            html: {
                tags: /<\/?([a-zA-Z][a-zA-Z0-9]*)/g,
                attributes: /\s([a-zA-Z-]+)(?==)/g,
                strings: /"[^"]*"|'[^']*'/g,
                comments: /<!--[\s\S]*?-->/g
            },
            css: {
                properties: /\b([a-zA-Z-]+)(?=\s*:)/g,
                values: /:\s*([^;]+)/g,
                strings: /"[^"]*"|'[^']*'/g,
                comments: /\/\*[\s\S]*?\*\//g,
                numbers: /\b(\d+\.?\d*)(px|em|rem|%|vh|vw|pt|cm|mm|in|pc)?\b/g,
                colors: /#[0-9a-fA-F]{3,8}\b/g
            }
        };
        
        const patterns = languagePatterns[language] || languagePatterns['javascript'];
        if (!patterns) {
            return this.escapeHtml(code);
        }
        
        // 转义 HTML
        let highlighted = this.escapeHtml(code);
        
        // 按优先级应用高亮规则
        // 1. 注释（最先处理，避免被其他规则干扰）
        if (patterns.comments) {
            highlighted = highlighted.replace(patterns.comments, '<span class="token-comment">$&</span>');
        }
        
        // 2. 字符串
        if (patterns.strings) {
            highlighted = highlighted.replace(patterns.strings, '<span class="token-string">$&</span>');
        }
        
        // 3. 注解（Java 特有）
        if (patterns.annotations) {
            highlighted = highlighted.replace(patterns.annotations, '<span class="token-decorator">@$1</span>');
        }
        
        // 4. 关键字
        if (patterns.keywords) {
            highlighted = highlighted.replace(patterns.keywords, '<span class="token-keyword">$&</span>');
        }
        
        // 5. 类型/内置对象
        if (patterns.types || patterns.builtins) {
            if (patterns.types) {
                highlighted = highlighted.replace(patterns.types, '<span class="token-type">$&</span>');
            }
            if (patterns.builtins) {
                highlighted = highlighted.replace(patterns.builtins, '<span class="token-builtin">$&</span>');
            }
        }
        
        // 6. 函数调用
        if (patterns.functions) {
            highlighted = highlighted.replace(patterns.functions, '<span class="token-function">$1</span>');
        }
        
        // 7. 数字
        if (patterns.numbers) {
            highlighted = highlighted.replace(patterns.numbers, '<span class="token-number">$&</span>');
        }
        
        // 8. HTML 标签和属性
        if (patterns.tags) {
            highlighted = highlighted.replace(/(&lt;\/?)([a-zA-Z][a-zA-Z0-9]*)/g, '$1<span class="token-tag">$2</span>');
        }
        if (patterns.attributes) {
            highlighted = highlighted.replace(/\s([a-zA-Z-]+)(?==)/g, ' <span class="token-attribute">$1</span>');
        }
        
        // 9. CSS 属性
        if (patterns.properties) {
            highlighted = highlighted.replace(patterns.properties, '<span class="token-property">$1</span>');
        }
        
        // 10. 颜色值
        if (patterns.colors) {
            highlighted = highlighted.replace(patterns.colors, '<span class="token-number">$&</span>');
        }
        
        // 11. Python 装饰器
        if (patterns.decorators) {
            highlighted = highlighted.replace(patterns.decorators, '<span class="token-decorator">$1</span>');
        }
        
        return highlighted;
    },
    
    // 转义 HTML 特殊字符
    escapeHtml(text) {
        const map = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        };
        return text.replace(/[&<>"']/g, function(m) { return map[m]; });
    },
    
    // 标准化代码（将中文全角括号转换为标准尖括号）
    normalizeCode(code) {
        if (!code) return '';
        return code.replace(/《/g, '<').replace(/》/g, '>');
    }
};

// 导出为全局可用
window.SyntaxHighlighter = SyntaxHighlighter;
