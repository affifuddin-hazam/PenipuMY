# image_generator.py
import logging
import os
import jinja2
from playwright.async_api import async_playwright
from typing import Union
from config import TEMPLATE_DIR # Import dari config

logger = logging.getLogger(__name__)

# Setup Jinja2 Environment
try:
    jinja_env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(TEMPLATE_DIR),
        autoescape=jinja2.select_autoescape(['html', 'xml'])
    )
    logger.info(f"Jinja2 environment berjaya dimuatkan dari '{TEMPLATE_DIR}'.")
except Exception as e:
    logger.critical(f"GAGAL muat Jinja2 environment: {e}")
    jinja_env = None

def render_html_template(template_file: str, data: dict) -> str:
    """Render data ke dalam templat HTML guna Jinja2."""
    if not jinja_env:
        raise Exception("Jinja2 environment tidak dimuatkan.")
    
    template = jinja_env.get_template(template_file)
    return template.render(data=data)

async def generate_profile_image(template_file: str, data: dict) -> Union[bytes, None]:
    """
    Render HTML dan guna Playwright untuk 'screenshot' sebagai PNG.
    """
    if not jinja_env:
        logger.error("Ralat: Jinja2 tidak dimuatkan, gagal generate gambar.")
        return None

    try:
        html_content = render_html_template(template_file, data)
        
        async with async_playwright() as p:
            browser = None
            try:
                browser = await p.chromium.launch()
            except Exception:
                logger.warning("Gagal lancar Chromium Playwright. Cuba guna Chrome sedia ada.")
                try:
                    chrome_path = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
                    if not os.path.exists(chrome_path):
                            chrome_path = "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe"

                    if os.path.exists(chrome_path):
                        browser = await p.chromium.launch(
                            channel="chrome",
                            executable_path=chrome_path
                        )
                        logger.info(f"Berjaya lancar Chrome dari: {chrome_path}")
                    else:
                        raise Exception("Path Chrome sedia ada tidak dijumpai.")
                        
                except Exception as e_fallback:
                    logger.error(f"GAGAL LANCAR SEMUA BROWSER. Ralat: {e_fallback}")
                    logger.error("PENTING: Sila jalankan 'playwright install' di terminal anda.")
                    return None
            
            if not browser:
                logger.error("Tidak dapat 'launch' browser. Sila jalankan 'playwright install'.")
                return None

            page = await browser.new_page()
            await page.set_content(html_content)
            card_locator = page.locator("#profile-card")
            screenshot_bytes = await card_locator.screenshot(type="png")
            await browser.close()
            
            return screenshot_bytes

    except jinja2.TemplateNotFound:
        logger.error(f"Ralat: Templat tidak dijumpai: {template_file}")
        return None
    except Exception as e:
        logger.error(f"Ralat semasa generate gambar ({template_file}): {e}")
        return None