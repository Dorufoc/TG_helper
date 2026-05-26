# TGHelper Web 项目安全审查报告

**审查日期**: 2026-05-26  
**审查范围**: Python Flask 后端 + Vue.js 前端  
**审查依据**: OWASP 安全最佳实践、Flask 安全指南、前端 JavaScript 安全规范

---

## 执行摘要

本项目整体安全架构良好，已实施多项安全措施：
- ✅ 使用 PBKDF2 进行密码哈希
- ✅ 数据库访问使用参数化查询和白名单验证
- ✅ API 密钥使用 RSA 加密存储
- ✅ 实现了 CSRF 保护
- ✅ 配置了安全响应头
- ✅ 实现了登录限流

但仍发现一些需要改进的安全问题，下文按严重程度分类列出。

---

## 🔴 严重 (Critical)

### 问题 1: CSP 配置过于宽松

**规则 ID**: PY-CSP-001  
**位置**: `web_server.py:1022-1031`  
**严重程度**: Critical

**问题描述**:
当前 CSP 配置允许 `'unsafe-inline'` 和 `'unsafe-eval'`，这会显著降低 CSP 对 XSS 攻击的防护效果。

```python
# 当前配置 (不安全)
csp_policy = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "  # ❌ 过于宽松
    "style-src 'self' 'unsafe-inline'; "
    ...
)
```

**影响**: 攻击者可以通过注入内联脚本或执行动态代码来实施 XSS 攻击。

**修复建议**:
1. 移除 `'unsafe-inline'` 和 `'unsafe-eval'`
2. 使用 nonce 或 hash 来允许特定的内联脚本
3. 将外部脚本移至独立 JS 文件

```python
# 建议配置
csp_policy = (
    "default-src 'self'; "
    "script-src 'self'; "  # ✅ 严格模式
    "style-src 'self'; "
    "img-src 'self' data: blob:; "
    "connect-src 'self'; "
    "font-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)
```

---

### 问题 2: 返回用户密码哈希给管理员

**规则 ID**: PY-DATA-001  
**位置**: `web_server.py:1741`  
**严重程度**: Critical

**问题描述**:
在获取用户列表的 API 中，将用户的密码哈希返回给前端：

```python
# web_server.py:1739-1748
user_list.append({
    'username': username,
    'password': user.get('password'),  # ❌ 返回密码哈希
    'role': user.get('role', 'user'),
    ...
})
```

**影响**: 
- 密码哈希泄露给前端，增加被破解风险
- 违反最小权限原则

**修复建议**:
```python
user_list.append({
    'username': username,
    # 'password': user.get('password'),  # ✅ 移除此行
    'role': user.get('role', 'user'),
    ...
})
```

---

## 🟠 高 (High)

### 问题 3: 文件路径遍历风险

**规则 ID**: PY-PATH-001  
**位置**: `web_server.py:1186-1191`  
**严重程度**: High

**问题描述**:
虽然代码尝试防止路径遍历，但存在潜在绕过风险：

```python
# web_server.py:1186-1191
safe_path = os.path.abspath(os.path.join(PAPER_JSON_DIR, file_path))
if not safe_path.startswith(PAPER_JSON_DIR):  # ❌ 可能被绕过
    raise ValueError("非法文件路径，禁止跨目录访问")
```

**影响**: 攻击者可能通过构造特殊路径（如使用 Unicode 规范化差异）绕过检查。

**修复建议**:
```python
import os
from pathlib import Path

def validate_safe_path(base_dir: str, user_path: str) -> str:
    """安全路径验证"""
    # 规范化基础目录
    base = Path(base_dir).resolve()
    
    # 规范化用户路径并解析
    try:
        target = (base / user_path).resolve()
    except (ValueError, RuntimeError):
        raise ValueError("非法文件路径")
    
    # 检查是否在基础目录内
    try:
        target.relative_to(base)
    except ValueError:
        raise ValueError("非法文件路径，禁止跨目录访问")
    
    return str(target)
```

---

### 问题 4: 验证码使用后未立即清除

**规则 ID**: PY-SESSION-001  
**位置**: `web_server.py:1460-1462`  
**严重程度**: High

**问题描述**:
验证码验证通过后，session 中的验证码未及时清除：

