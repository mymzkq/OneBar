from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class SearchResult:
    type: str
    title: str
    subtitle: str
    target: str
    icon_key: str | None = None
    score: int = 0

    def to_dict(self) -> dict:
        data = asdict(self)
        if self.type in ("app", "file", "folder"):
            data["path"] = self.target
        elif self.type == "setting":
            data["uri"] = self.target
        elif self.type == "system":
            data["command"] = self.target
        elif self.type == "uwp":
            data["app_id"] = self.target
        return data
