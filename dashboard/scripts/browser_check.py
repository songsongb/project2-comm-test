"""Optional real Chromium QA. Never opens tel: links or sends emergency reports."""
import argparse
import json
import os
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:8502')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'docs/ui-verification')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    # Optional portable browser/dependencies for restricted Linux QA environments.
    if Path('/tmp/laser-guard-browsers').exists():
        os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', '/tmp/laser-guard-browsers')
    if Path('/tmp/laser-guard-browser-libs').exists():
        os.environ['LD_LIBRARY_PATH'] = '/tmp/laser-guard-browser-libs/usr/lib/x86_64-linux-gnu' + (':' + os.environ['LD_LIBRARY_PATH'] if os.environ.get('LD_LIBRARY_PATH') else '')
    if Path('/tmp/laser-guard-fonts.conf').exists():
        os.environ['FONTCONFIG_FILE'] = '/tmp/laser-guard-fonts.conf'
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
        context = browser.new_context(viewport={'width': 1440, 'height': 1100}, permissions=['clipboard-read', 'clipboard-write'])
        page = context.new_page()
        errors, requests = [], []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('request', lambda r: requests.append(r.url))
        page.goto(args.url)
        page.get_by_role('heading', name='Security Monitoring', exact=True).wait_for(timeout=40000)
        page.get_by_role('radio', name='DMA 성능 분석', exact=True).wait_for(timeout=30000)
        page.get_by_role('combobox').first.click()
        page.get_by_role('option', name='실제 USB Serial', exact=True).click()
        page.get_by_role('button', name='포트 다시 검색', exact=True).wait_for()
        page.screenshot(path=str(args.output / 'security-disconnected.png'), full_page=True)
        assert page.locator('[data-testid="stPlotlyChart"]').count() == 0
        page.get_by_text('DMA 성능 분석', exact=True).click()
        page.get_by_role('heading', name='DMA Performance Lab', exact=True).wait_for()
        page.locator('[data-testid="stPlotlyChart"]').nth(3).wait_for(timeout=20000)
        assert page.locator('[data-testid="stPlotlyChart"]').count() == 4
        page.screenshot(path=str(args.output / 'dma-no-data.png'), full_page=True)
        print('Verified Security/DMA mode switch and four graphs', flush=True)
        # Real expander interaction and explicit DB export/download.
        page.get_by_text('원본 로그 · 다운로드', exact=True).click()
        page.get_by_role('button', name='원본 JSONL 다운로드 준비', exact=True).click()
        page.get_by_role('button', name='원본 JSONL 다운로드', exact=True).wait_for()
        with page.expect_download() as download:
            page.get_by_role('button', name='원본 JSONL 다운로드', exact=True).click()
        assert download.value.suggested_filename == 'raw_live.jsonl'
        print('Verified explicit raw JSONL preparation and browser download', flush=True)
        page.get_by_text('보안 관제', exact=True).click()
        page.get_by_role('combobox').first.click()
        page.get_by_role('option', name='Demo · 합성 데이터', exact=True).click()
        page.get_by_role('button', name='Demo 시작', exact=True).wait_for()
        slider = page.get_by_role('slider').first
        slider.focus()
        slider.press('End')
        page.get_by_role('button', name='Demo 시작', exact=True).click()
        page.wait_for_function("""() => {const t=document.body.innerText;const m=t.match(/재생 (\\d+)\/(\\d+)/);return m && m[1]===m[2] && t.includes('처리 대기 0행')}""", timeout=40000)
        page.get_by_text('경찰 신고 지원 · 112', exact=True).click()
        page.get_by_role('heading', name='경찰 신고 (112)', exact=True).wait_for()
        assert page.locator('a[href="tel:112"]').count() == 0
        assert 'ALARM_BEAM' in page.locator('body').inner_text()
        copy_frame = None
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            copy_frame = next((f for f in page.frames if f.get_by_role('button', name='전화번호 복사', exact=True).count()), None)
            if copy_frame:
                break
            page.wait_for_timeout(100)
        assert copy_frame is not None, 'clipboard component did not finish mounting'
        copy_frame.get_by_role('button', name='전화번호 복사', exact=True).click()
        copy_frame.get_by_text('복사했습니다', exact=True).wait_for(timeout=5000)
        assert page.evaluate('navigator.clipboard.readText()') == '112'
        print('Verified full Demo processing, real alarm history, and 112 clipboard', flush=True)
        page.screenshot(path=str(args.output / 'emergency-demo.png'), full_page=True)
        page.locator('[data-testid="stMain"]').evaluate('(el) => el.scrollTop=0')
        page.screenshot(path=str(args.output / 'security-demo.png'), full_page=True)
        page.get_by_text('DMA 성능 분석', exact=True).click()
        page.locator('[data-testid="stPlotlyChart"]').nth(3).wait_for(timeout=20000)
        page.locator('[data-testid="stMain"]').evaluate('(el) => el.scrollTop=0')
        page.screenshot(path=str(args.output / 'dma-demo.png'), full_page=True)
        page.get_by_text('센서 파형 · TRACE · TRIAL', exact=True).click()
        page.locator('[data-testid="stPlotlyChart"]').nth(5).wait_for(timeout=15000)
        page.screenshot(path=str(args.output / 'sensor-details.png'), full_page=True)
        # Responsive layout: document must not overflow the viewport horizontally.
        widths = {}
        for width in (1440, 768, 390):
            page.set_viewport_size({'width': width, 'height': 1000})
            page.wait_for_timeout(700)
            widths[str(width)] = page.evaluate('({width:innerWidth, document:document.documentElement.scrollWidth})')
            assert widths[str(width)]['document'] <= width + 2
        page.screenshot(path=str(args.output / 'dma-mobile.png'), full_page=True)
        result = {'browser': browser.version, 'errors': errors, 'widths': widths,
                  'real_download': download.value.suggested_filename, 'clipboard': '112 verified',
                  'auto_police_requests': [u for u in requests if u.startswith('tel:') or 'police.go.kr' in u],
                  'result': 'passed', 'notes': 'No telephone link clicked; no manual report submitted.'}
        assert not errors and not result['auto_police_requests']
        (args.output / 'browser-results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        browser.close()


if __name__ == '__main__':
    main()
