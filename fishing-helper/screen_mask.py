def mask_overlay(frame, origin_x, origin_y, rectangle):
    """Hide the floating hub from vision/OCR without changing screen pixels."""
    if rectangle is None:
        return frame
    x, y, width, height = rectangle
    left = max(0, x - origin_x)
    top = max(0, y - origin_y)
    right = min(frame.shape[1], x + width - origin_x)
    bottom = min(frame.shape[0], y + height - origin_y)
    if right > left and bottom > top:
        frame[top:bottom, left:right] = 0
    return frame
