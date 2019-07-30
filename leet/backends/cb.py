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

from ..base import LeetBackend, LeetMachine, LeetSOType, LeetSession, LeetFileAttributes
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
        except cbapi.errors.ObjectNotFoundError as e:
            raise LeetSessionError("Max limit of sessions opened") from e
        #return CBSession(self.sensor.lr_session(), self)

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
            "start_process" : self.raw_session.create_process,
            "make_dir" : self.raw_session.create_directory,
            "dir_list" : self.raw_session.list_directory
            }

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

        remote_path = self.path_separator.join(remote_file_path.split(self.path_separator)[:-1])
        if not self.exists(remote_path):
            self.make_dir(remote_path)

        self._execute("put_file", fp, remote_file_path)

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
            if necessary_create:
                check.pop(-1)
                for missing_path in path_parts[i:]:
                    check.append(missing_path)
                    path = self.path_separator.join(check)
                    _MOD_LOGGER.debug("Trying to create path '%s' on the remote host", path)
                    self._execute("make_dir", path)
            else:
                _MOD_LOGGER.debug("No path need to be created.")
        else:
            self._execute("make_dir", remote_path)

    def exists(self, remote_file_path):
        """See base class documentation"""
        if remote_file_path[-1] == self.path_separator:
            idx = -2
        else:
            idx = -1
        split_path = remote_file_path.split(self.path_separator)
        #passing a root path (c:, d:, /, etc) is a logic error and raises an
        #exception
        if len(split_path) == 1:
            raise LeetCommandError("Can't verify existence of root paths.")
        file_name = split_path[idx]
        path = self.path_separator.join(split_path[:idx]) + self.path_separator

        try:
            list_dir = self._execute("dir_list", path)
            #list_dir = self.raw_session.list_directory(path)
        except LeetCommandError as e:
        # except cbapi.live_response_api.LiveResponseError as e:
            return False

        return bool([a for a in list_dir if a["filename"] == file_name])

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

    def _parse_file_attributes(self, attributes):
        attr = []
        attr_list = set(attributes)

        if "HIDDEN" in attr_list:
            attr.append(LeetFileAttributes.HIDDEN)
        if "DIRECTORY" in attr_list:
            attr.append(LeetFileAttributes.DIRECTORY)
        if "SYSTEM" in attr_list:
            attr.append(LeetFileAttributes.SYSTEM)

        return attr

    def list_dir(self, remote_path):
        """See base class documentation"""
        # Sample return of a CB dirlist
        # {'last_access_time': 1458169329, 'last_write_time': 1458169329, 'filename': '$Recycle.Bin', 'create_time': 1247541536, 'attributes': ['HIDDEN', 'SYSTEM', 'DIRECTORY'], 'size': 0},
        # {'last_access_time': 1515105722, 'last_write_time': 1515105722, 'filename': 'Boot', 'create_time': 1449789900, 'attributes': ['HIDDEN', 'SYSTEM', 'DIRECTORY'], 'size': 0},
        # {'last_access_time': 1515105722, 'last_write_time': 1290309831, 'filename': 'bootmgr', 'create_time': 1449789900, 'attributes': ['READONLY', 'HIDDEN', 'SYSTEM', 'ARCHIVE'], 'size': 383786},
        # {'last_access_time': 1247548136, 'last_write_time': 1247548136, 'filename': 'Documents and Settings', 'create_time': 1247548136, 'alt_name': 'DOCUME~1', 'attributes': ['HIDDEN', 'SYSTEM', 'DIRECTORY', 'REPARSE_POINT', 'NOT_CONTENT_INDEXED'], 'size': 0}
        list_dir = []
        cb_list_dir = self._execute("dir_list", remote_path)
        if len(cb_list_dir) == 1 and "DIRECTORY" in cb_list_dir[0]["attributes"]:
            cb_list_dir = self._execute("dir_list", remote_path + self.path_separator)

        for entry in cb_list_dir:
            data = {"name": entry["filename"],
                    "size": entry["size"],
                    "attributes": self._parse_file_attributes(entry["attributes"]),
                    "create_time": datetime.datetime.utcfromtimestamp(entry["create_time"]),
                    "modification_time": datetime.datetime.utcfromtimestamp(entry["last_write_time"]),
                    }
            list_dir.append(data)

        return list_dir

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
        super().__init__("CB-" + profile_name, 7) #TODO move max_session to a configuration/variable
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
                if sensor.last_checkin_time > recent_sensor.last_checkin_time:
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
