import logging
import sys
import threading
import time

#import leet.cb
#import leet_plugins.dir_list

from cbapi.response import Process, CbResponseAPI, Sensor
from cbapi.response.models import Sensor as CB_Sensor


def wait():
    time.sleep(2)
    sys.stdin.write("ha ha\n")


def main():
    t = threading.Thread(target=wait)
    t.start()
    v = input()
    print(v)


# def main():
#     hostnames = ["US1004511WP"]
#     cb = CbResponseAPI()
#
#     sensor = cb.select(Sensor).where("hostname:"+hostnames[0]).first()
#
#     with sensor.lr_session() as session:
#         print(session.list_directory("c:\\"))

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
