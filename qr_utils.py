from PIL import Image
from pyzbar.pyzbar import decode
import io
import logging
from typing import Optional

logger = logging.getLogger(__name__)

def decode_qr_image(image_bytes: bytes) -> Optional[str]:
    try:
        image = Image.open(io.BytesIO(image_bytes))
        decoded = decode(image)

        if not decoded:
            return None

        return decoded[0].data.decode("utf-8")

    except Exception as e:
        logger.error(f"QR decode failed: {e}")
        return None
