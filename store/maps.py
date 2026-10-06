from html.parser import HTMLParser


class _IframeSourceParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.source = ""

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "iframe" and not self.source:
            self.source = dict(attrs).get("src", "")


def extract_map_source(value):
    """Return a plain map URL or the iframe source from a pasted embed snippet."""
    content = (value or "").strip()
    if not content:
        return ""
    if "<" not in content:
        return content
    parser = _IframeSourceParser()
    parser.feed(content)
    parser.close()
    return parser.source.strip()