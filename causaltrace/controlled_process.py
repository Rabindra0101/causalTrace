"""Interruptible subprocess.run equivalent; Docker freezes in the daemon."""
import subprocess
import time
import psutil
from causaltrace.investigation_control import ACTIVE_CONTROL, InvestigationStopped, checkpoint


def _tree(process):
    try:
        root = psutil.Process(process.pid)
        return root.children(recursive=True) + [root]
    except psutil.NoSuchProcess:
        return []


def _kill(process):
    for child in _tree(process):
        try:
            child.kill()
        except psutil.NoSuchProcess:
            pass


def _docker(action, name):
    result = subprocess.run(['docker', action, name] if action != 'rm' else ['docker','rm','-f',name],
                            capture_output=True, timeout=3, check=False)
    return result.returncode == 0


def run(args, *, timeout=None, check=False, capture_output=False, **kwargs):
    control = ACTIVE_CONTROL.get()
    if control is None:
        return subprocess.run(args, timeout=timeout, check=check, capture_output=capture_output, **kwargs)
    checkpoint()
    name = args[args.index('--name')+1] if args[0]=='docker' and '--name' in args else None
    if capture_output:
        kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    input_data = kwargs.pop('input', None)
    if input_data is not None:
        kwargs['stdin'] = subprocess.PIPE
    process = subprocess.Popen(args, **kwargs)
    suspended, frozen = [], False
    complete = None
    active_time, last = 0., time.monotonic()
    control.activity = 'docker' if name else 'process'
    try:
        while True:
            state = control.status()
            now = time.monotonic()
            if state == 'running':
                active_time += now-last
            last = now
            if state == 'stopping':
                raise InvestigationStopped()
            if state == 'paused':
                if name and not frozen and process.poll() is None:
                    frozen = _docker('pause', name)
                elif not name and not suspended and process.poll() is None:
                    for child in _tree(process):
                        try:
                            child.suspend()
                            suspended.append(child)
                        except psutil.NoSuchProcess:
                            pass
                if frozen or suspended or complete is not None:
                    control.pause_effect = 'paused'
            else:
                if frozen:
                    if not _docker('unpause', name):
                        raise RuntimeError('Unable to resume the paused Docker container.')
                    frozen = False
                for child in reversed(suspended):
                    try:
                        child.resume()
                    except psutil.NoSuchProcess:
                        pass
                suspended.clear()
                if complete is not None:
                    break
                if timeout is not None and active_time >= timeout:
                    raise subprocess.TimeoutExpired(args, timeout)
            if complete is None:
                try:
                    complete = process.communicate(input=input_data, timeout=.1)
                except subprocess.TimeoutExpired:
                    pass
                input_data = None
            else:
                time.sleep(.05)
        result = subprocess.CompletedProcess(args, process.returncode, *complete)
        if check:
            result.check_returncode()
        return result
    finally:
        if process.poll() is None or suspended or frozen:
            if name:
                try:
                    _docker('rm', name)
                except (OSError, subprocess.SubprocessError):
                    pass
            _kill(process)
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
        control.activity = 'between_operations'
