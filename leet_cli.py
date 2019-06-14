# LEET
# Leverage EDR for Execution of Things
import time
import logging
import cmd, shlex
import threading, queue
import configparser

import tabulate

import leet.backends.cb
import leet.api
#from leet.base import LeetJob, LeetJobStatus
from leet.errors import LeetPluginError

_LEVEL = logging.DEBUG
_MOD_LOGGER = logging.getLogger(__name__)
_MOD_LOGGER.setLevel(_LEVEL)
_log_handler = logging.StreamHandler()
_log_handler.setLevel(_LEVEL)
_log_handler.setFormatter(logging.Formatter("%(asctime)s - %(threadName)s - %(message)s"))
_MOD_LOGGER.addHandler(_log_handler)

_leet_log = logging.getLogger("leet")
_leet_log.addHandler(_log_handler)
_leet_log.setLevel(_LEVEL)

def pairwise(iterable):
    "s -> (s0, s1), (s2, s3), (s4, s5), ..."
    a = iter(iterable)
    return zip(a, a)

def pretty_print(job):
    print("JobID:", job.id, "\tResult: ", job.status)
    print("--------- Result ----------")
    print(tabulate.tabulate(job.plugin_result.data, headers="keys"))
    #print(job.plugin_result.data)

def pretty_jobs_status(jobs):
    """List of dicts containing 'id, hostname, status'"""
    print(tabulate.tabulate(jobs, headers="keys"))
    #print(job.plugin_result.data)


def _find_cb_profiles():
    """Find all the profiles available in the carbonblack.credentials files.

    Returns:
        list of str: A list with the name of each profile
    """
    config = configparser.ConfigParser(default_section="cbbackend", strict=True)
    config.read(".carbonblack/credentials.response")
    profile_list = [sec_name for sec_name in config.keys() if sec_name != "cbbackend"]
    _MOD_LOGGER.debug("Requested to read 'all' profiles. Found: %s", ",".join(profile_list))

    return profile_list

