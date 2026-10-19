"""Explicit bounded analysis profiles and per-investigation provider usage."""
from contextvars import ContextVar

PROFILES = {
    'standard': {'files':12,'source_chars':100000,'file_chars':30000,'log_chars':40000,'diff_chars':20000,'response_tokens':4000,'timeout':60,'history_runs':32,'failure_groups':20,'reversals':3,'repair_attempts':5},
    'deep': {'files':24,'source_chars':200000,'file_chars':50000,'log_chars':60000,'diff_chars':40000,'response_tokens':8000,'timeout':180,'history_runs':64,'failure_groups':40,'reversals':5,'repair_attempts':10},
}
ACTIVE_PROFILE = ContextVar('analysis_profile',default='standard')
MODEL_USAGE = ContextVar('provider_usage',default=None)

def settings():
    return PROFILES[ACTIVE_PROFILE.get()]

def usage_summary():
    calls=MODEL_USAGE.get() or []
    return {'reported_requests':len(calls), 'prompt_tokens':sum(c['prompt_tokens'] for c in calls),
            'completion_tokens':sum(c['completion_tokens'] for c in calls),
            'total_tokens':sum(c['total_tokens'] for c in calls),
            'note':'Provider-reported token usage only. Not a dollar estimate or an account balance; failed requests can have unavailable usage.'}
