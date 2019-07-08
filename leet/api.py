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

On a high level, these are the steps LEET uses to execute a job:

# Recevies a request from the UI
# Transform that request in a LeetSearchRequest and sends it to be processed by
    the backends
# Receives the results from the backend(s) and for the machines found, create the
    necessary LeetJob
# Pool for the machines to be online and once they are online try to connect
    and execute the plugin
# Notifies the UI that a LeetJob is done.
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
from apscheduler.schedulers.base import STATE_STOPPED as APS_SCHED_STOPPED

from .base import LeetJob, LeetSearchRequest, LeetJobStatus
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

class _LTControl(enum.Enum):
    """ An internal control flag to tell what the thread handling Leet should
    do. This way all interaction happens via the internal control queue, making
    it easier to sync. This will always be passed as the first value of a tuple
    and the next values are documented here.

    Control command            | Value
    =======================================
    STOP                       | None
    SEARCH_BACKEND             | LeetSearchRequest
    SEARCH_READY               | LeetSearchRequest
    JOB_DONE                   | LeetJob
    """
    STOP = 0x0
    SEARCH_BACKEND = 0x1
    SEARCH_READY = 0x2
    JOB_DONE = 0x3

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

    def __init__(self, backend_list, job_notification):
        """
        Args:
            backend_list (list of LeetBackend*): A list of the backend instances.
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
        return [name for name in self._plugins]

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

    def notify_search_completed(self, search_request):
        """Notifies a search has been completed by all backends.

        Note:
            This method should be called by the backends only.

        Args:
            search_request (LeetSearchRequest): The search request that has been
                completed.
        """
        self._queue.put((_LTControl.SEARCH_READY, search_request))

    def _start_threads(self, stack):
        # start the schedulers
        temp_backend = {}

        _MOD_LOGGER.debug("Starting schedulers...")
        self._sched_machine.start()
        self._sched_search.start()
        _MOD_LOGGER.debug("Starting backend resources...")

        for backend, pool in self._backend_list.values():
            pool = concurrent.futures.ThreadPoolExecutor(max_workers=backend.max_sessions, thread_name_prefix="Thr-" + backend.backend_name + "-sessions")
            temp_backend[backend.backend_name] = (backend, pool)
            stack.enter_context(pool)
            stack.enter_context(backend)
            _MOD_LOGGER.debug("Finished allocating resources for backend '%s'", backend.backend_name)

        self._backend_list = temp_backend
        self.ready = True

    def run(self):
        """Starts LEET, the threads and backend connections, making LEET ready to be
        interacted with.
        """
        with contextlib.ExitStack() as stack:
            self._start_threads(stack)
            #TODO this look ugly, redo
            backend_quantity = len(self._backend_list)
            #main loop
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

    def _conf_backend(self, backend_list):
        """Links the backend with the Leet class.

        Args:
            backedn_list (LeetBackend*): A list of backend instances
        """
        for backend in backend_list:
            _MOD_LOGGER.debug("Linking backend %s with LEET.", backend.backend_name)
            backend.leet = self
            self._backend_list[backend.backend_name] = (backend, None)

    def _search_ready(self, search_request):
        """Internal method to process a search that is ready.

        It internally process the LeetSearchRequest once the search is ready
        or has expired. For all machines that were found by the backend a new
        LeetJob is created and add to the processing schedule.

        Args:
            search_request (LeetSearchRequest): The search that is ready
        """
        f_machines = set()

        _MOD_LOGGER.debug("Search finished. Took %s secs.", search_request.end_time - search_request.start_time)
        #TODO solve conflicts
        for machine in search_request.found_machines:
            f_machines.add(machine.hostname)
            _MOD_LOGGER.info("Adding job for machine %s", machine.hostname)
            self._add_job(LeetJob(machine, search_request.plugin))
        if len(search_request.hostnames) > len(f_machines):
            _MOD_LOGGER.info("The following machines were not found and will be ignored: %s", [h for h in search_request.hostnames if h not in f_machines])

    def _add_job(self, leet_job):
        """Internal method that adds the job to the processing list and
        to the schedule."""
        with self._job_list_lock:
            self._job_list.append(leet_job)
            self._sched_machine.add_job(self._is_machine_ready, 'date', args=[leet_job])

    def _remove_job(self, leet_job):
        """Removes a job from the job list."""
        with self._job_list_lock:
            self._job_list.remove(leet_job)

    #TODO move this to another place? where?
    def _execute_plugin(self, leet_job):
        """Manages the execution of the plugin in one machine.

        It will attempt to connect to the machine and execute the plugin, also
        taking care to set the correct state of the job. It will also handle
        two types of errors that can be raised due to the execution: 'LeetSessionError'
        and 'LeetPluginerror'.

        In case of a 'LeetPluginError', it will stop the execution of the job and
        mark it as an error.

        Args:
            leet_job (LeetJob): The LeetJob instance that is going to be executed.
        """
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
            leet_job.plugin_result = [{"error_message": str(e)}]
            self._queue.put((_LTControl.JOB_DONE, leet_job))

    def _handle_errors(self, result):
        """Catch all method registered as a callback for the jobs once they are executed.
        """
        #TODO, obviously
        result.result()

    def _expire_search(self, search_request):
        """ Expires the search and process what has been foudn.

        If a search timeout, mark it as ready and schedule for execution

        Args:
            search_request (LeetSearchRequest): Search that has expired.
        """
        #if the search is ready, just let it be removed by the scheduler.
        if not search_request.ready:
            _MOD_LOGGER.warning("Search %s expired. Running the jobs with what we have", search_request.id)
            #TODO more info on what completed and what expired
            search_request.ready = True
            self.notify_search_completed(search_request)
        else:
            _MOD_LOGGER.debug("Search %s has been completed, remove from schedule", search_request.id)


    def _can_reschedule_job(self, leet_job):
        """Checks if a jobs can be rescheduled.

        Args:
            leet_job (LeetJob): LeetJob that will be checked.

        Returns:
            (bool): True if it can be rescheduled or False, if not.
        """
        expiry_time = leet_job.start_time + self._job_expiry_timeout
        if leet_job.status != LeetJobStatus.CANCELLED and datetime.datetime.utcnow() < expiry_time:
            return True
        else:
            return False

    def _is_machine_ready(self, leet_job):
        """Check if the machine is ready to connect. If not, reschedule the
        job to try again in the time determined by 'self._machine_update_interval'.
        """
        leet_job.machine.refresh()
        if leet_job.machine.can_connect:
            _MOD_LOGGER.debug("Machine for job %s is Online. Attempting connection.", leet_job.id)
            job = self._backend_list[leet_job.machine.backend_name][1].submit(self._execute_plugin, leet_job)
            job.add_done_callback(self._handle_errors)
        else:
            if self._can_reschedule_job(leet_job):
                _MOD_LOGGER.debug("Machine for job %s is Offline. Rescheduling", leet_job.id)
                next_exec = datetime.datetime.now() + self._machine_update_interval
                self._sched_machine.add_job(self._is_machine_ready, 'date', run_date=next_exec, args=[leet_job])
            else:
                _MOD_LOGGER.debug("Job %s has been cancelled or timed out. Removing.", leet_job.id)
                #TODO change job status in case it has not been cancelled. Timeout status?
                self._queue.put((_LTControl.JOB_DONE, leet_job))

    def schedule_jobs(self, plugin, hostnames):
        """Main interface between the UI and the class. It receives the list
        of hostnames and the plugin that will be executed.

        Args:
            plugin (LeetPlugin*): The instance of the plugin to be executed
            hostnames (list of str): A list with the hostnames where the search
            will be executed.
        """
        #TODO remove
        #plugin.check_param()
        search_request = LeetSearchRequest(hostnames, plugin)
        _MOD_LOGGER.debug("Scheduling jobs for %i machines", len(hostnames))
        self._queue.put((_LTControl.SEARCH_BACKEND, search_request))

    def cancel_job(self, job):
        """Cancel a job.

        Args:
            job (LeetJob): A instance of LeetJob that will be cancelled.
        """
        pass
        # self._queue.put((_LTControl.CANCEL_JOB, job))

    def cancel_by_id(self, job_id):
        """Cancel a job by id.

        Args:
            job_id (UUID): The ID of the job that should be cancelled.

        Raises:
            KeyError: In case the ID does not exists
        """
        pass
        #TODO replace error for LeetError?
        # self.cancel_job(self._job_list[job_id])

    def cancel_all_jobs(self):
        """Cancel all jobs."""
        pass
        # for job in self._job_list:
        #     self.cancel_job(job)

    def _stop_schedulers(self):
        _MOD_LOGGER.debug("Closing scheduler threads...")
        if self._sched_machine.state != APS_SCHED_STOPPED:
            self._sched_machine.shutdown()
        if self._sched_search.state != APS_SCHED_STOPPED:
            self._sched_search.shutdown()

    def shutdown(self):
        """Stop the execution of Leet and free all the resources, including the
        backend resources."""
        self._stop_schedulers()
        self._queue.put((_LTControl.STOP, None))

        # if self.ready:
        #     self.ready = False
        #     _MOD_LOGGER.debug("Requesting all threads to close")
        #     self._queue.put((_LTControl.STOP, None))
        #     _MOD_LOGGER.debug("Closing backend threads")
        #     for backend, thread_pool in self._backend_list.values():
        #         backend.shutdown()
        #         thread_pool.shutdown()


            # self._sched_machine.shutdown()
            # self._sched_search.shutdown()
