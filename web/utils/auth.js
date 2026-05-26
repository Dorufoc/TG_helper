/**
 * 认证相关工具模块
 * 提供设备ID生成和用户名管理功能
 * SEC-007: deviceId和rememberedUser使用Cookie存储，降低XSS窃取风险
 */

let DEVICE_ID = generateDeviceId();

let CURRENT_USERNAME = null;

function _getCookie(name) {
    const match = document.cookie.match(new RegExp('(?:^|; )' + name.replace(/([.$?*|{}()\[\]\\\/+^])/g, '\\$1') + '=([^;]*)'));
    return match ? decodeURIComponent(match[1]) : null;
}

function _setCookie(name, value, maxAgeDays) {
    let cookie = name + '=' + encodeURIComponent(value) + '; path=/; SameSite=Lax';
    if (location.protocol === 'https:') {
        cookie += '; Secure';
    }
    if (maxAgeDays) {
        cookie += '; max-age=' + (maxAgeDays * 86400);
    }
    document.cookie = cookie;
}

function _deleteCookie(name) {
    document.cookie = name + '=; path=/; SameSite=Lax; max-age=0';
}

function generateDeviceId() {
    let deviceId = _getCookie('deviceId');
    if (!deviceId) {
        deviceId = 'dev-' + crypto.randomUUID();
        _setCookie('deviceId', deviceId, 365);
    }
    return deviceId;
}

function setLoggedInUsername(username) {
    CURRENT_USERNAME = username;
}

function saveRememberedUser(username) {
    _setCookie('rememberedUser', username, 30);
}

function loadRememberedUser() {
    const fromCookie = _getCookie('rememberedUser');
    return fromCookie || '';
}

function clearRememberedUser() {
    _deleteCookie('rememberedUser');
}
