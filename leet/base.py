# -*- coding: utf-8 -*-
import uuid
import enum
import abc
import threading
import queue
import datetime
import logging
import argparse

_MOD_LOGGER = logging.getLogger(__name__)

from .errors import LeetPluginError, LeetError

class LeetJobStatus(enum.Enum):
    '''Flags the status of an individual job.

    How are the states supposed to flow:
    PENDING -> EXECUTING, CANCELLED, ERROR
    EXECUTING -> COMPLETED, CANCELLED, ERROR, PENDING

    There might be a situation where a job has been cancelled, but it is already
    on it's way, as such, we can also have:
    CANCELLED -> COMPLETED
    '''
    #TODO one more status related to pending_cancellation?
    PENDING = 0x0
    EXECUTING = 0x1
    COMPLETED = 0x2
    CANCELLED = 0x3
    ERROR = 0x4

class LeetSOType(enum.Enum):
    """Defines the types of SO in a standard way."""
    WINDOWS = 0x1
    LINUX = 0x2
    MAC = 0x3
    UNKNOWN = 0X10

class LeetMachine(metaclass=abc.ABCMeta):
    """Represents a machine with the relevant information and how to
    interact in the scope of the LEET.

    This class is one of the classes that HAS to be overloaded when writing a
    backend.

    Attributes:
        hostname (str): The machine hostname
        can_connect (bool): If True, LEET will try to connect to the machine if
            there is a job scheduled
        drive_list (list of str): A list of drives for the machine
        so_type (LeetSOType): The type of SO of the machine
        backend_name (str): The name of the backend where the machine was found.
    """

    def __init__(self, hostname, backend_name):
        """Returns a LeetMachine object.

        Args:
            hostname (str): hostname of the machine
            backend_name (str): Name of the backend the machine can be found
        """
        self.hostname = hostname
        self.so_type = LeetSOType.UNKNOWN
        self.drive_list = None
        self.backend_name = backend_name

    @property
    @abc.abstractmethod
    def can_connect(self):
        """A flag that shows if the machine can receive a connection. It should
        be updated automatically or when the refresh method is called."""

    @abc.abstractmethod
    def refresh(self):
        """Refresh the status of the machine and updates can_connect attribute"""

    @abc.abstractmethod
    def connect(self):
        """Starts the session with the machine, it has to return a LeetSession subclass

        Returns:
            (LeetSession*): A subclass of LeetSession
        """

    def __repr__(self):
        'Return a nicely formatted representation string'
        return (f'{self.__class__.__name__}(hostname={self.hostname}, '
                f'can_connect={self.can_connect}, so_type={self.so_type}, '
                f'drive_list={self.drive_list})'
               )

