from .models import SearchResult
from .providers_common import score_text


SYSTEM_TOOLS = (
    ("任务管理器", "taskmgr.exe", ("task manager", "工作管理員")),
    ("控制面板", "control.exe", ("control panel",)),
    ("计算器", "calc.exe", ("calculator", "計算機")),
    ("记事本", "notepad.exe", ("notepad", "記事本")),
    ("资源管理器", "explorer.exe", ("file explorer", "explorer", "檔案總管")),
    ("命令提示符", "cmd.exe", ("command prompt", "cmd", "命令列")),
    ("PowerShell", "powershell.exe", ("power shell",)),
    ("画图", "mspaint.exe", ("paint", "小画家")),
    ("运行", "explorer.exe shell:::{2559a1f3-21d7-11d4-bdaf-00c04f60b9f0}", ("run", "執行")),
    ("设备管理器", "devmgmt.msc", ("device manager", "devmgmt", "裝置管理員")),
    ("磁盘管理", "diskmgmt.msc", ("disk management", "diskmgmt", "磁碟管理")),
    ("服务", "services.msc", ("services", "services.msc", "服務")),
    ("注册表编辑器", "regedit.exe", ("registry editor", "regedit", "登錄編輯程式")),
)


class SystemToolsProvider:
    def search(self, query: str, limit: int = 50) -> list[SearchResult]:
        results = []
        for title, command, aliases in SYSTEM_TOOLS:
            score = score_text(query, title, aliases)
            if score:
                results.append(SearchResult("system", title, "系统工具", command, "system", score + 20))
        return sorted(results, key=lambda item: item.score, reverse=True)[:limit]
