import os
import time
import logging
import importlib
import threading, queue
import itertools
import enum

from .base import LeetJob, LeetJobStatus, LeetPluginException, LeetException

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

    with os.scandir(absolute_path) as dir:
        found_plugins = [entry.name for entry in dir if entry.is_file() and not entry.name.startswith("_") and entry.name.endswith(".py")]
    if not len(found_plugins):
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

class Leet(threading.Thread):
    def __init__(self, backend, notify_queue=None, plugin_dir=_PLUGIN_DIR):
        super().__init__(name="Thr-Leet")
        self._plugins = None
        self._queue = queue.SimpleQueue()
        self._backend = backend
        self._job_list = []
        #TODO receive a queue and put the result of the job on the queue,
        #   allowing realtime notification of completed jobs
        self._notify_queue = notify_queue
        self.ready = False

        self._completed_list_lock = threading.Lock()
        self._completed_list = []

        self._backend._set_leet_control(self)
        self.reload_plugins()


    @property
    def plugin_list(self):
        return [name for name in self._plugins.keys()]

    @property
    def job_status(self):
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
        self._completed_list_lock.acquire()
        self._job_list.remove(leet_job)
        self._completed_list.append(leet_job)
        self._completed_list_lock.release()

    def _notifyjob(self, job):
        """An internal function called by the LeetBackend to notify a job has
        been completed."""
        self._queue.put((_LTControl.JOB_COMPLETED_NOTIFICATION, job))

    def run(self):
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
                    value.cancel()
                    backend.cancel_task(value)
                else:
                    raise LeetException(f"No internal handling code for {code}.")
                    pass

                # except queue.Empty as e:
                #     f_tasks = lt_cb.pop_finished_tasks()
                #     tasks += f_tasks

    def return_completed_jobs(self):
        """This will return the completed jobs AND remove from the internal control.

        Returns a list of LeetJobs
        """
        self._completed_list_lock.acquire()
        temp_list = self._completed_list
        self._completed_list = []
        self._completed_list_lock.release()

        return temp_list

    def reload_plugins(self):
        _MOD_LOGGER.debug("(Re)loading plugins.")
        self._plugins = _load_plugins()

    def get_plugin(self, plugin_name):
        """Returns an instance of the plugin"""
        return self._plugins[plugin_name].LeetPlugin()

    def start_job_single_machine(self, hostname, plugin):
        """Start a job for a single machine"""
        plugin.check_param()
        self._queue.put((_LTControl.NEW_JOB, LeetJob(hostname, plugin)))

    def start_jobs(self, hostnames, plugin):
        """A list of hostnames, a plugin instance"""
        plugin.check_param()
        _MOD_LOGGER.debug("Requesting jobs for %i machines", len(hostnames))
        self._queue.put((_LTControl.NEW_JOBS, [LeetJob(hostname, plugin) for hostname in hostnames]))

    def cancel_job(self, job):
        """job - LeetJob"""
        self._queue.put((_LTControl.CANCEL_JOB, job))
        pass

    def cancel_by_id(self, id):
        """id - uuid"""
        self.cancel_job(self._job_list[id])

    def cancel_all_jobs(self):
        for job in self._job_list:
            self.cancel_job(job)

    def close(self):
        self._queue.put((_LTControl.STOP, None))
        self.ready = False
        #self.

    def __enter__(self):
        return self

    def __exit__(self, exeception_type, exception_value, traceback):
        #print(exeception_type, exception_value, traceback)
        self.close()
