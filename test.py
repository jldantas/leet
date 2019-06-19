

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

def make_dir(remote_path, recursive=True):
    separator = "\\"

    path_parts = remote_path.split(separator)

    #This skips the root of the path
    check = []
    check.append(path_parts.pop(0))

    if recursive:
        for i, part in enumerate(path_parts):
            check.append(part)
            print("check", check)
            if not os.path.exists(separator.join(check)):
                #the moment we can't find a path, we need to create everything
                #from there forward
                break
        print(i, len(path_parts))
        if i + 1 == len(path_parts):
            print("nothing to do")
        else:
            print("do something")
        check.pop(-1)
        for missing_path in path_parts[i:]:
            check.append(missing_path)
            print("build", separator.join(check))
    else:
        print("build all", remote_path)

def main():


    #path = "c:\\Windows\\parte1\\part2\\parte3\\la.txt"
    path = "c:\\Windows\\bla.txt"
    path = "c:\\Windows\\system32\\bla.txt"
    separator = "\\"

    path_parts = path.split(separator)


    make_dir(separator.join(path_parts[:-1]), True)
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
