import uuid
import enum
import abc
import collections
import copy
import threading

class LeetBaseException(Exception):
    """Base class for all LeetException"""
    pass

class LeetPluginException(LeetBaseException):
    """Class for all plugin exceptions"""
    #TODO save plugin information
    pass

class LeetException(LeetBaseException):
    """Class for all exceptions outside of plugins"""
    pass

class LeetJobStatus(enum.Enum):
    '''Flags the status of an individual job.

    How are the states supposed to flow:
    PENDING -> EXECUTING, CANCELLED
    EXECUTING -> COMPLETED, CANCELLED, ERROR, PENDING

    There might be a situation where a job has been cancelled, but it is already
    on it's way, as such, we can also have:
    CANCELLED -> COMPLETED, ERROR
    '''
    #TODO one more status related to pending_cancellation?
    PENDING = 0x0
    EXECUTING = 0x1
    COMPLETED = 0x2
    CANCELLED = 0x3
    ERROR = 0x4


class _JobFSM():
    """A very, very, very simplified state machine to control how a job
    status can change."""
    def __init__(self, transitions_table, initial):
        #self.states = states
        self._transitions = {}
        self.current_state = initial
        self._t_lock = threading.RLock()

        self._process_transitions(transitions_table)

    def _process_transitions(self, transitions_table):
        for t in transitions_table:
            self._transitions[(t["source"], t["trigger"])] = t["dest"]

    def next(self, condition):
        try:
            self._t_lock.acquire()
            self.current_state = self._transitions[(self.current_state, condition)]
        except KeyError as e:
            raise LeetException(f"Invalid transition from {self.current_state} with trigger {condition}") from e
        finally:
            self._t_lock.release()

class LeetJob():
    """Class that represents a Job in Leet. It creates an identifier
    and saves all the relevant information to get a task running
    """
    def __init__(self, hostname, plugin_instance):
        self.id = uuid.uuid4()
        self.hostname = hostname
        self.plugin_result = None
        self.plugin_instance = plugin_instance
        self._status_machine = None

        self._conf_status_machine()

    @property
    def status(self):
        return self._status_machine.current_state

    def _conf_status_machine(self):
        t = [
            {"trigger" : "executing", "source" : LeetJobStatus.PENDING, "dest" : LeetJobStatus.EXECUTING},
            {"trigger" : "cancel", "source" : LeetJobStatus.PENDING, "dest" : LeetJobStatus.CANCELLED},
            {"trigger" : "pending", "source" : LeetJobStatus.EXECUTING, "dest" : LeetJobStatus.PENDING},
            {"trigger" : "cancel", "source" : LeetJobStatus.EXECUTING, "dest" : LeetJobStatus.CANCELLED},
            {"trigger" : "completed", "source" : LeetJobStatus.EXECUTING, "dest" : LeetJobStatus.COMPLETED},
            {"trigger" : "completed", "source" : LeetJobStatus.CANCELLED, "dest" : LeetJobStatus.COMPLETED},
            {"trigger" : "error", "source" : LeetJobStatus.EXECUTING, "dest" : LeetJobStatus.ERROR},
            {"trigger" : "error", "source" : LeetJobStatus.CANCELLED, "dest" : LeetJobStatus.ERROR}
        ]
        self._status_machine = _JobFSM(t, LeetJobStatus.PENDING)

    def pending(self):
        self._status_machine.next("pending")

    def executing(self):
        self._status_machine.next("executing")

    def cancel(self):
        self._status_machine.next("cancel")

    def completed(self):
        self._status_machine.next("completed")

    def error(self):
        self._status_machine.next("error")

    def __eq__(self, other):
        if isinstance(other, LeetJob):
            return self.id == other.id
        else:
            #TODO log?
            return False

    def __repr__(self):
        'Return a nicely formatted representation string'
        return (f'{self.__class__.__name__}(id={self.id}, '
                f'hostname={self.hostname}, status={self.status}, '
                f'plugin_result={self.plugin_result}, plugin_instance={self.plugin_instance})'
               )

class LeetBackend(metaclass=abc.ABCMeta):
    """
    Rules:
    - A backend must account for the possibility of more than one indentifier by machine?
    """
    def __init__(self, leet_backend_name):
        self.LEET_BACKEND = leet_backend_name

    def notify_job_completed(self, job):
        """Should be called by the backend implementation when a job has been
        completed.

        LeetJob
        """
        self._leet_control._notifyjob(job)

    @abc.abstractmethod
    def close(self):
        """Closes/Stops all the backend resources"""

    @abc.abstractmethod
    def start(self):
        """Allocate all the necessary resources to allow the backend to start"""

    @abc.abstractmethod
    def add_task(self, task):
        """Must receive a LeetJob"""

    @abc.abstractmethod
    def add_tasks(self, tasks):
        """Must receive a list of LeetJob"""

    @abc.abstractmethod
    def cancel_task(self, task):
        """Must receive a LeetJob"""

    def _set_leet_control(self, leet_control):
        """Is called internally to link the Leet parent class with the backend,
        so communication can flow. Should be called only from the contructor of
        the Leet class."""
        self._leet_control = leet_control

##############################################################################
# Plugin basic data class section
##############################################################################

#TODO a guide to write plugins

