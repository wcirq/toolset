"""Bound-session, run-local cache. Ambiguous overlaps never become deltas."""
from .qt_history import merge_older


def combine_cache(old, new):
    if not old:
        return list(new)[-1000:], len(new)
    a = [('message', m['text']) for m in old]
    b = [('message', m['text']) for m in new]
    merged = merge_older(a, b)
    if merged is None:
        raise RuntimeError('缓存与新消息未找到唯一重叠，请先重新读取历史建立基线。')
    added = len(merged)-len(a)
    return (list(old) + (list(new[-added:]) if added else []))[-1000:], added


def cache_context(messages):
    return '\n\n'.join('[#%d] %s\n%s' % (len(messages)-i,
        message.get('displayed_time') or '时间未确认', message['text'])
        for i, message in enumerate(messages))