class LeetSession(metaclass=abc.ABCMeta):
    """An abstraction of a session, allowing the decoupling of the backend and
    the plugin. This is class is (or subclasses) are passed to plugins where
    it will be used to interact with the machine.

    Note:
        Any implementation of this class can raise only two errors aside from the
        standard python errors: 'LeetSessionError' and 'LeetCommandError'. This
        allows the plugins to handle only those, simplyfing plugin design.

    Warning:
        The 'raw_session' attribute can be used by any plugin, but it becomes
        responsibility of the plugin to check if the class is of the right
        type and correclty handle and/or raise the necessary errors.

    Attributes:
        raw_session (?): The raw session created by the backend, this depends
            completely on the backend in use.
        path_separator (str): Tells what is the path separator based on the
            remote machine type

    """
    def __init__(self, session, machine_info):
        """Returns an object of LeetSession"""
        self.raw_session = session

        if machine_info.so_type == LeetSOType.WINDOWS:
            self.path_separator = "\\"
        #TODO in case of unknow, should we throw an error?
        else:
            self.path_separator = "/"

    @abc.abstractmethod
    def list_processes(self):
        """Returns a list of processes currently executing on the machine.

        Returns:
            (list of dicts): A list of dicts where each entry on the list represents
                a process and each dictionary MUST have the following format:
                {"username" (str): Username the process is executing,
                 "pid" (int): The process ID,
                 "ppid" (int): The parent process ID,
                 "start_time" (datetime): The date and time, in UTC, that the process started,
                 "command_line" (str): The commandline used to start the process,
                 "path" (str): The path of the executable}

            For example:
            [{"username": "NT AUTHORITY\\SYSTEM",
            "ppid": 644,
            "pid": 856,
            "command_line": 'svchost.exe -k dcomlaunch -p -s PlugPlay',
            "start_time": datetime.datetime(2019-05-01 13:00:00),
            "path": "c:\\windows\\system32\\svchost.exe",
            }]
        """

    @abc.abstractmethod
    def get_file(self, remote_file_path):
        """Returns the contents of a remote file. The file will be completed
        loaded in memory. There is NO guarantee it will work for locked files.

        This request must block until the whole file has been read.

        Args:
            remove_file_path (str): The absolute path on the remote machine.
            timeout (int): In seconds

        Returns:
            (binary content): The contents of the file, as binary stream
        """
        #TODO should we require the session backend returns any file, including locked ones?

    @abc.abstractmethod
    def put_file(self, fp, remote_file_path, overwrite):
        """Transfer a file to the remote machine.

        If the destination path does not exists, the backend implemenation MUST
        create it, unless the disk doesn't exists.

        Args:
            fp (file like object): A file like object with the data opened as
                binary
            remote_file_path (str): Absolute path where the file will be saved
            overwrite (bool): If the it is True, it will overwrite the file.

        Returns:
            None

        Raises:
            (LeetCommandError): If the file exists and the overwrite is set to False,
                or the path does not exists.
        """

    @abc.abstractmethod
    def delete_file(self, remote_file_path):
        """Delete a file or directory from the remote machine.

        If the a folder is passed to `remote_file_path`, it will recursively
        delete all its contents.

        Args:
            remote_file_path (str): File path of the file to be deleted.

        Returns:
            None

        Raises:
            (LeetCommandError): If the file doesn't exists, if the file is locked
                by the OS.
        """

    @abc.abstractmethod
    def make_dir(remote_path, recursive=True):
        """Creates a directory on the remote machine. This function WILL NOT
        check for root path and providing a path like "c:" or "/" is a violation.

        Args:
            remote_path (str): The remote path that will be created, WITHOUT the
                filename
            recursive (bool): If this flag is true, it will create all necessary
                subdirectories in the path
        """

    @abc.abstractmethod
    def exists(self, remote_file_path):
        """Checks if a path or file exist.

        Note:
            This method HAS to correctly handle files and directories!

        Args:
            remote_file_path (str): File path to be checked.

        Returns:
            (bool): True if it exists, False otherwise
        """

    @abc.abstractmethod
    def start_process(self, cmd_string, cwd="", background=False):
        """

        Returns:
            (str): If the command is not executed on the background,
                returns the command output as a string
            (None): If the the process is marked to start in the background
        """

    @abc.abstractmethod
    def __enter__(self):
        """Enter context"""

    @abc.abstractmethod
    def __exit__(self, exeception_type, exception_value, traceback):
        """Exit context"""


