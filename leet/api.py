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
                     +-----------------+                  +----------------+
                                                          |  +----------+  |
                     +-----------------+                  |  | Plugin a |  |
                     + Leet            +------------------+  +----------+  |
                     +---+----+--------+                  |                |
                         ^    ^     ^                     |  +----------+  |
LeetJob                  |    |     |                     |  | Plugin b |  |
              +----------+    |     +-------------+       |  +----------+  |
              |               |                   |       +----------------+
              v               |                   v
     +-----+-----+      +-----v-----+       +-----+-----+
     | Backend a |      | Backend b |       | Backend n |
     +-----------+      +-----------+       +-----------+

Where the interface communicates with Leet, Leet request a LeetJob for the backend
and the backend execute the specified plugin for the specified machine.
"""
import threading
import contextlib
import concurrent.futures
import enum
import queue
import logging
import datetime
import os
import importlib

from apscheduler.schedulers.background import BackgroundScheduler

from .base import LeetJob, LeetSearchRequest
from .errors import  LeetError, LeetSessionError, LeetPluginError

_MOD_LOGGER = logging.getLogger(__name__)

def _load_plugins(plugin_dir="plugins"):
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


    # NEW_JOB = 0x1
    # NEW_JOBS = 0x2
    # JOB_COMPLETED_NOTIFICATION = 0x3
    # CANCEL_JOB = 0x4
    #
    # FIND_MACHINES_BACKEND = 0x6
    # SEARCH_RESULT = 0x10

class _LTControl(enum.Enum):
    """ An internal control flag to tell what the thread handling Leet should
    do. This way all interaction happens via the internal control queue, making
    it easier to sync. This will always be passed as the first value of a tuple
    and the next values are documented here.

    Control command            | Value
    =======================================
    STOP                       | None
    SEARCH_BACKEND                    | LeetSearch
    NEW_JOBS                   | [LeetJob]
    JOB_COMPLETED_NOTIFICATION | LeetJob
    CANCEL_JOB                 | LeetJob
    """
    STOP = 0x0
    SEARCH_BACKEND = 0x1
    SEARCH_READY = 0x2
    JOB_DONE = 0x3

class Leet(threading.Thread):

    def __init__(self, backend_list, job_notification):
        """
        Args:
            job_notification (Queue?): A queue or something similar that has support
                for the method 'put(LeetJob)' and is thread safe. This is how the
                LEET returns data to the upper levels
        """
        super().__init__(name="Thr-Leet")
        self.ready = False
        self._backend_list = {}
        self._queue = queue.SimpleQueue()
        self._plugins = None

        self._job_list_lock = threading.Lock()
        self._job_list = []

        self._search_timeout = datetime.timedelta(seconds=30)
        self._sched_search = BackgroundScheduler()

        self._machine_update_interval = datetime.timedelta(seconds=20)
        self._sched_machine = BackgroundScheduler()

        self._job_expiry_timeout = datetime.timedelta(days=3)

        self._job_notification = job_notification

        self._conf_backend(backend_list)
        self.reload_plugins()

    @property
    def job_status(self):
        """A list of dictionaries with each job, its status and basic information"""
        status = []
        #acquire lock as jobs might be completed while processing
        with self._job_list_lock:
            for job in self._job_list:
                status.append({"id" : job.id,
                               "hostname" : job.machine.hostname,
                               "plugin": job.plugin_instance.LEET_PG_NAME,
                               "status" : job.status})

        return status

    @property
    def plugin_list(self):
        """A list of plugin names"""
        return [name for name in self._plugins.keys()]

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

    def _conf_backend(self, backend_list):
        for backend in backend_list:
            _MOD_LOGGER.debug("Linking backend %s and allocating resources.", backend.backend_name)
            backend.leet = self
            pool = concurrent.futures.ThreadPoolExecutor(max_workers=backend.max_sessions, thread_name_prefix="Thr-" + backend.backend_name + "sessions")
            self._backend_list[backend.backend_name] = (backend, pool)

    def notify_search_completed(self, search_request):
        """Notifies a search has been completed.

        Should be called by the backend only.
        """
        self._queue.put((_LTControl.SEARCH_READY, search_request))

    def run(self):

        with contextlib.ExitStack() as stack:
            self._sched_machine.start()
            self._sched_search.start()
            _MOD_LOGGER.debug("Starting all backends")
            for backend, pool in self._backend_list.values():
                stack.enter_context(backend)
            self.ready = True
            #TODO this look ugly, redo
            backend_quantity = len(self._backend_list)

            while True:
                code, value = self._queue.get()
                _MOD_LOGGER.debug("Processing internal command '%s'", code)
                if code == _LTControl.STOP:
                    break
                elif code == _LTControl.SEARCH_BACKEND:
                    value.backend_quantity = backend_quantity
                    for backend, t_pool in self._backend_list.values():
                        backend.search_machines(value)
                    next_exec = datetime.datetime.now() + self._search_timeout
                    self._sched_search.add_job(self._expire_search, 'date', run_date=next_exec, args=[value], id=str(value.id))
                elif code == _LTControl.SEARCH_READY:
                    self._search_ready(value)
                elif code == _LTControl.JOB_DONE:
                    self._remove_job(value)
                    self._job_notification.put(value)

    def _search_ready(self, search_request):
        _MOD_LOGGER.debug("Search finished. Took %s secs.", search_request.end_time - search_request.start_time)

        f_machines = set()

        #TODO solve conflicts
        for machine in search_request._found_machines:
            f_machines.add(machine.hostname)
            _MOD_LOGGER.info("Adding job for machine %s", machine.hostname)
            self._add_job(LeetJob(machine, search_request.plugin))
            #self._sched_machine.add_job(self._is_machine_ready, 'date', args=[LeetJob(machine, search_request.plugin)])
        if len(search_request.hostnames) > len(f_machines):
            _MOD_LOGGER.info("The following machines were not found and will be ignored: %s", [h for h in search_request.hostnames if h not in f_machines])

    def _add_job(self, leet_job):
        with self._job_list_lock:
            self._job_list.append(leet_job)
            self._sched_machine.add_job(self._is_machine_ready, 'date', args=[leet_job])

    def _remove_job(self, leet_job):
        with self._job_list_lock:
            self._job_list.remove(leet_job)

    def _execute_plugin(self, leet_job):
        try:
            with leet_job.machine.connect() as session:
                _MOD_LOGGER.debug("Session for job %s ready. Starting execution.", leet_job.id)
                leet_job.executing()
                leet_job.plugin_result = leet_job.plugin_instance.run(session, leet_job.machine)
                leet_job.completed()
                _MOD_LOGGER.debug("Job %s was successful.", leet_job.id)
                self._queue.put((_LTControl.JOB_DONE, leet_job))
        except LeetSessionError as e:
            if not e.stop:
                _MOD_LOGGER.debug("Job %s failed. Error: %s", leet_job.id, str(e))
                leet_job.pending()
                _MOD_LOGGER.debug("Rescheduling Job %s", leet_job.id)
                self._is_machine_ready(leet_job)
            else: #if this is a critial session error, let's remove the job from processing
                self._queue.put((_LTControl.JOB_DONE, leet_job))
        except LeetPluginError as e:
            _MOD_LOGGER.debug("Job %s failed. Error in plugin execution", leet_job.id)
            _MOD_LOGGER.exception(e)
            leet_job.error()
            self._queue.put((_LTControl.JOB_DONE, leet_job))


            # try:
            #     with cb_task.sensor.lr_session() as session:
            #         _MOD_LOGGER.debug("Session for job %s ready. Starting execution.", cb_task.leet_job.id)
            #         cb_task.leet_job.executing() #TODO this can raise an exception LeetException.
            #         results = cb_task.leet_job.plugin_instance.run(session, cb_task.leet_job.hostname)
            #         if results.success:
            #             cb_task.leet_job.plugin_result = results
            #             _MOD_LOGGER.debug("Job %s was successful.", cb_task.leet_job.id)
            #         else:
            #             _MOD_LOGGER.debug("Job %s failed.", cb_task.leet_job.id)
            #         cb_task.leet_job.completed()
            #         self._out_queue.put(_CBComms(_CBCode.FINISHED_NOTIFICATION, cb_task))
            # except cbapi.errors.TimeoutError as e:
            #     try:
            #         #if we trigger this exception here, it means we tried an invalid
            #         #change of status and needs to be removed from the processing list
            #         self.leet_job.pending()
            #         self._out_queue.put(_CBComms(_CBCode.RESCHEDULE, cb_task))
            #     except LeetError as e:
            #         self._out_queue.put(_CBComms(_CBCode.REMOVE_FROM_LIST, cb_task))
            # except cbapi.live_response_api.LiveResponseError as e:
            #     _MOD_LOGGER.exception(e)
            #     cb_task.leet_job.error()
            #     self._out_queue.put(_CBComms(_CBCode.REMOVE_FROM_LIST, cb_task))
            # except LeetError as e:
            #     #print("****** HANDLER 2")
            #     _MOD_LOGGER.exception(e)
            #     cb_task.leet_job.error()
            #     self._out_queue.put(_CBComms(_CBCode.REMOVE_FROM_LIST, cb_task))
            # # #TODO! VERY BAD PRACTICE DETECTED. FIND A BETTER WAY TO HANDLE EXCEPTION FROM THREADPOOL
            # except Exception as e:
            #     print("****** HANDLER 3")
            #     _MOD_LOGGER.exception(e)
            #     print(e)

    def _handle_errors(self, result):
        #TODO, obviously
        result.result()

    def _expire_search(self, search_request):
        #if the search is ready, just let it be removed by the scheduler.
        if not search_request.ready:
            _MOD_LOGGER.warning("Search %s expired. Running the jobs with what we have", search_request.id)
            #TODO more info on what completed and what expired
            search_request.ready = True
            self.notify_search_completed(search_request)
        else:
            _MOD_LOGGER.warning("Search %s has been completed, remove from schedule", search_request.id)


    def _can_reschedule_job(self, leet_job):
        expiry_time = leet_job.start_time + self._job_expiry_timeout
        if leet_job.status != LeetJobStatus.CANCELLED and datetime.datetime.utcnow() < expiry_time:
            return True
        else:
            return False

    def _is_machine_ready(self, leet_job):
        leet_job.machine.refresh()
        if leet_job.machine.can_connect:
            _MOD_LOGGER.debug("Machine for job %s is Online. Attempting connection.", leet_job.id)
            job = self._backend_list[leet_job.machine.backend_name][1].submit(self._execute_plugin, leet_job)
            job.add_done_callback(self._handle_errors)
        else:
            if _can_reschedule_job(leet_job):
                _MOD_LOGGER.debug("Machine for job %s is Offline. Rescheduling", leet_job.id)
                next_exec = datetime.datetime.now() + self._machine_update_interval
                self._sched.add_job(self._is_machine_ready, 'date', run_date=next_exec, args=[leet_job])
            else:
                _MOD_LOGGER.debug("Job %s has been cancelled or timed out. Removing.", leet_job.id)
                #TODO change job status in case it has not been cancelled. Timeout status?
                self._queue.put((_LTControl.JOB_DONE, leet_job))

    def schedule_jobs(self, plugin, hostnames):
        """plugin instance
        list of hostnames"""
        plugin.check_param()
        search_request = LeetSearchRequest(hostnames, plugin)
        _MOD_LOGGER.debug("Scheduling jobs for %i machines", len(hostnames))
        self._queue.put((_LTControl.SEARCH_BACKEND, search_request))

    def shutdown(self):
        """Stop the execution of Leet and free all the resources, including the
        backend resources."""
        if self.ready:
            self.ready = False
            _MOD_LOGGER.debug("Requesting all threads to close")
            self._queue.put((_LTControl.STOP, None))
            _MOD_LOGGER.debug("Closing backend threads")
            for backend, thread_pool in self._backend_list.values():
                backend.shutdown()
                thread_pool.shutdown()

            _MOD_LOGGER.debug("Closing scheduler threads")
            self._sched_machine.shutdown()
            self._sched_search.shutdown()
