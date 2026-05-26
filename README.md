<p align="center">
  <img src="https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=A+modern+minimalist+logo+for+%22TG+Helper%22+question+bank+tool%2C+featuring+a+stylized+%22TG%22+letter+combined+with+a+book+and+checkmark+icon%2C+using+deep+purple+%236750A4+as+primary+color%2C+clean+lines%2C+professional+tech+style%2C+vector+graphics&image_size=square_hd" width="128" alt="TG Helper Logo">
</p>

<h1 align="center">TG Helper</h1>

<p align="center">
  <strong>现代化题库管理与智能答题系统</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Flask-3.0-000000?logo=flask&logoColor=white" alt="Flask">
  <img src="https://img.shields.io/badge/Vue.js-3-%234FC08D?logo=vuedotjs&logoColor=white" alt="Vue.js">
  <img src="https://img.shields.io/badge/MD3-Material%20Design%203-6750A4?logo=materialdesign&logoColor=white" alt="MD3">
  <img src="https://img.shields.io/badge/license-AGPLv3-red" alt="License">
  <img src="https://img.shields.io/badge/PRs-welcome-brightgreen" alt="PRs Welcome">
</p>

<p align="center">
  <a href="#核心特性">特性</a> ·
  <a href="#架构总览">架构</a> ·
  <a href="#快速开始">快速开始</a> ·
  <a href="#功能指南">功能指南</a> ·
  <a href="#开源依赖">依赖</a> ·
  <a href="#安全特性">安全</a>
</p>

***

## 简介

**TG Helper** 是一个面向头歌（EduCoder）平台的学习辅助工具，提供完整的题库管理、智能答题练习和知识库检索能力。系统采用 **Flask + Vue.js** 技术栈，支持 **Web 端**与 **GUI 桌面端**双模式运行。

不同于传统的自动答题工具，TG Helper 基于用户已提交并获得满分的作答记录进行题目提取，确保每一道题目的答案都真实可靠。同时内置 **RAG 知识库引擎**，支持将 PDF、DOCX、TXT 等文档导入为向量知识库，实现语义检索与智能问答。

***

## 核心特性

### &#x20;题库管理系统

全面支持头歌平台六大题型：**单选题、多选题、判断题、填空题、简答题、释义题**。题库以标准 JSON 格式存储，支持多题库切换、批量导入导出、题型统计与自定义抽取。

- 自动统计各题型数量分布
- 按题型灵活配置抽取数量
- 支持多题库并行管理与切换

### Web 答题平台

基于 **Flask + Vue.js 3** 构建的响应式 SPA 应用，提供完整的在线刷题体验。

- **多题型作答**：单选 / 多选 / 判断 / 填空 / 简答 / 释义
- **背题模式**：自动显示答案解析，适合考前冲刺
- **答题卡**：全局导航，按题型分组，题目状态可视化（未答 / 已答 / 已查看答案）
- **实时评分**：自动计算得分，展示错题对比
- **暗色模式**：完整支持深色主题，跟随系统偏好

### 错题本系统

- 自动收集练习中的错题，生成结构化错题集
- 支持导出带时间戳的 JSON 错题本文件
- 错题本历史管理（查看 / 删除）
- 详细答题对比，针对性查漏补缺

### &#x20;RAG 知识库引擎

内置完整的检索增强生成（RAG）系统，支持：

- **多格式文档导入**：PDF、DOCX、TXT、Markdown
- **向量化存储**：支持 DeepSeek / SiliconFlow / OpenAI 多种 Embedding 提供商
- **语义检索**：基于向量相似度的高精度内容检索
- **知识库管理**：创建多个知识库，独立管理文档与配置
- **智能对话**：基于检索结果的上下文问答

### &#x20;企业级安全体系

采用多层安全架构设计，保障数据与系统安全：

- **API 传输加密**：RSA 非对称密钥交换 + AES 对称加密
- **数据库安全路由**：SQL 白名单机制，参数化查询审计
- **文件访问控制**：权限分级（只读 / 读写 / 管理员），路径遍历防护
- **审计日志**：全操作链路追踪，支持安全扫描
- **登录限流**：5 分钟窗口内最多 5 次尝试，防暴力破解
- **CSP 安全策略**：内容安全策略 + Nonce 随机数防护 XSS

### 管理员控制台

功能完善的后台管理系统，支持：

