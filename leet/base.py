import uuid
import enum
import abc
import collections
import copy

class LeetException(Exception):
    """Base class for all LeetException"""
    pass

class LeetPluginException(LeetException):
    """Class for all plugin exceptions"""
    #TODO save plugin information
    pass

class LeetJobStatus(enum.Enum):
    '''Flags the status of an individual job'''
    PENDING = 0x0
    SUCCESS = 0x1
    FAILURE = 0x2
    EXECUTING = 0x3
    PENDING_NEWATTEMPT = 0x4
    CANCEL_REQUESTED =- 0x5
    CANCELLED = 0x6
    ERROR = 0x7

class LeetJob():
    """Class that represents a Job in Leet. It creates an identifier
    and saves all the relevant information to get a task running
    """
    def __init__(self, hostname, plugin_instance):
        self.id = uuid.uuid4()
        self.hostname = hostname
        #TODO add a lock to control the status, as this can change from the interface and from the backend
        self.status = LeetJobStatus.PENDING
        self.plugin_result = None
        self.plugin_instance = plugin_instance

    def __eq__(self, other):
        if self.id == other.id:
            return True
        else:
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
    def add_tasks(self, task):
        """Must receive a new LeetJob"""

    # @abc.abstractmethod
    # def pop_finished_tasks(self):
    #     """Returns a list of finished LeetJob """
    #
    # @abc.abstractmethod
    # def get_pending_tasks(self):
    #     """Returns a list of unfinished LeetJob"""

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


# self._ltpg_param = {}
#
# def __init__(self, name, description, mandatory):
#     self._vars = {"name" : name,
#                  "description" : description,
#                  "mandatory" : mandatory,
#                  "value" : None}
#
#
# self.reg_param(LeetPluginParameter("path", "Path to be listed on the remote endpoint", True))
#
#         LEET_PG_NAME = "dirlist"
#         LEET_PG_DESCRIPTION = "Returns a directory list from a path with STD timestamp data."
#         LEET_BACKEND = ["cb"]
#         pass

    @abc.abstractmethod
    def run(self, session, hostname):
        """This function has to be overloaded. The plugin will receive a session
        (class to be defined) and MUST return a PluginResult intance.
        """
        #TODO define the session interface to decouple from the backend

    def __repr__(self):
        'Return a nicely formatted representation string'
        return (f'{self.__class__.__name__}('
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