class LeetSearchRequest():
    """Represents a search request from LEET to the backends with the necessary
    information on what we are looking for and, if something is found, what
    is necessary to create a job from it.

    Attributes:
        id (uuid.UUID): Automatically random generated search ID
        start_time (datetime.datetime): The time, in UTC, when the search was
            created
        end_time (datetime.datetime): The time, in UTC, when the search was
            finished
        hostnames (list of str): A list of hostnames the backends will look for
        plugin (LeetPlugin*): An instance of the LeetPlugin that will be executed
            on the machines
        ready (bool): A boolean that tells if the search is finished or not
        backend_quantity (int): The number of backends that are expected results
    """

    def __init__(self, hostnames, plugin, backend_numbers=0):
        """Returns a new object of LeetSearchRequest.

        Args:
            hostnames (list of str): A list of hostnames the backends will look for
            plugin (LeetPlugin*): An instance of the LeetPlugin that will be executed
                on the machines
            backend_numbers (int): The number of backends that are expected results
        """
        self.id = uuid.uuid4()
        self.start_time = datetime.datetime.utcnow()
        self.end_time = None
        self.hostnames = hostnames
        self.plugin = plugin
        self.ready = False

        self.backend_quantity = backend_numbers

        #we can have any number of threads adding machines or setting themselves
        #as completed, lock to control all
        self._completed_backends = set()
        self._change_lock = threading.RLock()

        self._found_machines = []
        #TODO do we need two locks?
        self._machine_lock = threading.RLock()

    @property
    def found_machines(self):
        """Stores all the machines found on the search, by backend."""
        return self._found_machines

    def add_completed_backend(self, backend_name):
        """Informs that a backend has completed the search.

        This information is tracked and if all backends have returned information,
        the search is completed. Once that happens, it is informed to the class
        that this happened.

        Args:
            backend_name (str): The uniqe name of the backend that has finished
                the search
        """
        if not self.ready:
            with self._change_lock:
                self._completed_backends.add(backend_name)
                if len(self._completed_backends) >= self.backend_quantity:
                    self.end_time = datetime.datetime.utcnow()
                    self.ready = True


    def add_found_machines(self, machine_list):
        """Adds the machines found by the backend to the list of found machines.

        Note:
            There is no guarantee that a machine won't be found in more than one
            backend.

        Args:
            machine_list (list of LeetMachine*): A list of subclasses of LeetMachine
                with all the machines found by the backend
        """
        if not self.ready:
            with self._machine_lock:
                self._found_machines += machine_list

    def __eq__(self, other):
        if isinstance(other, LeetJob):
            return self.id == other.id
        else:
            return False

    def __repr__(self):
        'Return a nicely formatted representation string'
        return (f'{self.__class__.__name__}(id={self.id}, '
                f'start_time={self.start_time}, end_time={self.end_time}, '
                f'hostnames={self.hostnames}, plugin={self.plugin}, '
                f'completed_backends={self._completed_backends})'
               )

class _JobFSM():
    """A very, very, very simplified state machine used to control how a job
    status can change. The machine is simple enough that it can be used by
    different types of variables, but as this should be used only internally
    for LEET, so we can define the expected types.

    Attributes:
        current_state (LeetJobStatus): Indicates what is the current status of the job
    """

    def __init__(self, transitions_table, initial):
        """Creates a new _JobFSM() object. The transition table is a list of dicts
        that contains the source state, the destination state and a trigger.

        Args:
            transitions_table (list of dict): Each entry in the list has to be a dict
                with the keys 'source', 'trigger' and 'dest'. The type of values of 'source'
                and 'dest' must be the same and, in this case, LeetJobStatus.
                The format is mandatory.
            initial (LeetJobStatus): The initial state of the FSM

        Returns:
            _JobFSM: New object using with the correct transition table
        """
        self._transitions = {}
        self.current_state = initial
        #this lock controls the change of status by the machine
        self._t_lock = threading.RLock()

        self._process_transitions(transitions_table)

    def _process_transitions(self, transitions_table):
        """Process the provided transition table so it is better used by
        the class. Effectively, it changes the format from:

            [{"source": source_state, "trigger": "trigger_name", "dest": dest_state},
            {"source": source_state, "trigger": "trigger_name", "dest": dest_state},
            ...]

        to a dictionary:
            {(source_state, "trigger_name"): dest_state,
            (source_state, "trigger_name"): dest_state,
            ...}

        This information is stored and used to move between states.
        """
        for t in transitions_table:
            self._transitions[(t["source"], t["trigger"])] = t["dest"]

    def next(self, condition):
        """Function used to transition between machine states. The condition HAS
        to be the same as the trigger that was passed, i.e., the operation '=='
        has to be valid and return True

        Args:
            condition (str): The condition that happened to change the trigger.

        Raises:
            LeetError: If there is a condition that has not been registered. Basically,
                if there is an attempt to move from a valid state, without the right
                trigger.
        """
        try:
            self._t_lock.acquire()
            self.current_state = self._transitions[(self.current_state, condition)]
        except KeyError as e:
            raise LeetError(f"Invalid transition from {self.current_state} with trigger {condition}") from e
        finally:
            self._t_lock.release()

