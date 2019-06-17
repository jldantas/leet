from datetime import datetime as _datetime

from leet.base import PluginBase, LeetPluginParser


class LeetPlugin(PluginBase):
    LEET_PG_NAME = "dirlist"
    LEET_PG_DESCRIPTION = "Returns a directory list from a path with STD timestamp data."

    def __init__(self):
        super().__init__()
        self.arg_parser.add_argument("--path", help="Path to be listed on the remote endpoint", required=True)

    def run(self, session, machine_info):
        data = []

        #result.headers = ["Access ts", "Write ts", "Created ts", "Filename", "Size", "Attributes"]
        temp_data = session.list_directory(self.args.path)
        for item in temp_data:
            data_processed = {"Access ts" : _datetime.utcfromtimestamp(item["last_access_time"]),
                                "Write ts" : _datetime.utcfromtimestamp(item["last_write_time"]),
                                "Created ts" : _datetime.utcfromtimestamp(item["create_time"]),
                                "Filename" : item["filename"],
                                "Attributes" : "|".join(item["attributes"]),
                                "Size" : item["size"]}
            data.append(data_processed)


        return data

# Sample return of a CB dirlist
# {'last_access_time': 1458169329, 'last_write_time': 1458169329, 'filename': '$Recycle.Bin', 'create_time': 1247541536, 'attributes': ['HIDDEN', 'SYSTEM', 'DIRECTORY'], 'size': 0},
# {'last_access_time': 1515105722, 'last_write_time': 1515105722, 'filename': 'Boot', 'create_time': 1449789900, 'attributes': ['HIDDEN', 'SYSTEM', 'DIRECTORY'], 'size': 0},
# {'last_access_time': 1515105722, 'last_write_time': 1290309831, 'filename': 'bootmgr', 'create_time': 1449789900, 'attributes': ['READONLY', 'HIDDEN', 'SYSTEM', 'ARCHIVE'], 'size': 383786},
# {'last_access_time': 1247548136, 'last_write_time': 1247548136, 'filename': 'Documents and Settings', 'create_time': 1247548136, 'alt_name': 'DOCUME~1', 'attributes': ['HIDDEN', 'SYSTEM', 'DIRECTORY', 'REPARSE_POINT', 'NOT_CONTENT_INDEXED'], 'size': 0}
