from i18n import tr


class WebSuggestionsProvider:
    def suggestions(self, language: str, query: str, limit: int = 5) -> list[dict]:
        text = query.strip()
        if not text:
            return []
        keys = (
            "web_suggestion_more",
            "web_suggestion_download",
            "web_suggestion_tutorial",
            "web_suggestion_official",
            "web_suggestion_how_open",
        )
        return [
            {"title": tr(language, key).format(query=text), "query": tr(language, key).format(query=text)}
            for key in keys
        ][:limit]
