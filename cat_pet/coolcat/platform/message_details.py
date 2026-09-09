"""Separate observed layout from unverified sender identity."""
import re


TIME_LABEL = re.compile(r'(?:(?:\d{2,4}[-年/.]\d{1,2}[-月/.]\d{1,2}日?|昨天|今天|星期[一二三四五六日天])\s*)?\d{1,2}:\d{2}')


def enrich_messages(records, messages):
    """Keep displayed time context verbatim; never invent a precise timestamp."""
    result, time_label, index = [], None, 0
    total = sum(kind == 'message' for kind, _ in records)
    for kind, text in records:
        if kind != 'message':
            # Retraction/other labels must not become a timestamp.
            if TIME_LABEL.fullmatch(text.strip()):
                time_label = text.strip()
            continue
        detail = dict(messages[index])
        index += 1
        detail.update(number=total-index+1, displayed_time=time_label,
                      timestamp=None, links=re.findall(r'https?://[^\s<>]+', text),
                      content_kind='unsupported' if text == '[非文本消息或暂不支持的消息类型]' else 'text')
        result.append(detail)
    return result


def describe_message(text, rect, avatars):
    side = 'unknown'
    if len(avatars) == 1 and rect[2] > rect[0]:
        avatar = avatars[0]
        center = (avatar[0] + avatar[2]) / 2
        width = rect[2] - rect[0]
        if center < rect[0] + width * .25:
            side = 'left'
        elif center > rect[2] - width * .25:
            side = 'right'
    return {'text': text, 'layout_side': side, 'sender_id': None,
            'sender_name': None, 'message_id': None, 'direction': 'unknown',
            'source': 'qt_visible_control'}


def message_context(messages):
    lines = []
    for index, message in enumerate(messages):
        side = {'left': '左侧', 'right': '右侧'}.get(message['layout_side'], '位置未知')
        lines.append('#%d · %s · %s · 发送人未确认' % (
            message.get('number', len(messages)-index), side,
            message.get('displayed_time') or '时间未确认'))
    return '\n'.join(lines)
