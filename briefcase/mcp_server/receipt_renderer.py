"""Receipt rendering module - HTML to Image conversion."""

from pathlib import Path
from typing import Optional
from PIL import Image
from jinja2 import Environment, FileSystemLoader
import logging

logger = logging.getLogger(__name__)


class RenderingError(Exception):
    """Raised when receipt rendering fails."""
    pass


class ReceiptRenderer:
    """Renders HTML templates to PNG images for thermal printing."""

    def __init__(self, width_px: int = 576):
        template_dir = Path(__file__).parent / "templates"
        self.jinja_env = Environment(loader=FileSystemLoader(str(template_dir)))
        self.width_px = width_px

    def _crop_to_content(self, image: Image.Image) -> Image.Image:
        """Crop image to remove excess whitespace at bottom."""
        gray = image.convert('L')
        pixels = gray.load()

        last_content_row = image.height - 1
        for y in range(image.height - 1, -1, -1):
            for x in range(image.width):
                if pixels[x, y] < 250:
                    last_content_row = y
                    break
            else:
                continue
            break

        last_content_row = min(last_content_row + 20, image.height - 1)
        return image.crop((0, 0, image.width, last_content_row + 1))

    def render_html_to_image(self, html: str, width_px: Optional[int] = None) -> Image.Image:
        """Convert HTML string to PIL Image.

        Tries in order:
        1. imgkit (wkhtmltoimage) - fastest, best quality
        2. Selenium (headless Chrome) - fallback
        """
        if width_px is None:
            width_px = self.width_px

        # Try imgkit first
        try:
            import imgkit
            from io import BytesIO

            options = {
                'format': 'png',
                'width': width_px,
                'quality': 100,
                'enable-local-file-access': None,
            }
            img_bytes = imgkit.from_string(html, False, options=options)
            image = Image.open(BytesIO(img_bytes))
            return image

        except (ImportError, OSError, Exception) as e:
            logger.warning(f"imgkit not available: {e}, trying Selenium")

        # Selenium fallback
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from io import BytesIO
            import base64

            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager

            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument(f'--window-size={width_px},10000')

            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            html_encoded = base64.b64encode(html.encode('utf-8')).decode('utf-8')
            driver.get(f"data:text/html;base64,{html_encoded}")
            screenshot = driver.get_screenshot_as_png()
            driver.quit()

            image = Image.open(BytesIO(screenshot))
            image = self._crop_to_content(image)
            return image

        except Exception as e:
            logger.error(f"Selenium fallback failed: {e}")

        raise RenderingError(
            "All rendering methods failed. Install wkhtmltopdf (brew install wkhtmltopdf) "
            "or Selenium + chromedriver."
        )

    def render_template(self, template_name: str, **context) -> str:
        """Render Jinja2 template with context."""
        template = self.jinja_env.get_template(template_name)
        return template.render(**context)

    def render_template_to_image(self, template_name: str, **context) -> Image.Image:
        """Convenience: render template and convert to image."""
        html = self.render_template(template_name, **context)
        return self.render_html_to_image(html)
