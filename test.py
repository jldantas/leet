

import logging
import sys
import threading
import time
import queue

import leet.backends.cb
import leet.api
import leet.base
import leet.plugins.dir_list

from cbapi.response import Process, CbResponseAPI, Sensor
from cbapi.response.models import Sensor as CB_Sensor

_LEVEL = logging.DEBUG
_MOD_LOGGER = logging.getLogger(__name__)
_MOD_LOGGER.setLevel(_LEVEL)
_log_handler = logging.StreamHandler()
_log_handler.setLevel(_LEVEL)
_log_handler.setFormatter(logging.Formatter("%(asctime)s - %(threadName)s - %(message)s"))
_MOD_LOGGER.addHandler(_log_handler)

_leet_log = logging.getLogger("leet")
_leet_log.addHandler(_log_handler)
_leet_log.setLevel(_LEVEL)

import os

class Test():
    def __init__(self):
        self.path_separator = "\\"

    def exists(self, path):
        return os.path.exists(path)

    def make_dir(self, remote_path, recursive=True):
        """See base class documentation"""
        path_parts = remote_path.split(self.path_separator)

        #if the last split is empty, probably it was passed with trailling
        #separator
        if not path_parts[-1]:
            path_parts = path_parts[:-1]

        #This skips the root of the path
        check = []
        necessary_create = False
        check.append(path_parts.pop(0))

        if recursive:
            for i, part in enumerate(path_parts):
                check.append(part)
                if not self.exists(self.path_separator.join(check)):
                    #the moment we can't find a path, we need to create everything
                    #from there forward
                    necessary_create = True
                    break

            print(i, "check", check)

            if necessary_create:
                check.pop(-1)
                for missing_path in path_parts[i:]:
                    check.append(missing_path)
                    path = self.path_separator.join(check)
                    _MOD_LOGGER.debug("Trying to create path '%s' on the remote host", path)
                    print("building dir", path)
                    #self._execute("make_dir", path)
            else:
                _MOD_LOGGER.debug("No path need to be created.")
        else:
            print("building dir", remote_path)
            #self._execute("make_dir", remote_path)

def main():


    #path = "c:\\Windows\\parte1\\part2\\parte3\\la.txt"
    path = "C:\\maintenance2\\bla.zip"
    #path = "c:\\Windows\\system32\\bla.txt"
    separator = "\\"

    path_parts = path.split(separator)
    t = Test()
    t.make_dir(separator.join(path_parts[:-1]), True)

    #
    # to_create = []
    # for i, parts in enumerate(reversed(path_parts[:-1]), 1):
    #     print("part:", parts)
    #     print("tested path", separator.join(path_parts[:-1*i]))
    #     if not os.path.exists(separator.join(path_parts[:-1*i])):
    #         to_create.append(parts)
    #     else:
    #         break
    #
    # #TODO add if machine is windows?
    # if len(path_parts) == len(to_create):
    #     #TODO exception
    #     print("error")
    #
    # #for part in to_create:
    #
    #
    # print(path_parts)
    # print(to_create)
    # print(i)



# def main():
#     a = leet.plugins.dir_list.LeetPlugin()
#     try:
#
#         print(a.get_help())
#
#         b = a.parse_parameters("--path c:\\google".split(" "))
#         print(b)
#     except SystemExit as e:
#         print(e)

# def main():
#     a = CbResponseAPI(profile="default")
#
#     hostname = "SPEEDYTURTLEW10"
#     query = "hostname:" + hostname
#     sensors = a.select(Sensor).where(query)
#     print(sensors)


# def main():
#     hostnames = ["SPEEDYTURTLEW10"]
#     cb = CbResponseAPI()
#
#     sensor = cb.select(Sensor).where("hostname:"+hostnames[0]).first()
#
#     with sensor.lr_session() as session:
#         print(session.list_processes())
        #print(session.list_directory("c:\\"))

    # a = Test()
    # job = cb.live_response.submit_job(a.run, sensor.id)
    #
    # try:
    #     while True:
    #         time.sleep(20)
    #         sensor.refresh()
    #         print(job, sensor.status)
    # except KeyboardInterrupt:
    #     print("Exiting event loop")
    #

    # with sensor.lr_session() as session:
    #     print(dir(session))



# def main():
#     with leet_backend.cb.CBBackEnd(["all"]) as lt_cb:
#         pass


if __name__ == '__main__':
    main()