class LeetJob():
    """Class that represents a Job in LEET. It creates a unique, random, identifier for the
    job that contains which machine the job will run, which plugin, the result
    of the plugin and state of the job.

    Attributes:
        id (UUID): ID of the job. Should not be manually set or changed at any point
        machine (string): The name of the machine where the plugin will be executed
        plugin_result (PluginResult): Where the result of the plugin execution will
            be stored
        plugin_instance (PluginBase*): An instance of any class that implements 'PluginBase'.
    """

    def __init__(self, machine, plugin_instance):
        """Creates a new LeetJob() object. Receives the name of the host and the
        plugin instance.

        Args:
            machine (string): The name of the machine
            plugin_instance (PluginBase*):  An instance of any class that implements 'PluginBase'.

        Returns:
            LeetJob: New object representing the job.
        """
        self.id = uuid.uuid4()
        self.machine = machine
        self.start_time = datetime.datetime.utcnow()
        self.plugin_result = None
        self.plugin_instance = plugin_instance
        self._status_machine = None

        self._conf_status_machine()

    @property
    def status(self):
        """Status of the job"""
        return self._status_machine.current_state

    def _conf_status_machine(self):
        """Defines the transaction table of all the jobs.

        It follows what is documented in LeetJobStatus documentation.
        """
        #TODO having a machine per job is wasteful. It is the same machine for all jobs,
        #replace this for a single machine for all jobs.
        # two special cases of note:
        #   pending to pending -> a job can go from pending to pending, by itself,
        #       it is already in the state so there is no issue
        #   cancelled receiving executin keeps in the same state:
        #       if a job has been cancelled while LEET is trying to connect, it
        #       is a waste to just drop the connection, as such, we keep in cancelled
        #       and if the job is successful, just move it to finished.
        #TODO I don't like the last statement
        t = [
            {"trigger" : "pending", "source" : LeetJobStatus.PENDING, "dest" : LeetJobStatus.PENDING},
            {"trigger" : "executing", "source" : LeetJobStatus.PENDING, "dest" : LeetJobStatus.EXECUTING},
            {"trigger" : "cancel", "source" : LeetJobStatus.PENDING, "dest" : LeetJobStatus.CANCELLED},
            {"trigger" : "pending", "source" : LeetJobStatus.EXECUTING, "dest" : LeetJobStatus.PENDING},
            {"trigger" : "cancel", "source" : LeetJobStatus.EXECUTING, "dest" : LeetJobStatus.CANCELLED},
            {"trigger" : "completed", "source" : LeetJobStatus.EXECUTING, "dest" : LeetJobStatus.COMPLETED},
            {"trigger" : "completed", "source" : LeetJobStatus.CANCELLED, "dest" : LeetJobStatus.COMPLETED},
            {"trigger" : "executing", "source" : LeetJobStatus.CANCELLED, "dest" : LeetJobStatus.CANCELLED},
            {"trigger" : "error", "source" : LeetJobStatus.EXECUTING, "dest" : LeetJobStatus.ERROR},
            {"trigger" : "error", "source" : LeetJobStatus.PENDING, "dest" : LeetJobStatus.ERROR}
        ]
        self._status_machine = _JobFSM(t, LeetJobStatus.PENDING)

    def pending(self):
        """Change the job status to pending.

        Raises:
            LeetError: If the job can't be moved into this state.
        """
        self._status_machine.next("pending")

    def executing(self):
        """Change the job status to executing.

        Raises:
            LeetError: If the job can't be moved into this state.
        """
        self._status_machine.next("executing")

    def cancel(self):
        """Change the job status to cancelled.

        Raises:
            LeetError: If the job can't be moved into this state.
        """
        self._status_machine.next("cancel")

    def completed(self):
        """Change the job status to completed.

        Raises:
            LeetError: If the job can't be moved into this state.
        """
        self._status_machine.next("completed")

    def error(self):
        """Change the job status to error.

        Raises:
            LeetError: If the job can't be moved into this state.
        """
        self._status_machine.next("error")

    def __eq__(self, other):
        if isinstance(other, LeetJob):
            return self.id == other.id
        else:
            return False

    def __repr__(self):
        'Return a nicely formatted representation string'
        return (f'{self.__class__.__name__}(id={self.id}, '
                f'machine={self.machine}, status={self.status}, '
                f'plugin_result={self.plugin_result}, plugin_instance={self.plugin_instance})'
               )