```python
# web_server.py:1460-1462 (register 函数)
session_captcha = session.get('captcha_code', '').lower()
if captcha.lower() != session_captcha:
    return jsonify({'success': False, 'message': '验证码错误'}), 400
# ❌ 缺少 session.pop('captcha_code', None)
```

**影响**: 验证码可被重复使用，降低暴力破解防护效果。

**修复建议**:
```python
session_captcha = session.get('captcha_code', '').lower()
if captcha.lower() != session_captcha:
    return jsonify({'success': False, 'message': '验证码错误'}), 400
session.pop('captcha_code', None)  # ✅ 验证后立即清除
```

---

### 问题 5: 前端使用 innerHTML 处理用户内容

**规则 ID**: JS-XSS-001  
**位置**: `web/components/question/QuestionAnalysis.js:86`  
**严重程度**: High

**问题描述**:
虽然使用了 DOMPurify，但仍使用 `innerHTML` 作为最终输出方式：

```javascript
// QuestionAnalysis.js:82-86
escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;  // ❌ 使用 innerHTML
}
```

**影响**: 如果 DOMPurify 配置不当或被绕过，仍存在 XSS 风险。

**修复建议**:
使用 `textContent` 替代 `innerHTML`：
```javascript
escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.textContent;  // ✅ 更安全
}
```

---

## 🟡 中 (Medium)

### 问题 6: 会话密钥文件权限设置可能失败

**规则 ID**: PY-FILE-001  
**位置**: `web_server.py:973`  
**严重程度**: Medium

**问题描述**:
```python
os.chmod(SESSION_KEY_FILE, 0o600)  # 仅所有者可读写
```
在 Windows 上，`os.chmod` 对文件权限的控制有限。

**影响**: 会话密钥文件可能被其他用户读取。

**修复建议**:
添加 Windows 特定的权限设置：
```python
import platform

if platform.system() == 'Windows':
    import ctypes
    from pathlib import Path
    
    # Windows 上使用 ACL 设置权限
    file_path = Path(SESSION_KEY_FILE)
    # 移除继承权限，仅保留当前用户
    import subprocess
    subprocess.run(['icacls', str(file_path), '/inheritance:r'], check=False)
    subprocess.run(['icacls', str(file_path), '/grant', f'{os.getlogin()}:F'], check=False)
else:
    os.chmod(SESSION_KEY_FILE, 0o600)
```

---

### 问题 7: 前端存储敏感信息

**规则 ID**: JS-STORAGE-001  
**位置**: `web/utils/auth.js:34-44`  
**严重程度**: Medium

**问题描述**:
代码从 localStorage 读取 deviceId，虽然已迁移到 Cookie，但仍有遗留代码：

```javascript
// auth.js:34-44
deviceId = localStorage.getItem('deviceId');  // ❌ 仍在读取
if (deviceId) {
    _setCookie('deviceId', deviceId, 365);
    localStorage.removeItem('deviceId');
} else {
    deviceId = 'dev-' + Math.random().toString(36).substring(2, 10) + Date.now().toString(36);
    _setCookie('deviceId', deviceId, 365);
}
```

**影响**: 虽然已部分迁移，但仍依赖 localStorage 作为回退。

**修复建议**:
完全移除 localStorage 依赖，直接使用 Cookie：
```javascript
function generateDeviceId() {
    let deviceId = _getCookie('deviceId');
    if (!deviceId) {
        deviceId = 'dev-' + crypto.randomUUID();  // 使用更安全的随机数
        _setCookie('deviceId', deviceId, 365);
    }
    return deviceId;
}
```

---

### 问题 8: 缺少请求体大小限制验证

**规则 ID**: PY-INPUT-001  
**位置**: 多处 API 端点  
**严重程度**: Medium

**问题描述**:
虽然设置了 `MAX_CONTENT_LENGTH`，但部分端点未对请求体进行额外验证：

```python
# 例如 deepseek_parse 端点接收的文件路径
file_path = data.get('file_path', 'questions.json')  # ❌ 未验证路径长度和格式
```

**修复建议**:
```python
import re

def validate_file_path(file_path: str) -> str:
    """验证文件路径安全性"""
    if not file_path:
        return 'questions.json'
    
    # 限制长度
    if len(file_path) > 255:
        raise ValueError("文件路径过长")
    
    # 只允许安全的字符
    if not re.match(r'^[\w\-\./]+$', file_path):
        raise ValueError("文件路径包含非法字符")
    
    # 禁止路径遍历模式
    if '..' in file_path or '~' in file_path:
        raise ValueError("文件路径包含非法模式")
    
    return file_path
```

