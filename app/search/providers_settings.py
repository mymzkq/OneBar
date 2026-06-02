from .models import SearchResult
from .providers_common import score_text


SETTINGS_ITEMS = (
    ("设置", "Windows 设置", "ms-settings:", ("settings", "設定")),
    ("系统", "显示、声音、电源、存储", "ms-settings:system", ("system", "系統")),
    ("显示", "屏幕、缩放、亮度", "ms-settings:display", ("display", "顯示", "screen")),
    ("声音", "音量、输入输出设备", "ms-settings:sound", ("sound", "音效", "volume", "audio")),
    ("网络", "Wi-Fi、以太网、代理", "ms-settings:network", ("network", "網路", "wifi", "wi-fi", "proxy")),
    ("蓝牙", "蓝牙和设备", "ms-settings:bluetooth", ("bluetooth", "藍牙")),
    ("设备", "蓝牙、鼠标、键盘、打印机", "ms-settings:bluetooth", ("devices", "device", "設備", "设备", "mouse", "keyboard", "printer")),
    ("应用", "已安装应用、默认应用", "ms-settings:appsfeatures", ("apps", "app", "應用程式")),
    ("默认应用", "默认浏览器、文件关联", "ms-settings:defaultapps", ("default apps", "default app", "預設應用程式")),
    ("个性化", "主题、颜色、任务栏", "ms-settings:personalization", ("personalization", "個人化", "theme", "color")),
    ("任务栏", "任务栏设置", "ms-settings:taskbar", ("taskbar", "工作列")),
    ("Windows 更新", "系统更新", "ms-settings:windowsupdate", ("windows update", "update", "更新", "系統更新")),
    ("存储", "磁盘空间、清理建议", "ms-settings:storagesense", ("storage", "儲存", "disk")),
    ("隐私", "权限、麦克风、摄像头", "ms-settings:privacy", ("privacy", "隱私", "permission", "permissions")),
    ("电源", "电源和电池", "ms-settings:powersleep", ("power", "battery", "sleep", "電源", "電池")),
    ("账户", "账户、登录选项", "ms-settings:accounts", ("accounts", "account", "登入", "登录")),
)


class SettingsProvider:
    def search(self, query: str, limit: int = 50) -> list[SearchResult]:
        results = []
        for title, subtitle, uri, aliases in SETTINGS_ITEMS:
            score = score_text(query, title, aliases + (subtitle,))
            if score:
                results.append(SearchResult("setting", title, subtitle, uri, "setting", score + 30))
        return sorted(results, key=lambda item: item.score, reverse=True)[:limit]
