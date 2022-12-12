import logging
import inspect
import os
import queue
from logging import handlers


### helpers for non-blocking logging ###

# handlers used by queue listener
_q = _q_handler = _listener = None
_handlers = []
@property
def log_handlers():
    return _handlers

# create the queue and default handler
def init_logging(default:bool=True, fname:str=''):
    global _q
    global _q_handler
    if _q: return
    _q = queue.Queue(-1)
    _q_handler = handlers.QueueHandler(_q)

    if default:
        formatter = logging.Formatter(fmt='%(asctime)s - %(levelname)-6s - %(name)s - %(message)s')
        lpath = os.path.join(os.getcwd(), 'logs')
        if not os.path.exists(lpath): os.mkdir(lpath)
        fname = fname if fname else __package__.split(".")[0]
        handler = handlers.TimedRotatingFileHandler(
            filename=os.path.join(lpath, f'{fname}.log'),
            when='H',
            interval=6,
            backupCount=12,
            delay=True
        )
        handler.setFormatter(formatter)
        add_handler(handler)

# create a logger, attach the queue, return the logger
def make_logger(name:str='') -> logging.Logger:
    if not _q_handler: init_logging()
    if not name: name = os.path.basename(inspect.stack()[1].filename)
    _logger = logging.getLogger(name)
    _logger.addHandler(_q_handler)
    _logger.setLevel('INFO')
    return _logger

# removes all current handlers for logger and replaces with q_handler for non-blocking logging
def set_q_handler(logger:logging.Logger):
    if not _q_handler: init_logging()
    for handler in logger.handlers:
        logger.removeHandler(handler)
    logger.addHandler(_q_handler)
    logger.setLevel('INFO')

# add handlers to the listener
def add_handler(handler:logging.Handler) -> None:
    _handlers.append(handler)

# begin the logging thread
def start_logging():
    global _listener
    if _listener: return
    _listener = handlers.QueueListener(_q, *_handlers)
    _listener.start()

def stop_logging():
    global _listener
    _listener.stop()
    _listener = None