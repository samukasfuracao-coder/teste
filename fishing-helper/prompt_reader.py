"""Read small collection labels without shrinking their text on small windows."""
import cv2

from vision_text import has_collect, has_disconnect


def prompt_crop(image):
    height, width = image.shape[:2]
    crop = image[int(height * .25):int(height * .65),
                 int(width * .35):int(width * .65)]
    scale = max(2.0, min(4.0, 960 / max(1, crop.shape[1])))
    return cv2.resize(crop, None, fx=scale, fy=scale,
                      interpolation=cv2.INTER_CUBIC)


def read_central_prompt(ocr, image, phase):
    crop = prompt_crop(image)
    results, _ = ocr(crop)
    found = has_collect(results)
    disconnected = has_disconnect(results)
    # Retry the small pale label separately from the fish name and scenery.
    # During collection, every negative reading must pass this second check
    # so an OCR miss is less likely to be mistaken for a completed pickup.
    if not found and (image.shape[1] < 1200 or phase in ('collecting', 'waiting_collect')):
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        contrast = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
        alternate, _ = ocr(cv2.cvtColor(contrast, cv2.COLOR_GRAY2BGR))
        found = has_collect(alternate)
        disconnected = disconnected or has_disconnect(alternate)
    return found, disconnected
