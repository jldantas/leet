# -*- coding: utf-8 -*-
"""Implements the Carbon Black Response, using Live Response backend.

This module contains the three necessary classes to implement the CB backend:

- CBMachine -> Represents a machine to CB
- CBSession -> Represents a LR session
- Backend -> The main entry point for the backend

"""
import logging
import datetime

from cbapi.response import CbResponseAPI, Sensor
import cbapi.errors

from ..base import LeetBackend, LeetMachine, LeetSOType, LeetSession
from ..errors import LeetSessionError, LeetCommandError

_MOD_LOGGER = logging.getLogger(__name__)

class CBMachine(LeetMachine):
    """A LeetMachine implementation for the CB Backend.

    Attributes:
        sensor (cbapi.response.Sensor): A sensor as seen by the CB API.
        can_connect (bool): If the machine is available to be connected.
    """
    def __init__(self, hostname, backend_name, sensor):
        """Creates a new CBMachine object.

        Args:
            hostname (str): The hostname of the machine
            backend_name (str): The unique name for the backend
            sensor (cbapi.response.Sensor): The sensor object that represents
                a machine in CB
        """
        super().__init__(hostname, backend_name)
        self.sensor = sensor

        if self.sensor.os_type == 1:
            self.so_type = LeetSOType.WINDOWS

    @property
    def can_connect(self):
        """If the machine is available to be connected."""
        return True if self.sensor.status == "Online" else False

    def refresh(self):
        """See base class documentation"""
        self.sensor.refresh()

    def connect(self):
        """See base class documentation"""
        try:
            return CBSession(self.sensor.lr_session(), self)
        except cbapi.errors.TimeoutError as e:
            raise LeetSessionError("Timed out when requesting a session to cbapi") from e
        return CBSession(self.sensor.lr_session(), self)

class CBSession(LeetSession):
    """Represents a new session using the CB backend.

    This basically wraps a live response session into a leet session, allowing
    decoupling of the plugin and the backend. It handles all the necessary
    code provide what is defined in the base class and makes sure any errors
    raised are correctly coverted to the respective Leet errors.
    """
    #TODO test what error is raised if session is interrupted in the middle
    def __init__(self, lr_session, machine_info):
        """Returns a CBSession object.

        Args:
            lr_session (cbapi.live_response_api.LiveResponse): A live response
                session
            machine_info (CBMachine): A machine info object
        """
        super().__init__(lr_session, machine_info)

        self._mapping_table = {
            "list_processes" : self.raw_session.list_processes,
            "get_file" : self.raw_session.get_file,
            "put_file" : self.raw_session.put_file,
            "delete_file" : self.raw_session.delete_file,
            "start_process" : self.raw_session.create_process}

    def start_process(self, cmd_string, cwd=None, background=False):
        """See base class documentation"""
        return self._execute("start_process", cmd_string, not background, None, cwd, 600, not background)

    def delete_file(self, remote_file_path):
        """See base class documentation"""
        self._execute("delete_file", remote_file_path)

    def put_file(self, fp, remote_file_path, overwrite=False):
        """See base class documentation"""
        if self.exists(remote_file_path) and overwrite:
            self._execute("delete_file", remote_file_path)

        try:
            self._execute("put_file", fp, remote_file_path)
        except cbapi.live_response_api.LiveResponseError as e:
            raise LeetCommandError(str(e)) from e

    def exists(self, remote_file_path):
        """See base class documentation"""
        split = remote_file_path.split(self.path_separator)
        file_name = split[-1]
        path = self.path_separator.join(split[:-1]) + self.path_separator

        try:
            list_dir = self.raw_session.list_directory(path)
        except cbapi.live_response_api.LiveResponseError as e:
            return False

        return bool([a for a in list_dir if a["filename"] == file_name])
        # if [a for a in list_dir if a["filename"] == file_name]:
        #     return True
        # else:
        #     return False

    def get_file(self, remote_file_path):
        """See base class documentation"""
        #TODO check if the file exist first?
        return self._execute("get_file", remote_file_path)

    def _execute(self, *args):
        """See base class documentation"""
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
        """See base class documentation"""
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

class Backend(LeetBackend):
    """Implements the CB backend communication.

    This class starts the connection to the backend server and enables direct
    interaction with it.
    """
    def __init__(self, profile_name):
        """Returns a Backend object.

        Args:
            profile_name (str): The profile name that this class will connect,
                as seen in the 'credentials.response' file.
        """
        super().__init__("CB-" + profile_name, 10) #TODO move max_session to a configuration/variable
        self._profile_name = profile_name
        self._cb = None

    @property
    def url(self):
        """The Carbon Black server URL"""
        return self._cb.url

    def start(self):
        """Starts the internal thread (see base class documentation) and
        start the connection to the CB server.
        """
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
        """See base class documentation"""
        machine_list = []

        for hostname in search_request.hostnames:
            sensor = self._get_sensor(hostname)
            if sensor is not None:
                machine_list.append(CBMachine(hostname, self.backend_name, sensor))

        return machine_list
