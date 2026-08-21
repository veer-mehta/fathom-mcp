import json
import sys


class JsonlStdoutPipeline:
    def process_item(self, item):
        sys.stdout.write(json.dumps(item, ensure_ascii=False) + "\n")
        sys.stdout.flush()
        return item
