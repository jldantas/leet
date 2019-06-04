import os
import time
import logging
import importlib
import threading, queue
import itertools
import enum

from .base import LeetJob, LeetJobStatus, LeetPluginException

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
    plugin_names = map(lambda fname: "." + os.path.splitext(fname)[0], found_plugins)
    #importlib.import_module(plugin_dir, package="leet") #import the parent module
    importlib.import_module("leet.plugins") #import the parent module
    #import the plugins
    for plugin in plugin_names:
        mod = importlib.import_module(plugin, package="leet." + plugin_dir)
        plugins[mod.LeetPlugin.LEET_PG_NAME] = mod

    return plugins

class _LTControl(enum.Enum):
    """
    STOP - None
    NEW_JOB - LeetJob
    NEW_JOBS - [LeetJob]
    JOB_COMPLETED_NOTIFICATION - LeetJob

    """
    STOP = 0x0
    NEW_JOB = 0x1
    NEW_JOBS = 0x2
    JOB_COMPLETED_NOTIFICATION = 0x3


    # PROCESS = 0x2
    # RESCHEDULE = 0x3
    # FINISHED_NOTIFICATION = 0x4


class Leet(threading.Thread):
    def __init__(self, backend, notify_queue=None, plugin_dir=_PLUGIN_DIR):
        super().__init__(name="Thr-Leet")
        self._plugins = None
        self._queue = queue.Queue()
        self._backend = backend
        self._job_list = []
        #TODO receive a queue and put the result of the job on the queue,
        #   allowing realtime notification of completed jobs
        self._notify_queue = notify_queue
        self._ready = False

        self._completed_list_lock = threading.Lock()
        self._completed_list = []

        self._backend._set_leet_control(self)
        self.plugin_reload()


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

    # @property
    # def completed_jobs(self):
    #     return

    def _set_finished_job(self, leet_job):
        self._completed_list_lock.acquire()
        self._job_list.remove(leet_job)
        self._completed_list.append(leet_job)
        self._completed_list_lock.release()

    def run(self):
        with self._backend.start() as backend:
            self.ready = True
            while True:
                # try:
                    #code, value = in_queue.get(timeout=10)
                code, value = self._queue.get()
                if code == _LTControl.STOP:
                    break
                elif code == _LTControl.NEW_JOBS:
                    backend.add_tasks(value)
                    self._job_list += value
                elif code == _LTControl.JOB_COMPLETED_NOTIFICATION:
                    self._set_finished_job(value)

                else:
                    #TODO exception
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

    def _notifyjob(self, job):
        self._queue.put((_LTControl.JOB_COMPLETED_NOTIFICATION, job))

    def plugin_reload(self):
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
        self._queue.put((_LTControl.NEW_JOBS, [LeetJob(hostname, plugin) for hostname in hostnames]))


    def close(self):
        self._queue.put((_LTControl.STOP, None))
        self.ready = False
        #self.

    def __enter__(self):
        return self

    def __exit__(self, exeception_type, exception_value, traceback):
        #print(exeception_type, exception_value, traceback)
        self.close()