class LeetTerminal(cmd.Cmd):
    intro = "Starting LEET Terminal. Type '?' or 'help' for help."
    prompt = "LEET> "

    def __init__(self, cb_profiles=["default"]):
        super().__init__()

        self._leet = None
        self._notification_queue = queue.SimpleQueue()
        self.hostname_list = None
        self.plugin = None
        self.backends = self._load_backends(cb_profiles)

        self._notify_thread = threading.Thread(target=self._wait_leet_notification, name="Thr-CLI-Notify")
        self.finished_jobs = []

        #TODO allow backend configuration and setting


    def _load_backends(self, cb_profiles):
        backends = []

        if "all" in cb_profiles:
            profiles = _find_cb_profiles()
        else:
            profiles = cb_profiles
        backends += [leet.backends.cb.Backend(profile) for profile in profiles]

        return backends

    def start_connections(self):
        self._leet = leet.api.Leet(self.backends, self._notification_queue)

        _MOD_LOGGER.debug("Starting CLI monitoring thread")
        self._notify_thread.start()

        self._leet.start()
        _MOD_LOGGER.info("Waiting for LEET to be ready.")
        while not self._leet.ready:
            time.sleep(1)
        _MOD_LOGGER.info("LEET is ready.")

        return self

    def shutdown(self):
        self._leet.shutdown()
        self._notification_queue.put(None)
        self._notify_thread.join()
        self._leet.join()

    def __enter__(self):
        return self.start_connections()

    def __exit__(self, exeception_type, exception_value, traceback):
        """Exit context"""
        self.shutdown()


    def _wait_leet_notification(self):
        while True:
            leet_job = self._notification_queue.get()
            if leet_job is None:
                break
            else:
                LeetTerminal.prompt = "! LEET> "
                finished_jobs.append(leet_job)
                #TODO do something
                # if not self._notified:
                #     print("\nSomething finished. Use 'show' to get the results.")
                #     LeetTerminal.prompt = "! LEET> "
                #     self._notified = True

    def do_machines(self, args):
        """machines host1,host2,host3...
        Set the machines where the job will be executed.
        A list of machines where the job will run, separated by commas or space.
        """
        lex_parser = shlex.shlex(args)
        lex_parser.whitespace += ","

        machine_list = [m for m in lex_parser]
        #TODO check if the hostname has space in it, if yes, invalid.
        if not machine_list:
            print("Invalid. See the help.")
            return False

        self.hostname_list = machine_list
        print(f"Set to run in {len(self.hostname_list)} machines.")

    def print_plugin_list(self):
        pg_list = self._leet.plugin_list

        print("="*40)
        for pg_name in pg_list:
            print(pg_name)
        print("="*40)
        print(f"Total plugins: {len(pg_list)}")
        print("For details on each plugin, try 'help plugin [plugin_name]'")


    def set_plugin(self, parameters):
        plugin_name = parameters.pop(0)

        if len(parameters) % 2:
            #TODO exceptions
            print("Error, invalid number of parameters")
            return

        try:
            plugin = self._leet.get_plugin(plugin_name)
            parameter_dict = {k:v for k,v in pairwise(parameters)}
            #validate the plugin in the most simple way
            plugin.set_param(parameter_dict)
            plugin.check_param()

            self.plugin = plugin

        except KeyError as e:
            print(f"Error, '{plugin_name}' is not a valid plugin")
        except LeetPluginError as e:
            print("Error, plugin parameters are incorrect or missing")

    def do_plugin(self, args):
        """plugin plugin_name [parameters]
        Define the plugin that will run on the job. Get a list a plugins by ***
        plugin_name - the name of the plugin
        parameters - to be passed as name=value or name="value"
        """
        #TODO GET A LIST OF PARAMETERS FROM THE PLUGIN
        lex_parser = shlex.shlex(args.strip(), posix=True)
        lex_parser.whitespace += "="
        lex_parser.escapedquotes = ""
        tokens = [token for token in lex_parser]

        _MOD_LOGGER.debug("Plugin tokens: %s", tokens)

        if len(tokens) < 1:
            print("Error, invalid command.")
            return

        if tokens[0] == "list":
            self.print_plugin_list()
        elif tokens[0] == "set":
            self.set_plugin(tokens[1:])
        else:
            print("Error, invalid command.")

    def help_plugin(self):
        print("\n".join(["plugin list|set|plugin_name",
                    "\tlist - Prints a list of all plugins",
                    "\tset - Set the plugin it will be used. The set command follows the format:",
                    "\t\tplugin set plugin_name [parameters]",
                    "\tplugin_name - Shows the help for the plugin"]))


    # def complete_plugin(self, text, line, begidx, endidx):
    #     print(text, line, begidx, endidx)

    def do_add_job(self, args):

        if self.machine_list is None:
            print("Error, no machines defined. Use the commnad 'machines'")
            return
        if self.plugin is None:
            print("Error, no plugins defined. Use the 'plugin set' command")
            return

        print("********* Job information *********")
        print("***********************************")
        print("Plugin: ", self.plugin.LEET_PG_NAME)
        param = self.plugin.get_plugin_parameters()
        if param is not None:
            print("\tParameters:")
            for p in param:
                print("\t", p.name, "=", p.value)
        print("***********************************")
        print("Amount of machines: ", len(self.machine_list))
        print("Machine list: ", ",".join(self.machine_list))
        print("***********************************")
        print("The job(s) will be sent for processing.")
        confirm = input("Confirm? (y/n) ")
        if confirm.strip().lower() == "y":
            self._leet.start_jobs(self.machine_list, self.plugin)
            #self._leet_queue.put((self.machine_list, self.plugin))

        print("Job scheduled. Cleaning parameters.")
        self.machine_list = None
        self.plugin = None

    def do_show(self, args):
        completed_jobs = self._leet.return_completed_jobs()
        self._notified = False
        LeetTerminal.prompt = "LEET> "

        if completed_jobs:
            for job in completed_jobs:
                pretty_print(job)
        else:
            print("***No jobs have been completed.")

    def do_status(self, args):
        status = self._leet.job_status
        if status:
            pretty_jobs_status(status)
        else:
            print("***No jobs pending")

    def do_cancel_all_jobs(self, args):
        self._leet.cancel_all_jobs()


    def do_exit(self, args):
        self.shutdown()

        return True

    do_EOF = do_exit

    def adv_help_plugin(self, tokens):
        """This function process advanced help for plugins in the format:
        'help plugin <something>'. These can be:
        help plugin list
        help plugin set
        help plugin 'plugin_name'
        """
        options = ["list", "set"] + self._leet.plugin_list
        if len(tokens) > 3 or tokens[2] not in options:
            print("***No help for ", " ".join(tokes))
            return

        if tokens[2] == "list":
            print("TODO help for list")
        if tokens[2] == "set":
            print("TODO help for set")
        else:
            print(self._leet.get_plugin(tokens[2]).get_help())
        pass

    def precmd(self, line):
        lowered = line.lower().strip()
        lex = shlex.shlex(lowered, posix=True)

        lex.escapedquotes = ""
        tokens = [token for token in lex]
        if not tokens: #if nothing is passed
            return lowered

        if tokens[0] == "help" and len(tokens) > 2 and tokens[1] == "plugin":
            self.adv_help_plugin(tokens)
            return ""
        else:
            return lowered

    def do_test(self, line):
        #hostnames = ["US1004511WP", "DESKTOP-90N8EBG"]
        #hostnames = ["DESKTOP-90N8EBG"]
        #hostnames = ["US1004511WP"]
        hostnames = ["SPEEDYTURTLEW10"]

        pg = self._leet.get_plugin("dirlist")
        pg_param = {"path" : "c:\\"}
        #pg_param = {"path" : "c:\\akljsdf"}
        pg.set_param(pg_param)
        self._leet.start_jobs(hostnames, pg)

    def emptyline(self):
        pass


