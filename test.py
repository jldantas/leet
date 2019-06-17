

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

def main():
    a = leet.plugins.dir_list.LeetPlugin()
    try:

        print(a.get_help())

        b = a.parse_parameters("--path c:\\google".split(" "))
        print(b)
    except SystemExit as e:
        print(e)

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
