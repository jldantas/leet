# -*- coding: utf-8 -*-
""" LEET main interface module.

This module contains the main interface for LEET, where plugins are initialized
and the class "Leet", which is the main interface.

LEET runs as a thread and all the requests from the application are handled by
this thread. As such, almost no calls to the functions in Leet will block the
main application thread. It also implies that closing of the resources might not
be immediate, as the thread processes outstanding requests.

LEET is basically organized as follows:

                     +-----------------+
                     | GUI/CLI         |
                     +-----------------+

                     +-----------------+
           +---------+ Leet            +----------+
           |         +--------+--------+          |
           |                  |                   |
LeetJob    |                  |                   |
           |                  |                   |
           |                  |                   |
           v                  |                   v
     +-----+-----+      +-----v-----+       +-----+-----+
     | Backend a |      | Backend b |       | Backend n |
     +-+------+--+      +--+-----+--+       +-+-------+-+
       |      ^            |     ^            |       ^
       |      |            |     |            |       |
       v      |            v     |            v       |
     +-+------+------------+-----+------------+-------+---+
     |                                                    |
     |  +----------+     +----------+      +----------+   |
     |  | Plugin a |     | Plugin b |      | Pulgin n |   |
     |  +----------+     +----------+      +----------+   |
     |                                                    |
     +----------------------------------------------------+

Where the interface communicates with Leet, Leet request a LeetJob for the backend
and the backend execute the specified plugin for the specified machine.
"""
import os
import logging
import importlib
import threading
import queue
import itertools
import enum

from .base import LeetJob, LeetError

_MOD_LOGGER = logging.getLogger(__name__)
_PLUGIN_DIR = "plugins"

def _load_plugins(plugin_dir=_PLUGIN_DIR):
    #TODO replace for a more robust system
    """Load the plugins dynamically.

    This function will parse the folder defined in '_PLUGIN_DIR' and do basic
    check to see if everything is present and plugin is defined. All plugins
    MUST NOT start with '_' and MUST end with '.py'.
    """
    plugins = {}
    absolute_path = os.path.join(os.path.dirname(__file__), plugin_dir)

    with os.scandir(absolute_path) as directory:
        found_plugins = [entry.name for entry in directory if entry.is_file() and not entry.name.startswith("_") and entry.name.endswith(".py")]
    if not found_plugins:
        #TODO better error information
        print("No plugin found. Stopping things.")
    _MOD_LOGGER.debug("Plugins found: %s", found_plugins)
    plugin_names = map(lambda fname: "." + os.path.splitext(fname)[0], found_plugins)
    #importlib.import_module(plugin_dir, package="leet") #import the parent module
    importlib.import_module("leet.plugins") #import the parent module
    #import the plugins
    for plugin in plugin_names:
        mod = importlib.import_module(plugin, package="leet." + plugin_dir)
        plugins[mod.LeetPlugin.LEET_PG_NAME] = mod

    return plugins

class _LTControl(enum.Enum):
    """ An internal control flag to tell what the thread handling Leet should
    do. This way all interaction happens via the internal control queue, making
    it easier to sync. This will always be passed as the first value of a tuple
    and the next values are documented here.

    Control command            | Value
    =======================================
    STOP                       | None
    NEW_JOB                    | LeetJob
    NEW_JOBS                   | [LeetJob]
    JOB_COMPLETED_NOTIFICATION | LeetJob
    CANCEL_JOB                 | LeetJob
    """
    STOP = 0x0
    NEW_JOB = 0x1
    NEW_JOBS = 0x2
    JOB_COMPLETED_NOTIFICATION = 0x3
    CANCEL_JOB = 0x4