def main():
    cli = LeetTerminal()

    with LeetTerminal() as cli:
            cli.cmdloop()

    # try:
    #     cli.conn_start()
    #     cli.cmdloop()
    # except KeyboardInterrupt:
    #     #TODO if we cancel while still trying to connect?
    #     print("Exiting event loop")
    # # except Exception as e:
    # #     print(e)
    # finally:
    #     cli.close()



#
#TIP when listing directories, tha final backslash is important

# {'last_access_time': 1557479642, 'last_write_time': 1557479621, 'filename': 'pcr1_11.txt', 'create_time': 1557479642, 'attributes': ['ARCHIVE'], 'size': 0}

# ======== SENSOR DATA ==================
    #              boot_id: 0
    #             build_id: 37
    # build_version_string: 006.002.001.81002
    #          clock_delta: 0
    #    computer_dns_name: winwork
    #        computer_name: WINWORK
    #         computer_sid: S-1-5-21-2165326087-2182911670-1483370010
    #               cookie: 330046951
    #              display: True
    #      emet_dump_flags:
    #  emet_exploit_action:  (GPO configured)
    #          emet_is_gpo: False
    #   emet_process_count: 0
    #  emet_report_setting:  (GPO configured)
    #  emet_telemetry_path:
    #         emet_version:
    # event_log_flush_time: None
    #             group_id: 13
    #                   id: 396
    #         is_isolating: False
    #    last_checkin_time: 2019-05-15 13:17:17.073564+00:00
    #          last_update: 2019-05-15 13:17:18.741825+00:00
    #   license_expiration: 1990-01-01 00:00:00+00:00
    #     network_adapters: 192.168.140.6,000c29f277e9|
    # network_isolation_enabled: False
    #    next_checkin_time: 2019-05-15 13:17:47.072763+00:00
    #              node_id: 0
    #                notes: None
    #   num_eventlog_bytes: 6887000
    # num_storefiles_bytes: 0
    # os_environment_display_string: Windows 10 Professional, 64-bit
    #    os_environment_id: 1
    #              os_type: 1
    #       parity_host_id: 0
    # physical_memory_size: 8588865536
    #          power_state: 0
    #    registration_time: 2019-05-15 13:13:47.891765+00:00
    #       restart_queued: False
    # sensor_health_message: Healthy
    # sensor_health_status: 100
    #        sensor_uptime: 213
    #             shard_id: 0
    #               status: Online
    # supports_2nd_gen_modloads: False
    #        supports_cblr: True
    #   supports_isolation: True
    # systemvolume_free_size: 65150107648
    # systemvolume_total_size: 85253419008
    #            uninstall: False
    #          uninstalled: None
    #               uptime: 89063



if __name__ == '__main__':
    main()
