# LEET
Leverage EDR for Execution of Things

## Getting started

### Prerequisites

```
Python >= 3.6
```

For the CLI:

```
tabulate
```

For the Carbon Black backend:

```
apscheduler
cbapi
```

### Installation

```
pip install tabulate apscheduler cbapi
```

Clone the git repository.

### Usage

Run: `python leet.py`

#### Observations

TODO

#### Examples

TODO

## TODO/Roadmap?

Not in a particular order of importance.

- Replace the plugin system for something more robust
- Add API support to multiple backends at the same time
- Create a generic machine info class to be passed to plugins, so more granular
  control can be achieved
- Decouple the backend from the plugin
-- In the mean time, validate plugin backend support
- Do performance tests
- Move CB backend thread pool for the sessions to a process pool (allowing the plugin to perform more cpu intensive tasks)
- Add api support to save results of a plugin to a file
- Add the ability of executing "routines", e.g., a group of plugins, in order
- CLI should also read a job file and configure itself properly
- Find a way to efficiently handle errors from threadpools (cb backend)
- Bubble the error from the plugin/backend to the api
- Save jobs to continue later

## Features

It will persistently and relentlessly try to connect to the endpoint and
do it's best to execute whatever was requested.

## CHANGELOG

- Initial commit

## Known problems

TODO

## References:

TODO
