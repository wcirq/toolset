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


def nickname_candidate(rect, avatars, text_controls, content_rects=()):
    """Conservative layout candidate, not a verified member identity."""
    if len(avatars) != 1:
        return None
    avatar = avatars[0]
    if (avatar[0]+avatar[2])/2 >= rect[0]+(rect[2]-rect[0])*.25:
        return None
    candidates = [item for item in text_controls
                  if avatar[2] <= item['rect'][0] < rect[2]
                  and avatar[1]-4 <= item['rect'][1] <= avatar[1]+12
                  and 0 < item['rect'][3]-item['rect'][1] <= (avatar[3]-avatar[1])*.6
                  and 0 < len(item['text']) <= 80
                  and not TIME_LABEL.fullmatch(item['text'])
                  and not item['text'].startswith(('http://', 'https://'))]
    if not candidates:
        return None
    candidates.sort(key=lambda item: item['rect'][0])
    if candidates[0]['rect'][0] > avatar[2]+80:
        return None
    for left, right in zip(candidates, candidates[1:]):
        if (abs(left['rect'][1]-right['rect'][1]) > 3 or
                not 0 <= right['rect'][0]-left['rect'][2] <= 24):
            return None
    candidate = candidates[0]
    bottom = max(item['rect'][3] for item in candidates)
    bodies = [item['rect'] for item in text_controls if item not in candidates] + list(content_rects)
    if not any(box[1] >= bottom+4 and box[0] >= avatar[2] for box in bodies):
        return None
    if len(candidates) > 1:
        candidate = dict(candidate, text=''.join(item['text'] for item in candidates),
                         objects=[item['object'] for item in candidates],
                         rect=(candidate['rect'][0], candidate['rect'][1], candidates[-1]['rect'][2], bottom))
    return candidate


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
            'sender_name': None, 'message_id': None,
            'direction': {'left': 'incoming', 'right': 'outgoing'}.get(side, 'unknown'),
            'direction_basis': 'user_confirmed_layout' if side != 'unknown' else None,
            'source': 'qt_visible_control'}


def message_context(messages):
    lines = []
    for index, message in enumerate(messages):
        side = {'left': '左侧', 'right': '右侧'}.get(message['layout_side'], '位置未知')
        direction = {'incoming': '对方消息', 'outgoing': '自己消息'}.get(message.get('direction'), '方向未确认')
        member = ('昵称候选：' + message['sender_name_candidate']) if message.get('sender_name_candidate') else '成员身份未解析'
        lines.append('#%d · %s · %s · %s；%s' % (
            message.get('number', len(messages)-index), side,
            message.get('displayed_time') or '时间未确认', direction, member))
    return '\n'.join(lines)
