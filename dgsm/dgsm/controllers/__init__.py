import inspect
import importlib
import os
import dgsm.controllers.implementations as imps
from dgsm.controllers.proc_controller import ProcController
from dgsm.controllers.app_controller import AppController, cmd, stdout_handler
from dgsm.controllers.default_controller import DefaultController


# dictionary of implemented application controllers
# k=ID(string), v=ProcController(concrete implementation)
CONTROLLERS = {}
DEFAULT_ID = 'default'

# inspect a file and return dictionary of implemented ProcControllers found in file
def _collect_controllers_from_file(file_path:str, package=None) -> dict[str,ProcController]:
    if not os.path.isfile(file_path): raise ValueError(f"'{file_path}' must be a path to a file")
    path = os.path.realpath(file_path)
    pkg = f'{package}.' if package else f'{os.path.split(path)[1]}.'
    pkg_file = os.path.splitext(f'{pkg}{path}')[0]

    implemented_controllers = [
        imp for imp in inspect.getmembers(importlib.import_module(pkg_file, package), inspect.isclass)
        if isinstance(imp[1], type(ProcController)) and not inspect.isabstract(imp[1])
    ]
    # return dict { *class.ID()*: *class*, etc. } of all ProcController implementations
    return {
        imp[1].ID().casefold() : imp[1]
        for imp in implemented_controllers
    }

# inspect a directory and return a dictionary of implemented ProcControllers found in directory
def _collect_controllers(path, package=None) -> dict[str,ProcController]:
    ### create list of all files in *path* with extension removed
    if not os.path.exists(path): raise ValueError(f"path: '{path}' does not exist")
    pkg_path = os.path.dirname(os.path.realpath(path)) if os.path.isfile(path) else os.path.realpath(path)
    pkg = f'{package}.' if package else f'{os.path.split(pkg_path)[1]}.'
    pkg_files = [ # list of all files without extension at path
        os.path.splitext(f'{pkg}{f}')[0] for f in os.listdir(pkg_path)
        if os.path.isfile(os.path.join(pkg_path,f))
    ]
    try: pkg_files.remove(f'{pkg}__init__')
    except ValueError: pass

    ### create list of tuples (*class_name*, *class*) of all concrete classes that implement ProcController
    implemented_controllers:list[tuple[str,ProcController]] = []
    for file in pkg_files:
        # add classes to the list if they implement ProcController and are not Abstract
        implemented_controllers.extend([
            imp for imp in inspect.getmembers(importlib.import_module(file, package), inspect.isclass)
            if isinstance(imp[1], type(ProcController)) and not inspect.isabstract(imp[1])
        ])
    # return dict { *class.ID()*: *class*, etc. } of all ProcController implementations
    return {
        imp[1].ID().casefold() : imp[1]
        for imp in implemented_controllers
    }

# remove specified ProcController implementations by id
def remove_controllers(ids:list[str]):
    for id in ids: CONTROLLERS.pop(id, None)

# remove all ProcControllers except the default implementation
def remove_all_controllers():
    remove_controllers([id for id in CONTROLLERS.keys() if id != DEFAULT_ID])

# creates CONTROLLERS dict based on all ProcController implementations found at a given directory or file
def create_controllers_from_path(path:str, package:str=None):
    remove_all_controllers()
    if os.path.isfile(path): CONTROLLERS.update(_collect_controllers_from_file(path, package))
    else: CONTROLLERS.update(_collect_controllers(path, package))

# updates CONTROLLERS dict based on all ProcController implementations found at given directory or file
def update_controllers_from_path(path:str, package:str=None):
    if os.path.isfile(path): CONTROLLERS.update(_collect_controllers_from_file(path, package))
    else: CONTROLLERS.update(_collect_controllers(path, package))

# add single ProcController implementation to CONTROLLERS dict
def add_controller(imp:ProcController):
    if not isinstance(imp, type(ProcController)) or inspect.isabstract(imp):
        raise ValueError(f"imp: '{imp}' must be a concrete implementation of ProcController")
    CONTROLLERS.update({imp.ID(): imp})

# add multiple ProcController implementations to CONTROLLERS dict
def update_controllers(controllers:list[ProcController]):
    for imp in controllers: add_controller(imp)

CONTROLLERS.update(_collect_controllers(imps.__file__, imps.__package__))
add_controller(DefaultController)

__all__ = [
    'CONTROLLERS', 'DEFAULT_ID', 'AppController', 'ProcController', 'cmd', 'stdout_handler',
    'create_controllers_from_path', 'update_controllers_from_path', 'add_controller', 'update_controllers',
    'remove_all_controllers', 'remove_controllers'
]