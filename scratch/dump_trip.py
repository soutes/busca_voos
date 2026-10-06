from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
    )
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        locale="pt-BR",
        timezone_id="America/Sao_Paulo",
        viewport={"width": 1366, "height": 850},
    )
    context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
    page = context.new_page()
    url = "https://www.trip.com/flights/showfarefirst?dcity=fln&acity=gig&ddate=2026-12-25&triptype=ow&class=y&quantity=1&lowpricesource=searchform"
    page.goto(url, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(3000)
    html = page.content()
    with open("scratch/trip_success.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("Salvo trip_success.html:", len(html))
    browser.close()
