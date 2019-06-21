# -*- coding: utf-8 -*-
"""This module define all errors that can be throw by LEET. """

class LeetBaseException(Exception):
    """Base class for all LeetException. Shouldn't be used"""
    pass

class LeetError(LeetBaseException):
    """Main error classes that happen within leet. If a more specific error class
    has been defined, it will be used."""
    pass

class LeetPluginError(LeetBaseException):
    """All execeptions caused by a plugin must be of this class."""
    pass

class LeetSessionError(LeetBaseException):
    """If an error in the session occurs, for example, a time out, this is
    the class you are looking for. If the stop flag is set, Leet will not
    try to open this session again"""
    def __init__(self, msg, stop=False):
        super().__init__(msg)
        self.stop = stop

class LeetCommandError(LeetBaseException):
    """If a command within a session fails, this should be raise. """
    pass
