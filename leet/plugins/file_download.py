#from datetime import datetime as _datetime
#import io
import os

from leet.base import PluginBase


class LeetPlugin(PluginBase):
    LEET_PG_NAME = "file_download"
    LEET_PG_DESCRIPTION = "Download a single file."

    def __init__(self):
        super().__init__()

        self.arg_parser.add_argument("--source", help="Absolute path of the file to be downloaded on the remote endpoint", required=True)
        self.arg_parser.add_argument("--dest", help="Absolute path where the file will be saved. If file name is ommited, it will use the file from source. The machine name will also be added", required=True)

    def _split_remote_path(self):
        if "\\" in self.args.source:
            sep = "\\"
        else:
            sep = "/"

        return self.args.source.rsplit(sep, 1)

    def run(self, session, machine_info):
        data = []

        #in case the destination file name is missing, lets fix it
        if os.path.isdir(self.args.dest):
            r_path, r_filename = self._split_remote_path()
            l_path = self.args.dest
            l_filename = "_".join([machine_info.hostname, r_filename])
        else:
            l_path, l_filename = os.path.split(self.args.dest)
            l_filename = "_".join([machine_info.hostname, l_filename])
        dest_path = os.path.join(l_path, l_filename)

        if session.exists(self.args.source):
            with open(dest_path, "wb") as output:
                output.write(session.get_file(self.args.source))

            data.append({"hostname" : machine_info.hostname,
                         "status": "ok"})
        else:
            data.append({"hostname" : machine_info.hostname,
                         "status": "failed. File not found."})

        return data
