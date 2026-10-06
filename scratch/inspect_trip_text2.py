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
    page = context.new_page()
    url = "https://www.trip.com/flights/showfarefirst?dcity=fln&acity=gig&ddate=2026-12-25&triptype=ow&class=y&quantity=1&lowpricesource=searchform"
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(8000)
    text = page.inner_text("body")
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    for i, l in enumerate(lines[30:100], start=30):
        print(f"  [{i}]", l)
    browser.close()
