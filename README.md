# LEET
Leverage EDR for Execution of Things

## Getting started

### Prerequisites

```
Python >= 3.6
apscheduler
```

For the CLI:

```
tabulate
```

For the Carbon Black backend:

```
cbapi
```

### Installation

Clone the git repository and use pip to manually install it. Pip should download
all the necessary packages.

In the folder where you cloned the respository:

```
pip install .
```

### Backend configuration

It is expected that each backend requires a particular configuration on how to
interface with backend, this may or may not include, server names/IPs, authentication,
tokens, etc.

#### Carbon Black

Right now this is the only backend present. Add the servers, API tokens and, if
necessary, proxy configuration as per instructions on:

- https://cbapi.readthedocs.io/en/latest/getting-started.html
- https://cbapi.readthedocs.io/en/latest/ - Section "API Credentials"

### Usage

After installation, an executable file called `leet_cli` should be present.
Execution of this file from a terminal should start LEET.

#### Observations

LEET not check for anything that is going to be executed on the machines. What
this means is that if a plugin is wants to delete all files from a machine and
the backend allows it, it will delete all the files, no questions asked.

It is highly recommended that you review and test the source code of any plugins
before executing.

#### Examples

TODO

## TODO/Roadmap?

Not in a particular order of importance.

- Replace the plugin system for something more robust
- Do performance tests
- Move CB backend thread pool for the sessions to a process pool (allowing the plugin to perform more cpu intensive tasks)
- Add api support to save results of a plugin to a file
- Add the ability of executing "routines", e.g., a group of plugins, in order
- CLI should also read a job file and configure itself properly
- Find a way to efficiently handle errors from threadpools (cb backend)
- Save jobs to continue later
- Do not wait for a command to be completed once the live response session
  has started, it is more efficient (async?)

## Features

It will persistently and relentlessly try to connect to the endpoint and
do it's best to execute whatever was requested.

## CHANGELOG

### 0.4

- Added support for directory listing on a session
- Normalized error message in case of plugin failure to the interface

### 0.3

- Better defined API
- Better defined error handling by sessions/plugins
- LEET will stop execution if no backend is found
- Added option to enable debug via command line
- Added setup.py
- Fixed a bug when of unclosed threads when LEET was stopped using Ctrl+C

### 0.2

- Changed the application architecture to a more modular design
- Decoupled plugin from backend
- Backend and plugin apis are more simple
- Multiple backends at the same time are supported
- Simplified communication with the user interface
- Code restructuring
- Changed plugin arguments to be based in the argparse module

### 0.1

- Initial commit

## Known problems

TODO

## References:

TODO
