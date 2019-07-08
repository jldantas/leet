# LEET
# Leverage EDR for Execution of Things
import time
import logging
import cmd
import shlex
import threading
import queue
import configparser
import os
import sys
import argparse

import tabulate

import leet.backends.cb
import leet.api
from leet.errors import LeetPluginError

_MOD_LOGGER = logging.getLogger(__name__)

def pairwise(iterable):
    "s -> (s0, s1), (s2, s3), (s4, s5), ..."
    a = iter(iterable)
    return zip(a, a)

def pretty_print(job):
    print("\n")
    print("-"*80)
    print("JobID:", job.id, "\t| Hostname: ", job.machine.hostname, "\t| Result: ", job.status)
    print("--------- Result ----------")
    print(tabulate.tabulate(job.plugin_result, headers="keys"))

def pretty_jobs_status(jobs):
    """List of dicts containing 'id, hostname, status'"""
    print(tabulate.tabulate(jobs, headers="keys"))

def _find_cb_profiles():
    """Find all the profiles available in the carbonblack.credentials files.

    Returns:
        list of str: A list with the name of each profile
    """
    dir_locations = [".carbonblack", os.path.join(os.path.expanduser("~"), ".carbonblack")]
    cred_file = "credentials.response"
    profiles = []

    for dir in dir_locations:
        cred_file_path = os.path.join(dir, cred_file)
        _MOD_LOGGER.debug("Searching CB profiles on '%s'", cred_file_path)
        if os.path.exists(cred_file_path):
            _MOD_LOGGER.debug("File exists, parsing...")
            config = configparser.ConfigParser(default_section="cbbackend", strict=True)
            config.read(cred_file_path)
            profiles += [sec_name for sec_name in config.keys() if sec_name != "cbbackend"]

    if profiles:
        _MOD_LOGGER.debug("Requested to read 'all' profiles. Found: %s", ",".join(profiles))

    return profiles

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
        self._notified = False

        #TODO allow backend configuration and setting


    def _load_backends(self, cb_profiles):
        backends = []

        if "all" in cb_profiles:
            profiles = _find_cb_profiles()
        else:
            profiles = cb_profiles
        backends += [leet.backends.cb.Backend(profile) for profile in profiles]

        if not backends:
            _MOD_LOGGER.error("No backends could be found for usage")
            sys.exit(1)

        return backends

    def start_connections(self):
        self._leet = leet.api.Leet(self.backends, self._notification_queue)

        _MOD_LOGGER.debug("Starting CLI monitoring thread")
        self._notify_thread.start()

        self._leet.start()
        _MOD_LOGGER.info("Waiting for LEET to be ready...")
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
        return self
        #return self.start_connections()

    def __exit__(self, exeception_type, exception_value, traceback):
        """Exit context"""
        self.shutdown()

    def _wait_leet_notification(self):
        while True:
            leet_job = self._notification_queue.get()
            if leet_job is None:
                break
            else:
                self.finished_jobs.append(leet_job)
                if not self._notified:
                    LeetTerminal.prompt = "! LEET> "
                    print("\nSomething finished. Use 'results' to get the results.")
                    self._notified = True

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
            plugin.parse_parameters(parameters)
            self.plugin = plugin
        except LeetPluginError as e:
            print(str(e))

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
        lex_parser.wordchars += "~-./*?="
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
        """Add a job for processing. You will be requested to confirm the addition."""

        if self.hostname_list is None:
            print("Error, no machines defined. Use the commnad 'machines'")
            return
        if self.plugin is None:
            print("Error, no plugins defined. Use the 'plugin set' command")
            return

        print("***********************************")
        print("********* Job information *********")
        print("***********************************")
        print("Plugin: ", self.plugin.LEET_PG_NAME)
        param = self.plugin.get_plugin_parameters()
        if param is not None:
            print("\tParameters:")
            for name, value in param.items():
                print("\t", name, "=", value)
        print("***********************************")
        print("Amount of machines: ", len(self.hostname_list))
        print("Machine list: ", ",".join(self.hostname_list))
        print("***********************************")
        print("The job(s) will be sent for processing.")
        confirm = input("Confirm? (y/n) ")
        if confirm.strip().lower() == "y":
            self._leet.schedule_jobs(self.plugin, self.hostname_list)
            print("Job scheduled. Cleaning parameters.")
            self.hostname_list = None
            self.plugin = None
        else:
            print("Job cancelled.")


    def do_results(self, args):
        """Print all the results"""
        LeetTerminal.prompt = "LEET> "
        self._notified = False

        if self.finished_jobs:
            for job in self.finished_jobs:
                pretty_print(job)
        else:
            print("***No jobs have been completed.")

    def do_status(self, args):
        """Shows a summary of the status of the jobs."""
        status = self._leet.job_status

        for job in self.finished_jobs:
            status.append({"id" : job.id,
                           "hostname" : job.machine.hostname,
                           "plugin": job.plugin_instance.LEET_PG_NAME,
                           "status" : job.status})
        if status:
            pretty_jobs_status(status)
        else:
            print("***No jobs pending")

    def do_cancel_all_jobs(self, args):
        """Cancel all pending jobs"""
        self._leet.cancel_all_jobs()

    def do_exit(self, args):
        """Close the program"""
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
            print("***No help for ", " ".join(tokens))
            return

        if tokens[2] == "list":
            print("TODO help for list")
        elif tokens[2] == "set":
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
        """This has an internal code used for testing. Do not use unless you
        are developing something and changed the code accordingly"""
        #hostnames = ["US1004511WP", "DESKTOP-90N8EBG"]
        hostnames = ["DESKTOP-90N8EBG"]
        #hostnames = ["US1004511WP"]
        #hostnames = ["SPEEDYTURTLEW10"]

        #param = ["--source", "C:\Windows\\system32\\cmd.exe", "--dest", "C:\\tools\\scripts\\cb_test"]
        #pg = self._leet.get_plugin("file_download")
        param = ["--path", "C:\\maintenance"]
        pg = self._leet.get_plugin("dirlist")
        pg.parse_parameters(param)

        self._leet.schedule_jobs(pg, hostnames)

    def emptyline(self):
        pass

def _config_verbose(level):
    #root_logger = logging.getLogger()
    leet_logger = logging.getLogger("leet")
    log_handler = logging.StreamHandler()
    log_handler.setFormatter(logging.Formatter("%(asctime)s - %(threadName)s - %(message)s"))

    leet_logger.addHandler(log_handler)
    leet_logger.setLevel(level)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug messages.")
    args = parser.parse_args()

    if args.verbose:
        _config_verbose(logging.DEBUG)
    else:
        _config_verbose(logging.INFO)

    #cli = LeetTerminal(["all"])
    cli = LeetTerminal(["default"])

    try:
        with cli.start_connections():
                cli.cmdloop()
    except KeyboardInterrupt:
        _MOD_LOGGER.info("Requesting all resources to close. Might take a while. Have faith.")
        cli.shutdown()



if __name__ == '__main__':
    main()