class _BackendControl(enum.Enum):
    """Controls what activity will be performed by the LeetBackend.

    Control command            | Value
    =======================================
    STOP                       | None
    SEARCH                     | LeetSearchRequest
    """
    STOP = 0x0
    SEARCH = 0x1

class LeetBackend(metaclass=abc.ABCMeta):
    """The main class for a LeetBackend. It abstracts the interaction between
    the Leet main class the backends.

    It is one of the classes that has to be overloaded by a backend.

    Attributes:
        backend_name (str): Name of the backend. Needs to be unique per instance
            of the backend
        max_sessions (int): The maximum number of sessions that a backend can
            hold simultaneously when connecting to the remote machines
        leet (Leet): A "pointer" to the main Leet class, allowing the backend
            to inform it of things it has done.
    """

    def __init__(self, backend_name, max_sessions):
        """Returns a new object of LeetBackend. Can't be used directly, only
        by subclasses.

        Args:
            backend_name (str): The name of the backend. It has to be unique by
                instance.
            max_sessions (int): The maximum number of sessions that a backend can
                hold simultaneously when connecting to the remote machines
        """
        self.backend_name = backend_name
        self.max_sessions = max_sessions
        #change this to to a threadpool?
        self._monitor_thread = threading.Thread(target=self._monitor_queue, name="Thr-" + backend_name)
        self._queue = queue.Queue()
        self.leet = None

    def start(self):
        """Start the backend thread and resources.

        Note:
            If overloaded by the subclass, the subclass MUST call the parent
            and return 'self'"""
        self._monitor_thread.start()

        return self

    def shutdown(self):
        """Deallocates the backend threads and resources.

        Note:
            If overloaded, by the subclass, the subclass MUST call the parent
        """
        self._queue.put((_BackendControl.STOP, None))
        self._monitor_thread.join()

    def search_machines(self, search_request):
        """Search for a group of machines on the backend.

        Args:
            search_request (LeetSearchRequest): The request with the information
                to be searched.
        """
        self._queue.put((_BackendControl.SEARCH, search_request))

    def _monitor_queue(self):
        """This method is the main loop for the thread present in the class.

        It monitors the internal queue for anything coming from the Leet class
        or the backend implementation and interfaces between them.
        """
        while True:
            code, value = self._queue.get()
            if code == _BackendControl.STOP:
                break
            elif code == _BackendControl.SEARCH:
                search_request = value
                machines = self._search_machines(search_request)
                _MOD_LOGGER.debug("Search finished. %d/%d found in this instance.", len(machines), len(search_request.hostnames))
                search_request.add_found_machines(machines)
                search_request.add_completed_backend(self.backend_name)
                _MOD_LOGGER.debug("Backend '%s' has finished searching.", self.backend_name)
                if search_request.ready:
                    _MOD_LOGGER.debug("Search is ready, sending notification")
                    self.leet.notify_search_completed(search_request)
            else:
                raise LeetError("'%s' is not a valid internal code", code)

            self._queue.task_done()

    def __enter__(self):
        """Enter context"""
        return self.start()

    def __exit__(self, exeception_type, exception_value, traceback):
        """Leave context"""
        #print(exeception_type, exception_value, traceback)
        self.shutdown()

    @abc.abstractmethod
    def _search_machines(self, search_request):
        """Method that search for the machines in the backend.

        This method needs to be overloaded by the subclass.

        Args:
            search_request (LeetSearchRequest): The search request to be processed
        """

