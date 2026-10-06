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
    url = "https://br.trip.com/flights/showfarefirst?dcity=fln&acity=gig&ddate=2026-12-25&triptype=ow&class=y&quantity=1&locale=pt-BR&curr=BRL"
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(6000)
    
    info = page.evaluate("""() => {
        const cards = [];
        const els = document.querySelectorAll('[class*="result-item"], [class*="flt-card"]');
        for (const el of els) {
            const txt = el.innerText || '';
            if (txt.includes('R$') || txt.includes('US$') || txt.includes('BRL')) {
                cards.push(txt.substring(0, 120).replace(/\\n/g, ' '));
            }
        }
        return cards;
    }""")
    print("Found cards with BRL / R$:", len(info))
    for c in info[:5]:
        print(" >", c)
    browser.close()
