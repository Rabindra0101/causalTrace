"""Cooperative controls: finish the active operation before pausing or stopping."""
from contextvars import ContextVar
from threading import Condition


class InvestigationStopped(BaseException):
    """Bypass provider-error handlers while allowing worktree finally cleanup."""


class Control:
    def __init__(self):
        self.condition = Condition()
        self.state = 'running'
        self.results = []

    def command(self, action):
        with self.condition:
            if self.state != 'stopping':
                self.state = {'pause':'paused', 'resume':'running', 'stop':'stopping'}[action]
            self.condition.notify_all()
            return self.state

    def checkpoint(self):
        with self.condition:
            while self.state == 'paused':
                self.condition.wait(timeout=1)
            if self.state == 'stopping':
                raise InvestigationStopped()


ACTIVE_CONTROL = ContextVar('investigation_control', default=None)


def checkpoint():
    control = ACTIVE_CONTROL.get()
    if control is not None:
        control.checkpoint()