##############################################################################
# Plugin basic data class section
##############################################################################

class LeetPluginParser(argparse.ArgumentParser):
    """A very simple extension of the standard ArgumentParser, so in case
    of errors we actually trigger an exception.
    """
    def error(self, message):
        raise LeetPluginError(message)

class PluginBase(metaclass=abc.ABCMeta):
    """The base class for all plugins. Defines basic methods on how to handle
    parameters and what the plugin needs to implement.

    Instructions on how to implement the plugin can be found on the "PLUGIN_INSTRUCTIONS"
    document. It is very important to note that plugins MUST be stateless.
    As a plugin might fail in the middle of execution. Effectively, what this means
    is that before doing something, check if it has been done before.

    A plugin behaves fully as a python code and can execute anything. For example,
    save files.

    Also, a plugin must return a PluginResult object. See the documentation there
    and the "PLUGIN_INSTRUCTIONS" for more information.

    Attributes:
        LEET_PG_NAME (str): name of the plugin, as it is going to be presented to
            the user
        LEET_PG_DESCRIPTION (str): A short description of the plugin
    """
    #TODO provide a hashing function as part of the backend?

    def __init__(self):
        """Creates a new PluginBase object.
        As a metaclass, it can't be instantiated by itself.

        Returns:
            PluginBase: New object representing the job.
        """
        self.arg_parser = LeetPluginParser(prog=self.LEET_PG_NAME, add_help=False)
        self.args = None
        #self._ltpg_param = {}

    def parse_parameters(self, args):
        self.args = self.arg_parser.parse_args(args)

    def get_help(self):
        """Returns a plugin help text based on description and parameters.

        Returns:
            str: A string containing the help of the plugin
        """
        header = [self.LEET_PG_DESCRIPTION, "=" * 40]
        help_msg = self.arg_parser.format_help()
        help_msg = help_msg.split(" ", 1)[1].replace("optional arguments:", "").split("\n")
        help_msg = "\n".join(header + [a for a in help_msg if a])

        return help_msg

    def get_plugin_parameters(self):
        """Returns all the parameters of a plugin.

        Returns:
            list of LeetPluginParameter: A list with all the parameters accepted
                by the plugin
        """
        return vars(self.args)

    @abc.abstractmethod
    def run(self, session, hostname):
        """This function will be called by the backend to execute the plugin
        and has to be overloaded. It will receive a session object, depending on
        the backend and the hostname of the machine in question.

        Args:
            session (depends on the backed): A session where the plugin can interact
                with the endpoint machine.
            hostname (str): The hostname where the plugin is executing.

        Returns:
            (list of dict): All the dicts should have the same keys, as the
                results will be passed to the user interface. For anything other
                than that, the plugin MUST implement what is necessary, including
                error handling.

            Example:
                data = [{"file name": "example.txt", size: "123"},
                        {"file name": "super.txt", size: "567"}]

        Raises:
            LeetPluginError: In case of any errors during the execution
                of the plugin
        """

    def __repr__(self):
        'Return a nicely formatted representation string'
        return (f'{self.__class__.__name__}(name={self.LEET_PG_NAME}, '
                f'description={self.LEET_PG_DESCRIPTION}, '
                f'_ltpg_param={self._ltpg_param})'
               )
