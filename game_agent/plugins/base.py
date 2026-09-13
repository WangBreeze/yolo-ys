class Plugin:
    API_VERSION = 1
    VERSION = "1.0.0"

    def __init__(self, context, options):
        self.context = context
        self.options = options

    def close(self):
        pass
