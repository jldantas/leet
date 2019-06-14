# -*- coding: utf-8 -*-

import logging
import queue
import enum
import datetime


from cbapi.response import Process, CbResponseAPI, Sensor
import cbapi.errors

from ..base import LeetBackend, LeetMachine, LeetSOType, LeetSession
from ..errors import LeetSessionError, LeetPluginError, LeetCommandError


_MOD_LOGGER = logging.getLogger(__name__)

class CBMachine(LeetMachine):
    def __init__(self, hostname, backend_name, sensor):
        super().__init__(hostname, backend_name)
        self.sensor = sensor

        if self.sensor.os_type == 1:
            self.so_type = LeetSOType.WINDOWS

    def refresh(self):
        self.sensor.refresh()
        if self.sensor.status == "Online":
            self.can_connect = True
        else:
            self.can_connect = False

    def connect(self):
        try:
            return CBSession(self.sensor.lr_session(), self)
        except cbapi.errors.TimeoutError as e:
            raise LeetSessionError("Timed out when requesting a session to cbapi") from e
        return CBSession(self.sensor.lr_session(), self)

class CBSession(LeetSession):
    #TODO test what error is raised if session is interrupted in the middle
    def __init__(self, lr_session, machine_info):
        super().__init__(lr_session, machine_info)

        self._mapping_table = {
            "list_processes" : self.raw_session.list_processes,
            "get_file" : self.raw_session.get_file,
            "put_file" : self.raw_session.put_file,
            "delete_file" : self.raw_session.delete_file,
            "start_process" : self.raw_session.create_process}

    def start_process(self, cmd_string, cwd=None, background=False):
        return self._execute("start_process", cmd_string, not background, None, cwd, 600, not background)

    def delete_file(self, remote_file_path):
        self._execute("delete_file", remote_file_path)

    def put_file(self, fp, remote_file_path, overwrite=False):
        if self.exists(remote_file_path) and overwrite:
            self._execute("delete_file", remote_file_path)

        try:
            self._execute("put_file", fp, remote_file_path)
        except cbapi.live_response_api.LiveResponseError as e:
            raise LeetCommandError(str(e)) from e

    def exists(self, remote_file_path):
        split = remote_file_path.split(self.path_separator)
        file_name = split[-1]
        path = self.path_separator.join(split[:-1]) + self.path_separator

        try:
            list_dir = self.raw_session.list_directory(path)
        except cbapi.live_response_api.LiveResponseError as e:
            return False

        if [a for a in list_dir if a["filename"] == file_name]:
            return True
        else:
            return False


    def get_file(self, remote_file_path):
        #TODO check if the file exist first?
        return self._execute("get_file", remote_file_path)

    def _execute(self, *args):
        #TODO should live response errors be mapped to plugin errors?
        _MOD_LOGGER.debug("Executing on session: %s", args)
        try:
            if len(args) == 1:
                return self._mapping_table[args[0]]()
            else:
                return self._mapping_table[args[0]](*args[1:])
        #TODO it can also raise ApiError on 404 to server?
        except cbapi.errors.TimeoutError as e:
            raise LeetSessionError("Timed out when requesting a session to cbapi") from e
        except cbapi.live_response_api.LiveResponseError as e:
            raise LeetCommandError(str(e)) from e
            #raise LeetPluginError(str(e)) from e
        # except KeyError as e:
        #     raise LeetSessionError("Unknown function.", True) from e

    def list_processes(self):
        """Returns the list of currently active processes"""
        processes = []

        process_list = self._execute("list_processes")

        for process in process_list:
            processes.append({"username": process["username"],
                              "pid": process["pid"],
                              "ppid": process["parent"],
                              "start_time": datetime.datetime.utcfromtimestamp(process["create_time"]),
                              "command_line": process["command_line"].split(self.path_separator)[-1],
                              "path": process["path"],
                              })

        return processes

    def __enter__(self):
        """Enter context"""
        return self

    def __exit__(self, exeception_type, exception_value, traceback):
        """Exit context"""
        self.raw_session.close()

#             VAR = EXPR
# VAR.__enter__()
# try:
#     BLOCK
# finally:
#     VAR.__exit__()


class Backend(LeetBackend):
    def __init__(self, profile_name):
        super().__init__("CB-" + profile_name, 10) #TODO move max_session to a configuration/variable
        self._profile_name = profile_name
        self._cb = None

    @property
    def url(self):
        """The Carbon Black server URL"""
        return self._cb.url

    def start(self):
        super().start()
        self._cb = CbResponseAPI(profile=self._profile_name)

        return self

    def _get_sensor(self, hostname):
        """Return the sensor related to the hostname. If more than one sensor
        is found, it will return the one that did the most recent check-in.

        Args:
            hostname (str): The machine name

        Returns:
            [Sensor]: The list of sensors
        """
        recent_sensor = None
        query = "hostname:" + hostname
        sensors = self._cb.select(Sensor).where(query)

        for sensor in sensors:
            if recent_sensor is None:
                recent_sensor = sensor
            else:
                if sensor.last_checkin_time > recent_sensor.sensor.last_checkin_time:
                    recent_sensor = sensor

        return recent_sensor

    def _search_machines(self, search_request):
        machine_list = []

        for hostname in search_request.hostnames:
            sensor = self._get_sensor(hostname)
            if sensor is not None:
                machine_list.append(CBMachine(hostname, self.backend_name, sensor))

        return machine_list
