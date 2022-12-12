from abc import ABCMeta
from collections import UserDict
from typing import Callable, Hashable


TAGS = '__intf_tags'

# returns decorator to tag methods
# methods decorated with this will have { 'intf_name': 'tag' } added to their TAGS attr
def interface_tag(intf_name:Hashable):
    def decorator(tag:Hashable=None):
        def wrapped(func:Callable):
            tags = getattr(func, TAGS, {})
            tags[intf_name] = tag if tag else func.__name__
            setattr(func, TAGS, tags)
            return func
        return wrapped
    return decorator

# Object for holding a group of descriptors that share the same interface_group
# Each class will have one TagGroup per unique interface_group added to its definition at instantiation
class InterfaceGroup(UserDict):
    def __init__(self, name) -> None:
        self.name = name
        self._accessing_inst = None
        super().__init__()
        
    def __getitem__(self, key):
        if not (attr := self.data.get(key, None)): return None
        return getattr(attr[0], attr[1]).__get__(self._accessing_inst) if self._accessing_inst else attr
    
    def __setitem__(self, key, item):
        # this brach is used during meta class init
        if type(item) is tuple: return super().__setitem__(key, item)
        
        # replace existing method in interface
        if self._accessing_inst and (attr := self.data.get(key, None)):
            setattr(attr[0], attr[1], item)
            return super().__setitem__(key, (attr[0], attr[1]))
        
        # add a new method to interface
        setattr(self._accessing_inst.__class__, item.__name__, item)
        rval = super().__setitem__(key, (self._accessing_inst.__class__, item.__name__))
        # propagate new method to subclasses
        for cls in type(self._accessing_inst).__subclasses__():
            if not getattr(cls, self.name, None): setattr(cls, self.name, InterfaceGroup(self.name))
            getattr(cls, self.name).update({key: (type(self._accessing_inst), item.__name__)})
        return rval
    
    def __getattr__(self, name):
        if attr := getattr(super(), name, None): return attr
        if not (attr := self.data.get(name, None)):
            raise AttributeError(f"'{type(self._accessing_inst).__name__}' object does not implement '{name}' in the '{self.name}' interface")
        return getattr(attr[0], attr[1]).__get__(self._accessing_inst) if self._accessing_inst else attr
    
    def __get__(self, inst, _):
        self._accessing_inst = inst
        return self


# Interface Group Introspector
# Creates and adds InterfaceGroup to the class definition for every interface_group found in a class during initialization
class IGIMeta(type):
    def __init__(cls, clsname, bases, attrs):
        # add list of groups to class attributes
        tag_groups = []
        setattr(cls, TAGS, tag_groups)
        
        # for each group in base classes, create a new TagGroup object
        for base in bases:
            base_groups = getattr(base, TAGS, [])
            for group_name in base_groups:
                if group_name not in tag_groups:
                    setattr(cls, group_name, InterfaceGroup(group_name))
                    tag_groups.append(group_name)
                # add base class's TagGroup info to our TagGroup
                getattr(cls, group_name).update(getattr(base, group_name))
        
        # search for tagged methods in this class's attributes
        for member in attrs.values():
            method_tags = getattr(member, TAGS, {})
            for group_name, tag in method_tags.items():
                if group_name not in tag_groups:
                    setattr(cls, group_name, InterfaceGroup(group_name))
                    tag_groups.append(group_name)
                getattr(cls, group_name).update({tag: (cls, member.__name__)})
        return super().__init__(clsname, bases, attrs)

# Accessors for InterfaceGroups
class IGI(metaclass=IGIMeta):
    # dictionary style access for InterfaceGroup in a class
    def __getitem__(self, group_name):
        return self.__getattribute__(group_name)
    
    # returns dict of all interface groups as unbounded functions
    @classmethod
    def all_intfs_def(cls):
        return {
            intf: {
                name: getattr(gattr[0], gattr[1], None)
                for name, gattr in getattr(cls, intf, {}).items()
            }
            for intf in getattr(cls, TAGS, [])
        }
    
    # returns specific interface group as unbounded functions
    @classmethod
    def get_intf_def(cls, intf_name, default=None):
        if intf := getattr(cls, intf_name, None):
            return {
                name: getattr(gattr[0], gattr[1], None)
                for name, gattr in intf.items()
            }
        return default
    
    # returns dict of all interface groups as bounded methods
    def all_intfs(self):
        return {
            intf: {
                name: meth
                for name, meth in getattr(self, intf, {}).items()
            }
            for intf in getattr(self, TAGS, [])
        }
    
    # returns specific interface group as bounded method
    def get_intf(self, intf_name, default=None):
        if intf := getattr(self, intf_name, None):
            return {
                name: meth
                for name, meth in intf.items()
            }
        return default

class AIGI(IGIMeta, ABCMeta): pass
