"""可粘贴到 SSKJ Camera Studio 的最小帧插件示例。"""

import cv2


def process(frame, context):
    text = f"SSKJ frame {context['frame_index']}"
    cv2.putText(
        frame, text, (32, 56), cv2.FONT_HERSHEY_SIMPLEX,
        1.0, (80, 213, 183), 2, cv2.LINE_AA,
    )
    return frame
