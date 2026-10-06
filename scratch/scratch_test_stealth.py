from playwright.sync_api import sync_playwright

def test_stealth():
    with sync_playwright() as p:
        # Try launching with stealth args
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            viewport={"width": 1366, "height": 850},
        )
        # Add stealth script
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = { runtime: {} };
        """)
        
        # Test Trip.com
        page = context.new_page()
        url_trip = "https://www.trip.com/flights/showfarefirst?dcity=fln&acity=gig&ddate=2026-12-25&triptype=ow&class=y&quantity=1&lowpricesource=searchform"
        page.goto(url_trip, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(6000)
        print("Trip.com title:", page.title())
        content_trip = page.content()
        print("Trip.com length:", len(content_trip), "Contains whaleguard:", "whaleguard" in content_trip.lower())
        
        # Test Skyscanner
        page2 = context.new_page()
        url_sky = "https://www.skyscanner.com.br/transporte/passagens-aereas/fln/gig/261225/?adultsv2=1&cabinclass=economy&adults=1&children=0&infants=0"
        page2.goto(url_sky, wait_until="domcontentloaded", timeout=30000)
        page2.wait_for_timeout(6000)
        print("Skyscanner title:", page2.title())
        print("Skyscanner url:", page2.url)
        content_sky = page2.content()
        print("Skyscanner length:", len(content_sky), "Contains captcha/px:", "captcha" in page2.url.lower() or "px" in page2.url.lower())
        
        browser.close()

if __name__ == "__main__":
    test_stealth()
