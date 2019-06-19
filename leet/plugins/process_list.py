from datetime import datetime as _datetime
import io

from leet.base import PluginBase


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

        with io.BytesIO(b"I dont like this song. I'm out") as f:
            session.put_file(f, "c:\\created\\folder\\structuture\\nah.txt", True)


        return data
