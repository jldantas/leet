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

        return session.list_dir(self.args.path)
