import sys
import os

from leet.base import PluginBase
from leet.errors import LeetPluginError

class LeetPlugin(PluginBase):
    LEET_PG_NAME = "file_download"
    LEET_PG_DESCRIPTION = "Download a single file smaller than 50MB."

    def __init__(self):
        super().__init__()
        self.max_size = 52428800 #50mb

        #TODO add regex support and multiple file download
        self.arg_parser.add_argument("--source", help="Absolute path of the file to be downloaded on the remote endpoint", required=True)
        self.arg_parser.add_argument("--dest", help="Absolute path where the file will be saved. If file name is ommited, it will use the file from source. The machine name will also be added", required=True)

    def _split_remote_path(self):
        if "\\" in self.args.source:
            sep = "\\"
        else:
            sep = "/"

        return self.args.source.rsplit(sep, 1)

    def _check_remote_file_size(self, session, path, file):
        dir_list = session.list_dir(path)
        size = sys.maxsize

        for entry in dir_list:
            if entry["name"] == file:
                size = entry["size"]
                break

        if size <= self.max_size:
            return True
        else:
            return False

    def _fix_local_path(self, hostname, r_filename):
        """Fix the local path before saving.

        Basically, what happens is, if the local path is a directory, it will get
        the remote filename and add that and will also prepend the machine name
        to the file, to guarantee uniqueness.
        """
        if not os.path.exists(self.args.dest):
            raise LeetPluginError("The local path does not exists.")

        if os.path.isdir(self.args.dest):
            l_path = self.args.dest
            l_filename = "_".join([hostname, r_filename])
        else:
            l_path, l_filename = os.path.split(self.args.dest)
            l_filename = "_".join([hostname, l_filename])

        if not os.path.exists(l_path):
            try:
                os.makedirs(l_path)
            except PermissionError as e:
                raise LeetPluginError(str(e)) from e
        #dest_path = os.path.join(l_path, l_filename)

        return os.path.join(l_path, l_filename)

    def run(self, session, machine_info):
        data = []

        r_path, r_filename = self._split_remote_path()
        dest_path = self._fix_local_path(machine_info.hostname, r_filename)

        if session.exists(self.args.source):
            #if file is bigger than max, stop it.
            if not self._check_remote_file_size(session, r_path, r_filename):
                raise LeetPluginError("File size is bigger than the allowed.")
            #download the file
            with open(dest_path, "wb") as output:
                output.write(session.get_file(self.args.source))
            data.append({"src" : self.args.source,
                         "dst" : dest_path,
                         "status": "ok"})
        else:
            raise LeetPlugin(f"Could not download {self.args.source}. File not found")
            data.append({"hostname" : machine_info.hostname,
                         "status": "failed. File not found."})

        return data
