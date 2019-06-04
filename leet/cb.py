import configparser
import logging
import threading
import queue
import collections
import enum
import itertools
import datetime
import concurrent.futures

#pip install apscheduler
from apscheduler.schedulers.background import BackgroundScheduler

#pip install cbapi
from cbapi.response import Process, CbResponseAPI, Sensor
from cbapi.response.models import Sensor as CB_Sensor
import cbapi.errors

from .base import LeetJobStatus, LeetBackend

_MOD_LOGGER = logging.getLogger(__name__)

_CBComms = collections.namedtuple("_CBComms", ("code", "value"))

class _CBCode(enum.Enum):
    """
    A SEARCH command value is a tuple composed of: (_search_command)
        - An event sync mechanism per thread
        - A common list for data return
        - A list of LeetJob
        * Returns a list of _CBTask iwth sensor and cb correctly filled

    A STOP command value is always None.

    A PROCESS command value is a _CBTask

    A RESCHEDULE command sends a _CBTask back to schedule
        - value is _CBTask

    A FINISHED_NOTIFICATION is to notify the main manager that something is done
        - value is a _CBTask

    """
    STOP = 0x0
    SEARCH = 0x1
    PROCESS = 0x2
    RESCHEDULE = 0x3
    FINISHED_NOTIFICATION = 0x4

class _CBTask():
    def __init__(self, leet_job, sensor, cb):
        self.leet_job = leet_job
        self.sensor = sensor
        self.cb_instance = cb

    def __repr__(self):
        'Return a nicely formatted representation string'
        return (f'{self.__class__.__name__}(leet_job={self.leet_job}, '
                f'sensor={repr(self.sensor)})'
               )

#TODO probably not the best way, will be resource intensive
class _CB_Instance(threading.Thread):
    _WAIT_TIMEOUT = 10

    def __init__(self, profile_name, output_queue, max_sessions):
        super().__init__(name="Thr-" + profile_name)
        self._cb = CbResponseAPI(profile=profile_name)
        self._lr_workers = concurrent.futures.ThreadPoolExecutor(max_workers=max_sessions, thread_name_prefix="Thr-lr-workers")
        self._in_queue = queue.Queue()
        self._out_queue = output_queue

    @property
    def url(self):
        return self._cb.url

    def run(self):
        _MOD_LOGGER.debug("Starting thread for cb instance")
        while True:

            code, value = self._in_queue.get()
            if code == _CBCode.SEARCH:
                _MOD_LOGGER.debug("Search request for %d machines....", len(value[2]))
                self._search_command(*value)
            if code == _CBCode.STOP:
                _MOD_LOGGER.debug("Stopping threads.")
                _MOD_LOGGER.debug("Waiting LR related threads.")
                self._lr_workers.shutdown()
                break
            if code == _CBCode.PROCESS:
                self._lr_workers.submit(self._execute_task, value) #does not block, so it is fine

            self._in_queue.task_done()


        _MOD_LOGGER.debug("Thread finished.")
        #TODO potential clean up code

    def add_request(self, cb_comms):
        self._in_queue.put(cb_comms)

    def _execute_task(self, cb_task):
        try:
            with cb_task.sensor.lr_session() as session:
                _MOD_LOGGER.debug("Session for job %s ready. Starting execution.", cb_task.leet_job.id)
                cb_task.leet_job.status = LeetJobStatus.EXECUTING
                results = cb_task.leet_job.plugin_instance.run(session, cb_task.leet_job.hostname)

                if results.success:
                    cb_task.leet_job.plugin_result = results
                    cb_task.leet_job.status = LeetJobStatus.SUCCESS
                    _MOD_LOGGER.debug("Job %s was successful.", cb_task.leet_job.id)
                else:
                    cb_task.leet_job.status = LeetJobStatus.FAILURE
                    _MOD_LOGGER.debug("Job %s failed.", cb_task.leet_job.id)
                self._out_queue.put(_CBComms(_CBCode.FINISHED_NOTIFICATION, cb_task))
        except cbapi.errors.TimeoutError as e:
            self.leet_job.status = LeetJobStatus.PENDING_NEWATTEMPT
            self._out_queue.put(_CBComms(_CBCode.RESCHEDULE, cb_task))



    def _get_sensor_most_recent_checkin(self, sensors):
        """of a list of same sensors, returns the one with the most recent checkin"""
        temp_sensor = None

        for sensor in sensors:
            if temp_sensor is None:
                temp_sensor = sensor
            else:
                if sensor.last_checkin_time > temp_sensor.sensor.last_checkin_time:
                    temp_sensor = sensor

        return temp_sensor

    def get_sensor(self, hostname):
        query = "hostname:" + hostname
        sensors = self._cb.select(Sensor).where(query)

        return self._get_sensor_most_recent_checkin(sensors)

    def _search_command(self, t_event, result, tasks):
        i = 0
        for task in tasks:
            sensor = self.get_sensor(task.hostname)
            if sensor is not None:
                i += 1
                cb_task = _CBTask(task, sensor, self)
                result.append(cb_task)
        _MOD_LOGGER.debug("Search finished. %d/%d found in this instance.", i, len(tasks))
        _MOD_LOGGER.debug("This instance has finished searching.")
        t_event.set()



