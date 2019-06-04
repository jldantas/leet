import logging
import sys

#import leet.cb
import leet_plugins.dir_list

from cbapi.response import Process, CbResponseAPI, Sensor
from cbapi.response.models import Sensor as CB_Sensor

#logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

class A():
    #V1 = None

    def f1(self):
        print(self.V1)

class B(A):
    V1 = "B"

    def __init__(self):
        super().__init__()


def main():
    b = B()
    b.f1()



# def main():
#     a = Test()
#     b = Test1()
#     c = Test2()
#
#     print(a.A, b.A, c.A)


# class Test():
#     def run(self, session):
#         return session.list_directory("c:\\")
#
#
#
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
