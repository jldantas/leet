# -*- coding: utf-8 -*-
"""An implementation of using Carbon Black Live Response as a backend.

Basically, this backend structure has:
- One thread in the main class, to monitor the data coming from the instances
- One thread per instance, that interfaces with the CB servers
- One groups of threads per instance, that interfaces with Live response sessions

"""
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

from .base import LeetJobStatus, LeetBackend, LeetError


_MOD_LOGGER = logging.getLogger(__name__)

_CBComms = collections.namedtuple("_CBComms", ("code", "value"))

class _CBCode(enum.Enum):
    """An internal control flag to allow communication between the instances and
    the main backend class. This will always be passed as the first value of a tuple
    and the next values are documented here.

    Control command            | Value
    =======================================
    STOP                      | None
    SEARCH                    | (threading.Event, [], [LeetJob])
    PROCESS                   | _CBTask
    RESCHEDULE                | _CBTask
    FINISHED_NOTIFICATION     | _CBTask
    REMOVE_FROM_LIST          | _CBTask


    A SEARCH command is required when the jobs are submitted and the backend is
        trying to fing the respective sensors.
    A STOP command stops the instances threads for a clean exit
    A PROCESS command starts the execution of a plugin for a specific job
    A RESCHEDULE command happens when the sensor is not online, rescheduling it
        for a later time or when a session is lost in the middle of execution (timeout)
    A FINISHED_NOTIFICATION is triggered if a job has been completed,
        independenlty if the result is success or not. This let's the main backend
        thread know that something finished and inform the api
    A REMOVE_FROM_LIST is used in case of cancellation or error, effectively removing
        the job from the list of things to process
    """
    STOP = 0x0
    SEARCH = 0x1
    PROCESS = 0x2
    RESCHEDULE = 0x3
    FINISHED_NOTIFICATION = 0x4
    REMOVE_FROM_LIST = 0x5

class _CBTask():
    """A simple wrapper to a LeetJob that allows the backend to add relevant
    information for control.

    Attributes:
        leet_job (LeetJob): The leet_job related to the object
        sensor (cbapi.response.Sensor): The sensor where the job will be executed
        cb_instance (_CBInstance): Instance where the sensor can be found

    Returns:
        _CBTask: A new task
    """

    def __init__(self, leet_job, sensor, cb):
        """Returns a new _CBTask object.

        Args:
            leet_job (LeetJob): The LeetJob to be executed
            sensor (cbapi.response.Sensor): The sensor where the job will be executed
            cb_instance (_CBInstance): Instance where the sensor can be found
        """
        self.leet_job = leet_job
        self.sensor = sensor
        self.cb_instance = cb

    def __repr__(self):
        'Return a nicely formatted representation string'
        return (f'{self.__class__.__name__}(leet_job={self.leet_job}, '
                f'sensor={repr(self.sensor)})'
               )