class LeetPluginParameter():
    """Defines a single parameter for a plugin. These need to be registered on
    the plugin instance."""
    def __init__(self, name, description, mandatory):
        self._vars = {"name" : name,
                     "description" : description,
                     "mandatory" : mandatory,
                     "value" : None}

    #Defines properties based on the dictionary
    def name():
        doc = "Name of the parameter."
        def fget(self):
            return self._vars["name"]
        def fset(self, value):
            raise LeetPluginParameter("Parameter 'name' is immutable.")
        def fdel(self):
            del self._vars["name"]
        return locals()
    name = property(**name())

    def description():
        doc = "Holds the descriptions of a parameter."
        def fget(self):
            return self._vars["description"]
        def fset(self, value):
            raise LeetPluginParameter("Parameter 'description' is immutable.")
        def fdel(self):
            del self._vars["description"]
        return locals()
    description = property(**description())

    def value():
        doc = "The value of the parameter."
        def fget(self):
            return self._vars["value"]
        def fset(self, value):
            self._vars["value"] = value
        def fdel(self):
            del self._vars["value"]
        return locals()
    value = property(**value())

    def mandatory():
        doc = "If a parameter is mandatory or not."
        def fget(self):
            return self._vars["mandatory"]
        def fset(self, value):
            raise LeetPluginParameter("Parameter 'mandatory' is immutable.")
        def fdel(self):
            del self._vars["mandatory"]
        return locals()
    mandatory = property(**mandatory())

    def __bool__(self):
        """Test if a parameter is defined correctly.

        The logic of the test is if a parameter is mandatory, but not defined,
        we have a problem. Otherwise, the parameter is correctly defined.
        """
        if self.mandatory and self.value is None:
            return False

        return True

    def __repr__(self):
        'Return a nicely formatted representation string'
        return (f'{self.__class__.__name__}(value={self.value}, '
                f'name={self.name}, '
                f'mandatory={self.mandatory}, description={self.description})'
               )

class PluginBase(metaclass=abc.ABCMeta):
    """
    A basic class for all plugins. Defines basic methods on how to handle
    parameters and what the plugin needs to implement.


    A plugin might fail. Badly. A plugin implementation must consider
    what is necessary to not do double work. For example: if the plugin
    adds a file a executes it, but a failure happens between the file transfer,
    the plugin must make sure to check if the file was there and take the
    appropriate actions before attempting a new transfer or command execution.

    A plugin needs to be stateless.

    #TODO provide a hashing function as part of the backend?

    """

    def __init__(self):
        self._ltpg_param = {}

    def reg_param(self, param):
        """Register a parameter. Receives LeetPluginParameter and should be called
        by the plugin's __init__"""
        self._ltpg_param[param.name] = param

    def set_param(self, parameters):
        """Set the parameters. Shouldn't be called directly by a plugin.
        Leet itslef will set the parameters coming from the user"""
        for key in parameters.keys():
            if key not in self._ltpg_param:
                raise LeetPluginException("Parameter is invalid for the chosen plugin.")
            else:
                self._ltpg_param[key].value = parameters[key]

    def get_param(self, name):
        """Return a parameter. Plugins should use this call to get the value."""
        #TODO a better way of getting this using properties
        return self._ltpg_param[name].value

    def check_param(self):
        """Does basic validation of the parameters. It makes sure all the
        necessary parameters are defined. Shoudl not be called by plugins, but
        can be overloaded in case the plugin requires better/different type
        of validation.
        """
        for key, item in self._ltpg_param.items():
            if not item:
                raise LeetPluginException(f"Mandatory parameter '{key}' missing")

    def get_help(self):
        """Returns a plugin help based on description and parameters."""
        param_list = []
        param_help = []

        for k, v in self._ltpg_param.items():
            param_list.append(k)
            param_help.append("\t".join([k, v.description]))

        param_list = "] [".join(param_list)
        param_help.insert(0, "\t")
        param_help = "\n\t".join(param_help)

        if param_list:
            help_text = "".join([self.LEET_PG_NAME, " [", param_list, "]\t", self.LEET_PG_DESCRIPTION, param_help])
        else:
            help_text = "".join([self.LEET_PG_NAME, "\t", self.LEET_PG_DESCRIPTION])


        return help_text

    def get_plugin_parameters(self):
        return [v for v in self._ltpg_param.values()]

    @abc.abstractmethod
    def run(self, session, hostname):
        """This function has to be overloaded. The plugin will receive a session
        (class to be defined) and MUST return a PluginResult intance.
        """
        #TODO define the session interface to decouple from the backend

    def __repr__(self):
        'Return a nicely formatted representation string'
        return (f'{self.__class__.__name__}(name={self.LEET_PG_NAME}, '
                f'description={self.LEET_PG_DESCRIPTION}, '
                f'_ltpg_param={self._ltpg_param})'
               )

class PluginResult():
    """Represents the result of a plugin execution"""
    #TODO Better define the interface.
    def __init__(self, success=False, headers=[], data=[]):
        self.success = success
        self.headers = headers
        self.data = data

    def __repr__(self):
        'Return a nicely formatted representation string'
        return (f'{self.__class__.__name__}(success={self.success}, '
                f'headers={self.headers}, data={self.data})'
               )