---

## 🟢 低 (Low)

### 问题 9: 日志中可能记录敏感信息

**规则 ID**: PY-LOG-001  
**位置**: 多处日志记录  
**严重程度**: Low

**问题描述**:
部分日志记录可能包含敏感信息：

```python
logger.info(f'用户 {username} 登录成功')  # 可能记录敏感用户名
```

**修复建议**:
确保日志中不记录密码、API 密钥等敏感信息。当前实现已较好，建议定期审计日志内容。

---

### 问题 10: 缺少 HSTS 头

**规则 ID**: PY-HEADER-001  
**位置**: `web_server.py:1013-1044`  
**严重程度**: Low

**问题描述**:
未配置 HSTS (HTTP Strict Transport Security) 响应头。

**修复建议**:
```python
if _is_production:
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
```

**注意**: HSTS 具有持久性，一旦设置错误可能导致网站无法访问。仅在生产环境且确认使用 HTTPS 时启用。

---

### 问题 11: 前端缺少 SRI (Subresource Integrity)

**规则 ID**: JS-SRI-001  
**位置**: `web/index.html:8-11`  
**严重程度**: Low

**问题描述**:
加载的外部脚本（如 CDN 资源）缺少 integrity 属性：

```html
<!-- 当前配置 -->
<script src="vue.global.js"></script>
<script src="marked.min.js"></script>
<!-- 缺少 integrity 属性 -->
```

**修复建议**:
为所有外部脚本添加 SRI：
```html
<script src="vue.global.js" 
        integrity="sha384-..."
        crossorigin="anonymous"></script>
```

---

## ✅ 已实施的良好安全实践

### 1. 密码安全
- ✅ 使用 PBKDF2 进行密码哈希 (`werkzeug.security.generate_password_hash`)
- ✅ 支持从旧 SHA256 自动迁移到新哈希算法

### 2. 数据库安全
- ✅ 使用参数化查询防止 SQL 注入
- ✅ 实现数据库路由层，带白名单验证
- ✅ 敏感数据脱敏处理

### 3. API 密钥安全
- ✅ 使用 RSA 加密存储 API 密钥
- ✅ 支持密钥轮换
- ✅ 临时 AES 密钥用于传输加密

### 4. 会话安全
- ✅ HttpOnly Cookie
- ✅ SameSite=Lax
- ✅ 会话超时机制
- ✅ 持久化会话密钥

### 5. 认证安全
- ✅ 登录限流 (5分钟5次)
- ✅ 验证码机制
- ✅ CSRF 保护 (X-Requested-With 检查)
- ✅ 角色权限控制

### 6. 响应头安全
- ✅ X-Content-Type-Options: nosniff
- ✅ X-Frame-Options: DENY
- ✅ X-XSS-Protection
- ✅ Referrer-Policy
- ✅ Permissions-Policy

### 7. 前端安全
- ✅ 使用 DOMPurify 净化 HTML
- ✅ 设备 ID 使用 Cookie 存储 (HttpOnly)

---

## 修复优先级建议

| 优先级 | 问题 | 估计工作量 |
|--------|------|-----------|
| P0 | 修复 CSP 配置 | 2小时 |
| P0 | 移除返回密码哈希 | 5分钟 |
| P1 | 修复验证码清除 | 5分钟 |
| P1 | 加强路径验证 | 1小时 |
| P1 | 修复 innerHTML 使用 | 30分钟 |
| P2 | Windows 文件权限 | 1小时 |
| P2 | 移除 localStorage 依赖 | 30分钟 |
| P3 | 添加 HSTS | 10分钟 |
| P3 | 添加 SRI | 1小时 |

---

## 附录：参考文档

- [OWASP Cheat Sheet Series](https://cheatsheetseries.owasp.org/)
- [Flask Security Documentation](https://flask.palletsprojects.com/en/latest/security/)
- [Content Security Policy (CSP)](https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP)
- [OWASP DOM Based XSS Prevention](https://cheatsheetseries.owasp.org/cheatsheets/DOM_based_XSS_Prevention_Cheat_Sheet.html)
