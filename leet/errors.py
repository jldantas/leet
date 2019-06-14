# -*- coding: utf-8 -*-

class LeetBaseException(Exception):
    """Base class for all LeetException"""
    pass

class LeetPluginError(LeetBaseException):
    """Class for all plugin exceptions"""
    #TODO save plugin information
    pass

class LeetSessionError(LeetBaseException):
    def __init__(self, msg, stop=False):
        super().__init__(msg)
        self.stop = stop

class LeetCommandError(LeetBaseException):
    pass

class LeetError(LeetBaseException):
    """Main error classes that happen within leet. If a more specific error class
    has been defined, it will be used."""
    pass