#TODO add support to return table or save to file (csv?)
class Leet(threading.Thread):
    """This is the main class from LEET. It starts all control needs and
    finds all the available plugins.

    The backend is also instantiated and necessary control between backend and
    this class is triggered. Once the instance has been started, a simple
    call to start (coming from the Thread class) will start the main loop
    allowing submission of tasks.

    Attributes:
        ready (bool): True or false if LEET is ready to start receiving jobs
    """

    def __init__(self, backend, notify_queue=None, plugin_dir=_PLUGIN_DIR):
        """Creates a new Leet() object. It receives an instance of the backend
        that will be used for communication and a path where to look for the
        plugins.

        Args:
            backend (LeetBackend*): An instance of a class that has overridden the
                LeetBackend class
            notify_queue (queue.Queue): NOT IMPLEMENTED, IGNORE
            plugin_dir (string|path): A path to where the plugins are located

        Returns:
            Leet: New object
        """
        super().__init__(name="Thr-Leet")
        self._plugins = None
        self._queue = queue.SimpleQueue()
        #TODO add support to multiple backends at the same time
        self._backend = backend
        self._job_list = []
        #TODO receive a queue and put the result of the job on the queue,
        #   allowing realtime notification of completed jobs
        self._notify_queue = notify_queue
        self.ready = False

        self._completed_list_lock = threading.Lock()
        self._completed_list = []

        self._backend._set_leet_control(self)
        #TODO plugin load/reload should be independent from LEET
        self.reload_plugins()


    @property
    def plugin_list(self):
        """A list of plugin names"""
        return [name for name in self._plugins.keys()]

    @property
    def job_status(self):
        """A list of dictionaries with each job, its status and basic information"""
        status = []
        #acquire lock as jobs might be completed while processing
        self._completed_list_lock.acquire()
        for job in itertools.chain(self._job_list, self._completed_list):
            status.append({"id" : job.id,
                           "hostname" : job.hostname,
                           "plugin": job.plugin_instance.LEET_PG_NAME,
                           "status" : job.status})
        self._completed_list_lock.release()

        return status

    def _set_finished_job(self, leet_job):
        """Internal function that moves a job from the "general" list to a
        completed job list, garanting right lock usage
        """
        self._completed_list_lock.acquire()
        self._job_list.remove(leet_job)
        self._completed_list.append(leet_job)
        self._completed_list_lock.release()

    def _notifyjob(self, job):
        """An internal function called by the LeetBackend to notify a job has
        been completed.

        Args:
            job (LeetJob): The LeetJob that was completed.
        """
        self._queue.put((_LTControl.JOB_COMPLETED_NOTIFICATION, job))

    def run(self):
        """Starts LEET and all backend connections, making LEET ready to be
        interacted with.
        """
        with self._backend.start() as backend:
            self.ready = True
            while True:
                # try:
                    #code, value = in_queue.get(timeout=10)
                code, value = self._queue.get()
                _MOD_LOGGER.debug("Received request for '%s'", code)
                if code == _LTControl.STOP:
                    break
                elif code == _LTControl.NEW_JOBS:
                    backend.add_tasks(value)
                    self._job_list += value
                elif code == _LTControl.NEW_JOB:
                    backend.add_task(value)
                    self._job_list.append(value)
                elif code == _LTControl.JOB_COMPLETED_NOTIFICATION:
                    self._set_finished_job(value)
                elif code == _LTControl.CANCEL_JOB:
                    #TODO handle if the job does not exists
                    #TODO handle error if a completed job is requested to be cancelled (LeetError)
                    value.cancel()
                    backend.cancel_task(value)
                else:
                    raise LeetError(f"No internal handling code for {code}.")

                # except queue.Empty as e:
                #     f_tasks = lt_cb.pop_finished_tasks()
                #     tasks += f_tasks

    def return_completed_jobs(self):
        """This will return the completed jobs AND remove from the internal control.
        Right now this is the only function that will remove jobs from leet,
        freeing memory and should be consistently called by the interface.

        Returns:
            [LeetJobs]: A list of LeetJobs that have been finished
        Returns a list of LeetJobs
        """
        self._completed_list_lock.acquire()
        temp_list = self._completed_list
        self._completed_list = []
        self._completed_list_lock.release()

        return temp_list

    def reload_plugins(self):
        """Forces a plugin reload"""
        _MOD_LOGGER.debug("(Re)loading plugins.")
        self._plugins = _load_plugins()

    def get_plugin(self, plugin_name):
        """Returns an instance of the plugin based on the name.

        Args:
            plugin_name (str): The name of the plugin

        Returns:
            (LeetPlugin*): An instance of the requested plugin

        Raises:
            KeyError: If the plugin name doesn't exists
        """
        return self._plugins[plugin_name].LeetPlugin()

    def start_job_single_machine(self, hostname, plugin):
        """Start a job for a single machine.

        Args:
            hostname (str): The target machine name
            plugin (LeetPlugin*): The plugin instance that will be executed
        """
        plugin.check_param()
        self._queue.put((_LTControl.NEW_JOB, LeetJob(hostname, plugin)))

    def start_jobs(self, hostnames, plugin):
        """Start a job for a list of machines

        Args:
            hostnames (list of str): A list of targer machine names
            plugin (LeetPlugin*): The plugin instance that will be executed
        """
        plugin.check_param()
        _MOD_LOGGER.debug("Requesting jobs for %i machines", len(hostnames))
        self._queue.put((_LTControl.NEW_JOBS, [LeetJob(hostname, plugin) for hostname in hostnames]))

    def cancel_job(self, job):
        """Cancel a job.

        Args:
            job (LeetJob): A instance of LeetJob that will be cancelled.
        """
        self._queue.put((_LTControl.CANCEL_JOB, job))

    def cancel_by_id(self, job_id):
        """Cancel a job by id.

        Args:
            job_id (UUID): The ID of the job that should be cancelled.

        Raises:
            KeyError: In case the ID does not exists
        """
        #TODO replace error for LeetError?
        self.cancel_job(self._job_list[job_id])

    def cancel_all_jobs(self):
        """Cancel all jobs."""
        for job in self._job_list:
            self.cancel_job(job)

    def close(self):
        """Stop the execution of Leet and free all the resources, including the
        backend resources."""
        self._queue.put((_LTControl.STOP, None))
        self.ready = False
        #self.

    def __enter__(self):
        """Context enter"""
        return self

    def __exit__(self, exeception_type, exception_value, traceback):
        """Context exit"""
        #print(exeception_type, exception_value, traceback)
        self.close()