class CBBackEnd(LeetBackend):
    """Interfaces with the CB api and manages the connection with multiple
    instances of the servers"""

    def __init__(self, profile_list=["default"], pool_interval=20, max_lr_sessions=10):
        super().__init__("cb")

        self._threads = []  #threads for instances, one per instance
        self._in_queue = queue.Queue()
        self._sched = BackgroundScheduler()
        #TODO can we use the threads themselves to check if things were started?
        self._started = False
        #solving conflict algorithm is basically get the earliest checkin
        self.enable_solve_conflict = False
        self._max_lr_sessions = max_lr_sessions
        #TODO a property to allow control of the pool_interval
        self._pool_interval = datetime.timedelta(seconds=pool_interval)
        self._monitor_thread = threading.Thread(target=self._monitor_queue, name="Thr-monitor")

        self._jobs = {}

        # if there is a profile called all, load all profiles
        if "all" in profile_list:
            self.profile_list = self._find_profiles()
        else:
            self._profile_list = profile_list


    def _find_profiles(self):
        """Find all the profiles available in the carbonblack credentials files."""
        config = configparser.ConfigParser(default_section="cbbackend", strict=True)
        config.read(".carbonblack/credentials.response")
        profile_list = [sec_name for sec_name in config.keys() if sec_name != "cbbackend"]
        _MOD_LOGGER.debug("Requested to read 'all' profiles. Found: %s", ",".join(profile_list))

        return profile_list



    def _monitor_queue(self):
        while True:
            code, value = self._in_queue.get()
            if code == _CBCode.RESCHEDULE:
                self._sched.add_job(self._trigger_lr, 'date', args=[value])
            elif code == _CBCode.FINISHED_NOTIFICATION:
                _MOD_LOGGER.debug("CBBackEnd FINISHED_NOTIFICATION for Job %s.", value.leet_job.id)
                self._jobs.pop(value.leet_job.id)
                self.notify_job_completed(value.leet_job)
            elif code == _CBCode.STOP:
                break
            else:
                _MOD_LOGGER.error("%s - Unknown code %s received.", self._monitor_thread.name, code)

            self._in_queue.task_done()


    def _trigger_lr(self, cb_task):
        """If the machine is available, trigger start of live response. If it is not,
        reschedule the job for the future. This should be called only by the scheduler.
        """
        cb_task.sensor.refresh()
        if cb_task.sensor.status == "Online":
            _MOD_LOGGER.debug("Sensor for job %s is Online. Attempting connection.", cb_task.leet_job.id)
            cb_task.cb_instance.add_request(_CBComms(_CBCode.PROCESS, cb_task))
        else:
            _MOD_LOGGER.debug("Sensor for job %s is Offline. Rescheduling", cb_task.leet_job.id)
            next_exec = datetime.datetime.now() + self._pool_interval
            self._sched.add_job(self._trigger_lr, 'date', run_date=next_exec, args=[cb_task])


    def _search_machines(self, tasks):
        """
        Searches for the machines in all instances, wait for the answer and return

        Receives a list of LeetJob
        Returns a list of _CBTask
        """
        t_events = []
        result = []
        t_status = set()

        _MOD_LOGGER.debug("Searching in all instances for the machines...")
        for i in range(len(self._threads)):
            t_events.append(threading.Event())
            self._threads[i].add_request(_CBComms(_CBCode.SEARCH, (t_events[-1], result, tasks)))

        _MOD_LOGGER.debug("Waiting for searches to complete...")
        t_status.add(t_events[0].wait(30))
        for i in range(1, len(self._threads)):
            t_status.add(t_events[i].wait(1))
        _MOD_LOGGER.debug("Search completed.")
        #TODO if t_status has a false, we have a search problem and need to recover

        return result


    def _solve_conflict(self, results):
        """A conflict is defined as a machine be found on different instances.
        The solution is to return the one with the most recent checkin.

        Result is a list of _CBTask sorted by hostname
        """
        new_result = []

        for hostname, tasks in itertools.groupby(results, key=lambda x: str.lower(x.leet_job.hostname)):
            list_tasks = list(tasks)
            if len(list_tasks) >= 2 and self.enable_solve_conflict:
                list_tasks.sort(key=lambda x: x.sensor.last_checkin_time, reverse=True)
                _MOD_LOGGER.warning("Machine %s in conflict. Resolution points to usage of instance '%s'.", hostname, list_tasks[0].cb_instance.url)
            elif len(list_tasks) >= 2 and not self.enable_solve_conflict:
                _MOD_LOGGER.warning("Machine %s in conflict. Cancelling job.", hostname)
                list_tasks[0].leet_job.status = LeetJobStatus.ERROR
                continue
            new_result.append(list_tasks[0])

        return new_result

    def get_pending_tasks(self):
        return [cb_task.leet_job for cb_task in self._jobs.values()]



    def add_tasks(self, tasks):
        """Add a new tasks to be processed by the backend.

        Receives a list of LeetJob
        """
        result = self._search_machines(tasks)

        result.sort(key=lambda x: str.lower(x.leet_job.hostname))
        if len(result) > len(tasks):
            _MOD_LOGGER.warning("More machines than expected were found. Handling conflicts...")
            result = self._solve_conflict(result)
        elif len(result) < len(tasks):
            _MOD_LOGGER.warning("Not all machines found. We are going to execute only to the found machines.")

        for cb_task in result:
            _MOD_LOGGER.debug("Adding %s to schedule.", cb_task.leet_job.id)
            self._jobs[cb_task.leet_job.id] = cb_task
            self._sched.add_job(self._trigger_lr, 'date', args=[cb_task])

    def start(self):
        """Find the necessary profiles and start a connection with each of them.
        and starts the necessary threads.
        """
        if not self._started:
            #create the multiple instances of CB and get them ready
            for profile_name in self._profile_list:
                instance = None
                try:
                    instance = _CB_Instance(profile_name, self._in_queue, self._max_lr_sessions)
                    self._threads.append(instance)
                    _MOD_LOGGER.info("Successfully connected to profile [%s]", profile_name)
                except cbapi.errors.ApiError as e:
                    _MOD_LOGGER.error("! Connection failed with profile %s", profile_name)
                    _MOD_LOGGER.exception(e)

            #start the instance threads
            [thread.start() for thread in self._threads]
            #starts the scheduler
            self._sched.start()
            #starts the monitoring thread
            self._monitor_thread.start()

            self._started = True

        return self

    def close(self):
        """Clean all the resources related to the backend. If you are not going
        to use the context manager, this MUST be called manually at the end of
        the code.
        """
        if self._started:
            _MOD_LOGGER.debug("Requesting all threads to close... ")
            #closes the scheduler threads
            self._sched.shutdown()
            #closes the _monitor_thread
            self._in_queue.put(_CBComms(_CBCode.STOP, None))
            #closes all instace threads
            [thread.add_request(_CBComms(_CBCode.STOP, None)) for thread in self._threads]
            _MOD_LOGGER.debug("Waiting for threads...")
            [thread.join() for thread in self._threads]
            self._monitor_thread.join()
            _MOD_LOGGER.debug("All internal threads have been closed.")
            self._started = False

    def __enter__(self):
        return self.start()

    def __exit__(self, exeception_type, exception_value, traceback):
        #print(exeception_type, exception_value, traceback)
        self.close()
