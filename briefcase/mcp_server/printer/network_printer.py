"""Network thermal printer implementation."""

from escpos.printer import Network
from escpos.exceptions import Error as EscposError
from PIL import Image
import logging

logger = logging.getLogger(__name__)


class NetworkPrinter:
    """Network thermal printer using python-escpos."""

    def __init__(self, host: str, port: int = 9100):
        self.host = host
        self.port = port
        self._printer = None

    def _connect(self):
        """Establish fresh network connection."""
        try:
            self._printer = Network(self.host, self.port)
        except Exception as e:
            logger.error(f"Network printer connection failed: {e}")
            raise

    def test_connection(self) -> bool:
        """Test if printer is accessible."""
        try:
            self._connect()
            self._printer.close()
            return True
        except Exception as e:
            logger.error(f"Printer connection test failed: {e}")
            return False

    def print_image(self, image: Image.Image) -> dict:
        """Print a PIL Image to the thermal printer."""
        try:
            self._connect()
            self._printer.image(image, impl='bitImageColumn')
            self._printer.cut()

            try:
                self._printer.close()
            except:
                pass
            self._printer = None

            return {"status": "success", "message": "Image printed and paper cut"}

        except EscposError as e:
            return {"status": "error", "message": f"Printer error: {str(e)}"}
        except Exception as e:
            return {"status": "error", "message": f"Print failed: {str(e)}"}
