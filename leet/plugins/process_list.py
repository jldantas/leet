from datetime import datetime as _datetime
import io

from leet.base import PluginBase,  LeetPluginParameter


class LeetPlugin(PluginBase):
    LEET_PG_NAME = "process_list"
    LEET_PG_DESCRIPTION = "Returns a list of processes currently in execution."


    def __init__(self):
        super().__init__()
        #self.reg_param(LeetPluginParameter("path", "Path to be listed on the remote endpoint", True))


    def run(self, session, machine_info):


        data = session.list_processes()
        print(session.get_file("c:\\song.txt"))

        print(session.start_process("cmd /c hostname"))

        # with io.BytesIO(b"I dont like this song. I'm out") as f:
        #     session.put_file(f, "c:\\nah.txt", True)


        return data

# Sample return of a CB dirlist
# {'last_access_time': 1458169329, 'last_write_time': 1458169329, 'filename': '$Recycle.Bin', 'create_time': 1247541536, 'attributes': ['HIDDEN', 'SYSTEM', 'DIRECTORY'], 'size': 0},
# {'last_access_time': 1515105722, 'last_write_time': 1515105722, 'filename': 'Boot', 'create_time': 1449789900, 'attributes': ['HIDDEN', 'SYSTEM', 'DIRECTORY'], 'size': 0},
# {'last_access_time': 1515105722, 'last_write_time': 1290309831, 'filename': 'bootmgr', 'create_time': 1449789900, 'attributes': ['READONLY', 'HIDDEN', 'SYSTEM', 'ARCHIVE'], 'size': 383786},
# {'last_access_time': 1247548136, 'last_write_time': 1247548136, 'filename': 'Documents and Settings', 'create_time': 1247548136, 'alt_name': 'DOCUME~1', 'attributes': ['HIDDEN', 'SYSTEM', 'DIRECTORY', 'REPARSE_POINT', 'NOT_CONTENT_INDEXED'], 'size': 0}