#TODO probably not the best way, will be resource intensive
class _CBInstance(threading.Thread):
    """Connects to one instance of the CB servers, based on the profile and
    handles all the communication to/from the instance. This includes LR
    sessions.
    """

    def __init__(self, profile_name, output_queue, max_sessions):
        """Returns a new object of _CBInstance. The creation of the object
        implies in a connection attempt.

        Once the object has been created, it is necessary to call the method
        'start()'.

        Args:
            profile_name (str): The profile name of the servers, as in the
                "credentials.response" file, that we will connect to
            output_queue (queue.Queue): The queue for communication with the Backend class
            max_sessions (int): the maximum number of live resopnse sessions that
                can exist at the same time.

        Returns:
            _CBInstance: New instance
        """
        super().__init__(name="Thr-" + profile_name)
        self._cb = CbResponseAPI(profile=profile_name)
        self._lr_workers = concurrent.futures.ThreadPoolExecutor(max_workers=max_sessions, thread_name_prefix="Thr-" + profile_name + "-lr-workers")
        self._in_queue = queue.Queue()
        self._out_queue = output_queue

    @property
    def url(self):
        """The Carbon Black server URL"""
        return self._cb.url

    def run(self):
        """Starts the processing of the main queue"""
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
            else:
                #TODO raise error
                pass

            self._in_queue.task_done()

        _MOD_LOGGER.debug("Thread finished.")
        #TODO potential clean up code

    def add_request(self, cb_comms):
        """Add a request to be processed by the instance.

        Args:
            cb_comms (_CBComms): An object of with what the instance will perform
                and the necessary parameters for it to happen. See the _CBCode
                class documentation for valid options
        """
        self._in_queue.put(cb_comms)

    def _execute_task(self, cb_task):
        """Once a machine is available, this function tries to connect via LR
        and execute the plugin. It is also the main coordinator to get the plugin
        result and notify the backed.

        Args:
            cb_task (_CBTask): The task that will be attempted to execute
        """
        try:
            with cb_task.sensor.lr_session() as session:
                _MOD_LOGGER.debug("Session for job %s ready. Starting execution.", cb_task.leet_job.id)
                cb_task.leet_job.executing() #TODO this can raise an exception LeetException.
                results = cb_task.leet_job.plugin_instance.run(session, cb_task.leet_job.hostname)
                if results.success:
                    cb_task.leet_job.plugin_result = results
                    _MOD_LOGGER.debug("Job %s was successful.", cb_task.leet_job.id)
                else:
                    _MOD_LOGGER.debug("Job %s failed.", cb_task.leet_job.id)
                cb_task.leet_job.completed()
                self._out_queue.put(_CBComms(_CBCode.FINISHED_NOTIFICATION, cb_task))
        except cbapi.errors.TimeoutError as e:
            try:
                #if we trigger this exception here, it means we tried an invalid
                #change of status and needs to be removed from the processing list
                self.leet_job.pending()
                self._out_queue.put(_CBComms(_CBCode.RESCHEDULE, cb_task))
            except LeetError as e:
                self._out_queue.put(_CBComms(_CBCode.REMOVE_FROM_LIST, cb_task))
        except cbapi.live_response_api.LiveResponseError as e:
            _MOD_LOGGER.exception(e)
            cb_task.leet_job.error()
            self._out_queue.put(_CBComms(_CBCode.REMOVE_FROM_LIST, cb_task))
        except LeetError as e:
            #print("****** HANDLER 2")
            _MOD_LOGGER.exception(e)
            cb_task.leet_job.error()
            self._out_queue.put(_CBComms(_CBCode.REMOVE_FROM_LIST, cb_task))
        # #TODO! VERY BAD PRACTICE DETECTED. FIND A BETTER WAY TO HANDLE EXCEPTION FROM THREADPOOL
        except Exception as e:
            print("****** HANDLER 3")
            _MOD_LOGGER.exception(e)
            print(e)


    def _get_sensor_most_recent_checkin(self, sensors):
        """Get the most recent sensor from a list of sensors.

        If a sensor has the same hostname (unlikely, but possible), this function
        will return the sensor with the most recent checkin. The ASSUMPTION is that
        if the most recent machine is the correct one. This implies that this
        backend does not support multiple machines with the same hostname.

        Args:
            sensors (list of Sensors): List of sensors to be compared against each
                other
        """
        temp_sensor = None

        for sensor in sensors:
            if temp_sensor is None:
                temp_sensor = sensor
            else:
                if sensor.last_checkin_time > temp_sensor.sensor.last_checkin_time:
                    temp_sensor = sensor

        return temp_sensor

    def get_sensor(self, hostname):
        """Return one or more sensors, given a hostname.

        Args:
            hostname (str): The machine name

        Returns:
            [Sensor]: The list of sensors
        """
        query = "hostname:" + hostname
        sensors = self._cb.select(Sensor).where(query)

        return self._get_sensor_most_recent_checkin(sensors)

    def _search_command(self, t_event, result, tasks):
        """Executes the search command.

        Args:
            t_event (threading.Event): The event that notifies the search has
                been completed
            result (list of _CBTask): List where the sensors will be added
            tasks (list of LeetJob): The list of jobs, and consequently, the machines,
                that are being searched in this instance.
        """
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

