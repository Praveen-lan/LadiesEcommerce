from html import escape
from html.parser import HTMLParser
import re


ALLOWED_TERMS_TAGS = {
    "b",
    "blockquote",
    "br",
    "div",
    "em",
    "h2",
    "h3",
    "h4",
    "hr",
    "i",
    "li",
    "ol",
    "p",
    "s",
    "strong",
    "sub",
    "sup",
    "strike",
    "u",
    "ul",
}
VOID_TERMS_TAGS = {"br", "hr"}


class _TermsHTMLSanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.open_tags = []
        self.blocked_tags = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.blocked_tags.append(tag)
            return
        if self.blocked_tags:
            return
        if tag not in ALLOWED_TERMS_TAGS:
            return
        alignment = ""
        if tag in {"div", "p"}:
            style = dict(attrs).get("style", "")
            match = re.fullmatch(r"\s*text-align\s*:\s*(left|center|right|justify)\s*;?\s*", style, re.I)
            if match:
                alignment = f' style="text-align: {match.group(1).lower()}"'
        self.parts.append(f"<{tag}{alignment}>")
        if tag not in VOID_TERMS_TAGS:
            self.open_tags.append(tag)

    def handle_startendtag(self, tag, attrs):
        if tag in ALLOWED_TERMS_TAGS:
            self.parts.append(f"<{tag}>" if tag in VOID_TERMS_TAGS else f"<{tag}></{tag}>")

    def handle_endtag(self, tag):
        if self.blocked_tags:
            if tag == self.blocked_tags[-1]:
                self.blocked_tags.pop()
            return
        if tag not in self.open_tags:
            return
        while self.open_tags:
            open_tag = self.open_tags.pop()
            self.parts.append(f"</{open_tag}>")
            if open_tag == tag:
                break

    def handle_data(self, data):
        if self.blocked_tags:
            return
        self.parts.append(escape(data, quote=False).replace("\n", "<br>"))

    def finish(self):
        while self.open_tags:
            self.parts.append(f"</{self.open_tags.pop()}>")
        return "".join(self.parts)


def sanitize_terms_html(value):
    parser = _TermsHTMLSanitizer()
    parser.feed(value or "")
    parser.close()
    return parser.finish()