- **用户管理**：创建 / 禁用 / 删除用户，角色权限分配
- **题库编辑**：在线编辑器，支持题型、选项、答案、解析的增删改
- **FTP 文件管理器**：服务端文件浏览，支持在线预览代码与图片
- **系统审计**：查看安全报告、操作日志
- **注册管理**：邀请码机制，支持查看用户邀请关系

### 扩展功能

- **网页源代码捕捉器**（PyQt5 内置浏览器）：登录头歌平台，自动抓取已提交满分试题
- **DeepSeek AI 解析**：调用大模型 API 为题目批量生成详细解析
- **CatMario 彩蛋**：内置经典猫里奥小游戏（由 [Tiwb](https://github.com/tiwb/catmario) 移植的 HTML5 版本）
- **语法高亮**：内置 50+ 种编程语言的 TextMate 语法规则（.tmLanguage.json），代码题自动着色。这些语法文件来源于 Visual Studio Code 内置语言扩展所使用的上游仓库，包括 [Microsoft TypeScript-TmLanguage](https://github.com/microsoft/TypeScript-TmLanguage)、[Microsoft vscode-markdown-tm-grammar](https://github.com/microsoft/vscode-markdown-tm-grammar)、[Microsoft vscode-css](https://github.com/microsoft/vscode-css)、[MagicStack/MagicPython](https://github.com/MagicStack/MagicPython) 等

***

## 架构总览

```
┌─────────────────────────────────────────────────────────┐
│                    用户交互层                             │
│  ┌──────────────────┐  ┌─────────────────────────────┐  │
│  │   Web SPA (Vue3) │  │  GUI Desktop (Tkinter/PyQt) │  │
│  │   index.html     │  │  main.py                    │  │
│  │   admin.html     │  │  browser_source_saver.py    │  │
│  │   editor.html    │  │                             │  │
│  │   rag.html       │  │                             │  │
│  │   ftp.html       │  │                             │  │
│  └────────┬─────────┘  └──────────────┬──────────────┘  │
└───────────┼───────────────────────────┼─────────────────┘
            │ HTTP/JSON                 │ subprocess
┌───────────┼───────────────────────────┼─────────────────┐
│           ▼                           ▼                  │
│  ┌──────────────────────────────────────────────────┐   │
│  │              Flask Web Server                    │   │
│  │              web_server.py                       │   │
│  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌───────────────┐  │   │
│  │  │题库API│ │用户API│ │RAG API│ │文件管理API    │  │   │
│  │  └──┬───┘ └──┬───┘ └──┬───┘ └───────┬───────┘  │   │
│  └─────┼────────┼────────┼──────────────┼──────────┘   │
│        │        │        │              │               │
│  ┌─────▼────────▼────────▼──────────────▼──────────┐   │
│  │              安全路由层                            │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────────────┐  │   │
│  │  │DB Router  │ │FileRouter│ │API Encryptor     │  │   │
│  │  │SQL白名单  │ │权限控制  │ │RSA+AES加密       │  │   │
│  │  └─────┬────┘ └────┬─────┘ └────────┬─────────┘  │   │
│  └───────┼────────────┼────────────────┼─────────────┘  │
│          │            │                │                 │
│  ┌───────▼────────────▼────────────────▼─────────────┐   │
│  │              数据存储层                              │   │
│  │  ┌──────────┐ ┌──────────┐ ┌────────────────────┐ │   │
│  │  │ SQLite   │ │ 文件系统 │ │ RAG Vector Store   │ │   │
│  │  │ users.db │ │ paper_* │ │ rag.db (SQLite+Vec) │ │   │
│  │  │ rag.db   │ │ ftp/    │ │                    │ │   │
│  │  └──────────┘ └──────────┘ └────────────────────┘ │   │
│  └────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────┘
```

### 模块分层

| 层级         | 技术                                         | 说明                                 |
| ---------- | ------------------------------------------ | ---------------------------------- |
| **前端 SPA** | Vue.js 3 (CDN) + CSS3 + DOMPurify + Marked | 无构建步骤的组件化前端架构                      |
| **Web 服务** | Flask 3.0 + Flask-CORS                     | RESTful API + CSP 安全头 + Session 管理 |
| **安全中间件**  | DB Router + File Router + API Encryptor    | 统一的权限校验与加密传输                       |
| **数据存储**   | SQLite + NumPy (向量化)                       | 轻量级但功能完备的持久化方案                     |
| **桌面 GUI** | Tkinter / PyQt5 + PyQtWebEngine            | 环境检测 + 一键安装 + 浏览器捕捉                |

***

## 快速开始

### 环境要求

- **Python** 3.9 或更高版本
- **操作系统**：Windows 10/11（推荐），Linux / macOS 亦可
- **可选依赖**：PyQt5 + PyQtWebEngine（仅使用网页源代码捕捉器时需要，其他所有功能无需安装）

### 安装

推荐使用虚拟环境安装：

```bash
# 克隆项目
git clone https://github.com/your-username/TG_helper.git
cd TG_helper

# 创建虚拟环境（推荐）
python -m venv .venv

# Windows 激活虚拟环境
.venv\Scripts\activate

# Linux / macOS 激活虚拟环境
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 启动

#### Web 端（推荐）

```bash
python web_server.py
```

浏览器访问 `http://localhost:5000` 即可使用。默认管理员账户：

| 账户      | 密码            |
| ------- | ------------- |
| `admin` | `admin123123` |

#### GUI 桌面端

```bash
python main.py
```

启动后可通过界面一键安装 PyQt5 组件（**仅用于浏览器捕捉功能**），随后即可使用网页源代码捕捉器。不安装 PyQt5 不影响其他所有功能的使用。

***

## 功能指南

### 答题练习流程

```
选择题库 → 配置题目抽取 → 开始答题 → 查看结果 → 错题复盘
```

1. **加载题库**：启动后系统自动加载当前目录下的 JSON 题库文件
2. **抽取配置**：按题型设置抽取数量（不超过最大可用题数）
3. **答题交互**：选择题点击选项，填空题输入文本，实时进度追踪
4. **查看答案**：支持"背题模式"一键显示解析
5. **提交评分**：自动计算得分，生成错题集

### 题库编辑

通过管理后台的题库编辑器，可在线进行：

- **新增题目**：选择题型，填写题干、选项、正确答案、解析
- **编辑题目**：修改任意题目字段
- **删除题目**：移除指定题目
- **批量操作**：批量导入 / 导出

### 管理员后台

访问 `http://localhost:5000/admin` 进入管理控制台：

- **数据概览**：用户数、题库数、题目总数、错题本数统计
- **用户管理**：查看用户列表、修改角色、启用 / 禁用账户
- **安全审计**：查看安全扫描报告与操作日志
- **回收站**：还原已删除的文件

### RAG 知识库

访问 `http://localhost:5000/rag` 进入知识库系统：

1. **创建知识库**：命名并选择 Embedding 模型与 API 密钥
2. **上传文档**：支持 PDF / DOCX / TXT / MD 格式
3. **配置分块**：自定义分块大小与重叠窗口
4. **语义检索**：输入查询内容，系统返回最相关的文档片段
5. **智能对话**：基于检索结果进行上下文问答

***

## 开源依赖

本项目依赖以下开源组件，按功能分类列出：

### Web 服务核心

| 包名                                               | 版本    | 用途               | 许可证          |
| ------------------------------------------------ | ----- | ---------------- | ------------ |
| [Flask](https://flask.palletsprojects.com/)      | 3.0.x | Web 框架，提供路由与请求处理 | BSD-3-Clause |
| [Flask-CORS](https://flask-cors.readthedocs.io/) | 4.0.x | 跨域资源共享支持         | MIT          |

### 数据处理

| 包名                                                               | 版本     | 用途                  | 许可证          |
| ---------------------------------------------------------------- | ------ | ------------------- | ------------ |
| [requests](https://requests.readthedocs.io/)                     | 2.31.x | HTTP 请求库，用于调用外部 API | Apache-2.0   |
| [beautifulsoup4](https://www.crummy.com/software/BeautifulSoup/) | 4.14.x | HTML/XML 解析，网页数据提取  | MIT          |
| [lxml](https://lxml.de/)                                         | 6.0.x  | 高性能 XML/HTML 解析引擎   | BSD-3-Clause |
| [Pillow](https://python-pillow.org/)                             | 10.2.x | 图像处理，用于验证码生成        | Historical   |

### 安全加密

| 包名                                       | 版本    | 用途                | 许可证              |
| ---------------------------------------- | ----- | ----------------- | ---------------- |
| [cryptography](https://cryptography.io/) | 41.0+ | RSA 密钥生成、AES 加密解密 | Apache-2.0 / BSD |

### RAG 知识库

| 包名                                                 | 版本      | 用途         | 许可证          |
| -------------------------------------------------- | ------- | ---------- | ------------ |
| [NumPy](https://numpy.org/)                        | 1.24+   | 向量计算与相似度运算 | BSD-3-Clause |
| [PyPDF2](https://pypdf2.readthedocs.io/)           | 3.0+    | PDF 文档解析   | BSD-3-Clause |
| [python-docx](https://python-docx.readthedocs.io/) | 0.8.11+ | Word 文档解析  | MIT          |

### 桌面 GUI（可选，仅网页源代码捕捉器需要）

| 包名 | 版本 | 用途 | 许可证 |
|------|------|------|--------|
| [PyQt5](https://www.riverbankcomputing.com/software/pyqt/) | 5.15.x | Qt GUI 框架（内置浏览器容器） | GPL v3 |
| [PyQtWebEngine](https://www.riverbankcomputing.com/software/pyqtwebengine/) | 5.15.x | Chromium 嵌入式浏览器引擎 | GPL v3 |

> 以上两个包仅在需要使用**网页源代码捕捉器**（从头歌平台抓取题目）时才需要安装。系统的 Web 答题平台、RAG 知识库、管理员后台等所有核心功能完全不需要 PyQt5 组件。

### Web 前端（CDN 加载，无需安装）

| 库名                                               | 用途            | 许可证          |
| ------------------------------------------------ | ------------- | ------------ |
| [Vue.js 3](https://vuejs.org/)                   | 前端响应式框架       | MIT          |
| [Marked](https://marked.js.org/)                 | Markdown 渲染引擎 | MIT          |
| [DOMPurify](https://github.com/cure53/DOMPurify) | HTML 安全过滤     | Apache-2.0   |

### 语法高亮规则（静态文件加载）

项目中 `syntax/` 目录包含 50+ 种编程语言的 **TextMate 语法规则文件**（.tmLanguage.json），用于在 Web 端实现代码语法着色。这些规则文件从 Visual Studio Code 内置语言扩展所使用的上游仓库获取并转换，涵盖以下主要来源：

| 上游仓库 | 覆盖语言 |
|----------|----------|
| [Microsoft TypeScript-TmLanguage](https://github.com/microsoft/TypeScript-TmLanguage) | TypeScript、TypeScriptReact、JavaScriptReact |
| [Microsoft vscode-markdown-tm-grammar](https://github.com/microsoft/vscode-markdown-tm-grammar) | Markdown |
| [Microsoft vscode-css](https://github.com/microsoft/vscode-css) | CSS |
| [Microsoft vscode-mssql](https://github.com/microsoft/vscode-mssql) | SQL |
| [MagicStack/MagicPython](https://github.com/MagicStack/MagicPython) | Python |
| [jeff-hykin/better-cpp-syntax](https://github.com/jeff-hykin/better-cpp-syntax) | C、C++ |
| [jeff-hykin/better-shell-syntax](https://github.com/jeff-hykin/better-shell-syntax) | Shell (Bash) |
| [textmate/html.tmbundle](https://github.com/textmate/html.tmbundle) | HTML |
| [textmate/asp.vb.net.tmbundle](https://github.com/textmate/asp.vb.net.tmbundle) | ASP.NET VB |
| [atom/language-xml](https://github.com/atom/language-xml) | XML、XSL |
| [RedCMD/YAML-Syntax-Highlighter](https://github.com/RedCMD/YAML-Syntax-Highlighter) | YAML |
| [jtbandes/swift-tmlanguage](https://github.com/jtbandes/swift-tmlanguage) | Swift |

> 所有可选依赖均可按需安装。核心功能仅需 `requirements.txt` 中的基础依赖即可运行。

***

## 项目结构

```
TG_helper/
│
├── web_server.py              # Flask Web 服务主入口
├── main.py                    # GUI 桌面端启动器（Tkinter）
├── requirements.txt           # Python 依赖清单
│
├── web/                       # Web 前端
│   ├── index.html             # 答题首页
│   ├── admin.html             # 管理员后台
│   ├── editor.html            # 题库编辑器
│   ├── rag.html               # RAG 知识库
│   ├── ftp.html               # FTP 文件管理器
│   ├── register.html          # 用户注册页
│   ├── app.js                 # Vue.js 主应用逻辑
│   ├── admin.js               # 管理后台逻辑
│   ├── editor.js              # 编辑器逻辑
│   ├── rag.js                 # RAG 页面逻辑
│   │
│   ├── components/            # Vue.js 组件
│   │   ├── auth/              # 认证组件（LoginModal）
│   │   ├── common/            # 通用组件（弹窗、通知、选择器）
│   │   ├── layout/            # 布局组件（顶栏、进度条）
│   │   ├── question/          # 题目组件（卡片、选项、输入、解析）
│   │   ├── result/            # 结果展示组件
│   │   ├── wrong-book/        # 错题本组件
│   │   ├── answer-sheet/      # 答题卡组件
│   │   └── editor/            # 题库编辑器组件
│   │
│   ├── mixins/                # Vue.js Mixins
│   │   ├── answer-mixin.js    # 答题逻辑混入
│   │   └── navigation-mixin.js # 导航逻辑混入
│   │
│   ├── utils/                 # 工具函数
│   │   ├── api.js             # API 请求封装
│   │   ├── auth.js            # 认证相关
│   │   ├── auth_manager.js    # 认证状态管理
│   │   ├── storage.js         # 本地存储
│   │   ├── answer-validator.js# 答案验证
│   │   └── api_encryption.js  # 前端加密
│   │
│   └── styles/                # 样式表
│       ├── tokens.css         # MD3 设计令牌
│       ├── main.css           # 主样式文件
│       ├── admin.css          # 管理后台样式
│       └── ...                # 各组件样式
│
├── game/                      # CatMario 彩蛋游戏
│   ├── docs/                  # 游戏资源（HTML/JS/图片/音效）
│   └── src/                   # 游戏源码（C/Emscripten）
│
├── syntax/                    # 语法高亮规则（50+ 语言）
│   ├── Python.tmLanguage.json
│   ├── JavaScript.tmLanguage.json
│   ├── cpp.tmLanguage.json
│   └── ...
│
├── logs/                      # 运行日志
│
├── api_encryptor.py           # API 加密模块（RSA 密钥对管理）
├── db_router.py               # 数据库安全路由
├── db_connection_pool.py      # 数据库连接池
├── db_audit_logger.py         # 数据库审计日志
├── db_security_scanner.py     # 数据库安全扫描器
├── user_database.py           # 用户数据库操作
├── file_router.py             # 文件访问控制路由
├── file_trash_manager.py      # 文件回收站管理器
├── file_audit_logger.py       # 文件操作审计日志
├── rag_module.py              # RAG 知识库核心引擎
├── parse_questions.py         # 文本题库解析器
├── deepseek_parser.py         # DeepSeek AI 解析调用
├── browser_source_saver.py    # PyQt5 网页源代码捕捉器
├── migrate_users.py           # 用户数据迁移工具
└── encryption_keys.json       # RSA 密钥对存储文件
```

***

## 安全特性

### API 传输加密

采用 **RSA 非对称加密 + AES 对称加密** 双层方案：

1. 客户端请求 `/api/get_public_key` 获取 RSA 公钥
2. 客户端生成 AES 密钥，用 RSA 公钥加密后传输
3. 服务端用 RSA 私钥解密，获得 AES 会话密钥
4. 后续敏感数据传输使用 AES 加密

密钥对每 10 分钟轮换一次，历史密钥立即销毁。

### 数据库安全

- **SQL 查询白名单**：所有 SQL 操作必须通过预注册的模板执行，杜绝 SQL 注入
- **参数化查询**：所有用户输入均通过参数化绑定传递
- **权限分级**：READ\_ONLY / READ\_WRITE / ADMIN 三级权限控制
- **审计日志**：记录所有数据库操作的时间、用户、查询类型

### 文件访问控制

- **统一文件路由**：所有文件操作必须通过 FileRouter 中间件
- **路径遍历防护**：使用 `os.path.realpath()` 校验目标路径在允许范围内
- **文件类型白名单**：限制可访问的文件扩展名
- **操作权限控制**：文件级只读 / 读写 / 管理员权限
- **回收站机制**：删除操作先移入回收站，支持恢复

### Web 安全

- **CSP 内容安全策略**：限制脚本、样式、字体等资源加载来源
- **Nonce 随机数**：内联脚本注入 Nonce，阻断 XSS 攻击
- **登录限流**：同一 IP 5 分钟内最多尝试 5 次登录
- **Session 安全**：HttpOnly + SameSite 属性，防 CSRF 攻击

***

## 参与贡献

欢迎通过 Issue 和 Pull Request 贡献代码。在提交 PR 前请确保：

1. 代码风格与现有项目保持一致
2. 新增功能包含对应的测试用例
3. 所有测试通过

项目作者：[@Dorufoc](https://github.com/Dorufoc)

***

## 许可证

本项目采用 **GNU Affero General Public License v3.0 (AGPL-3.0)** 开源协议。

AGPL 要求在网络环境下使用本软件的用户也能获取源代码。详情请参阅 [LICENSE](LICENSE) 文件。