class Backend(LeetBackend):
    """Main Carbon Black backend class.

    The main purpose of this class is to interface between the CB servers (using
    the _CBInstance class) and the Leet API and coordinate tasks between the many
    instances.

    To achieve this, it creates all the necessary classes to connect with the
    servers, a schedulers, to check if the machines are online and keeps monitoring
    the output of the instances to check if something changed.

    Attributes:
        enable_solve_conflict (bool): If true, in case a machine is found in multiple
            instances, it will get the one with the earliest checking time and
            proceed with execution. If it is false, the job in conflict will be
            marked as an error.
    """

    def __init__(self, profile_list=["default"], pool_interval=20, max_lr_sessions=10):
        """Creates a new CB Backend instance.

        Connection to the servers are not started until the method start is called
        or the instance is opened in a context manager.

        Args:
            profile_list (list of str): Which intances the backend will try to connect.
                The names should be the same names found on the "credentials.response"
                file. If the special name `all` is present, the credentials file will
                be parsed and the backend will try to connect to all the classes.
                Default is a list with a single entry connecting to the 'default'
                profile.
            pool_interval (int): The amount of time the backen will wait to check
                if a machine is online
            max_lr_sessions (int): The maximum amount of concurrent live response
                sessions, per instance.

        Returns:
            Backend: Instance
        """
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
            self._profile_list = self._find_profiles()
        else:
            self._profile_list = profile_list


    def _find_profiles(self):
        """Find all the profiles available in the carbonblack.credentials files.

        Returns:
            list of str: A list with the name of each profile
        """
        config = configparser.ConfigParser(default_section="cbbackend", strict=True)
        config.read(".carbonblack/credentials.response")
        profile_list = [sec_name for sec_name in config.keys() if sec_name != "cbbackend"]
        _MOD_LOGGER.debug("Requested to read 'all' profiles. Found: %s", ",".join(profile_list))

        return profile_list

    def _monitor_queue(self):
        """Monitor the queue for any communication from the instances"""
        while True:
            code, value = self._in_queue.get()
            if code == _CBCode.RESCHEDULE:
                self._sched.add_job(self._trigger_lr, 'date', args=[value])
            elif code == _CBCode.FINISHED_NOTIFICATION:
                _MOD_LOGGER.debug("CBBackEnd FINISHED_NOTIFICATION for Job %s.", value.leet_job.id)
                self._jobs.pop(value.leet_job.id)
                self.notify_job_completed(value.leet_job)
            elif code == _CBCode.REMOVE_FROM_LIST:
                _MOD_LOGGER.debug("CBBackEnd will no longer process Job %s (REMOVE_FROM_LIST).", value.leet_job.id)
                self._jobs.pop(value.leet_job.id)
            elif code == _CBCode.STOP:
                break
            else:
                _MOD_LOGGER.error("%s - Unknown code %s received.", self._monitor_thread.name, code)

            self._in_queue.task_done()


    def _trigger_lr(self, cb_task):
        """If the machine is available, trigger start of live response. If it is not,
        reschedule the job for the future. This should be called only by the scheduler.

        Args:
            cb_task (_CBTask): The task that will be checked.
        """
        cb_task.sensor.refresh()
        if cb_task.sensor.status == "Online":
            _MOD_LOGGER.debug("Sensor for job %s is Online. Attempting connection.", cb_task.leet_job.id)
            cb_task.cb_instance.add_request(_CBComms(_CBCode.PROCESS, cb_task))
        else:
            if cb_task.leet_job.status != LeetJobStatus.CANCELLED:
                _MOD_LOGGER.debug("Sensor for job %s is Offline. Rescheduling", cb_task.leet_job.id)
                next_exec = datetime.datetime.now() + self._pool_interval
                self._sched.add_job(self._trigger_lr, 'date', run_date=next_exec, args=[cb_task])
            else:
                _MOD_LOGGER.debug("Job %s has been cancelled, remove from the schedule.", cb_task.leet_job.id)
                self._in_queue.put(_CBComms(_CBCode.REMOVE_FROM_LIST, cb_task))


    def _search_machines(self, tasks):
        """Searches for the machines in all instances, wait for the searches
        to complete and return a list of _CBTask.

        It is important to note the search WILL timeout after 30 seconds and
        after that period, searches might be incomplete.

        Args:
            tasks (list of LeetJob): A list of jobs we need to find sensors for

        Returns:
            (list of _CBTask): A list of _CBTask for the machines that were found
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
        #TODO better handling of the timeout

        return result


    def _solve_conflict(self, results):
        """A conflict is defined as a machine be found on different instances.
        The solution is to return the one with the most recent checkin.

        Args:
            results (list of _CBTask): A list of _CBTask where to try and solve
                the conflicts

        Returns:
            (list of _CBTask): A list of _CBTask with the tasks in conflict
                removed
        """
        new_result = []

        for hostname, tasks in itertools.groupby(results, key=lambda x: str.lower(x.leet_job.hostname)):
            list_tasks = list(tasks)
            if len(list_tasks) >= 2 and self.enable_solve_conflict:
                list_tasks.sort(key=lambda x: x.sensor.last_checkin_time, reverse=True)
                _MOD_LOGGER.warning("Machine %s in conflict. Resolution points to usage of instance '%s'.", hostname, list_tasks[0].cb_instance.url)
            elif len(list_tasks) >= 2 and not self.enable_solve_conflict:
                _MOD_LOGGER.warning("Machine %s in conflict. Cancelling job.", hostname)
                list_tasks[0].leet_job.error()
                continue
            new_result.append(list_tasks[0])

        return new_result

    def get_pending_tasks(self):
        """Returns which tasks are still pending for the backend.

        Returns:
            list of LeetJob
        """
        return [cb_task.leet_job for cb_task in self._jobs.values()]

    def add_task(self, task):
        """Add a new task. We just cheat and use the same path as multiple machines.

        Args:
            task (LeetJob): A single job to be executed
        """
        tasks = [task]
        self.add_tasks(tasks)

    def add_tasks(self, tasks):
        """Add a new tasks to be processed by the backend.

        Args:
            tasks (list of LeetJob): Receives a list of LeetJob
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

    def cancel_task(self, task):
        """Must receive a LeetJob"""
        pass

    def start(self):
        """Find the necessary profiles and start a connection with each of them
        and starts the necessary threads.
        """
        if not self._started:
            #create the multiple instances of CB and get them ready
            for profile_name in self._profile_list:
                instance = None
                try:
                    instance = _CBInstance(profile_name, self._in_queue, self._max_lr_sessions)
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
