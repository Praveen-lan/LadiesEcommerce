class OrderIdConverter:
    """Matches order IDs that may contain slashes, e.g. 2026/10/05-4821."""

    regex = r"[-\w]+(?:/[-\w]+)*"

    def to_python(self, value):
        return value

    def to_url(self, value):
        return str(value)