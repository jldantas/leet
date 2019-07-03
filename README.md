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

```
pip install tabulate apscheduler cbapi
```

Clone the git repository and configure the backends.

### Usage

Run: `python leet_cli.py`

#### Observations

TODO

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

### 0.3

- Better defined API
- Better defined error handling by sessions/plugins
- LEET will stop execution if no backend is found
- Added option to enable debug via command line
- Added setup.py

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
