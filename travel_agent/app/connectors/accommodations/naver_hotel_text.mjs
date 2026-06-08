import { existsSync } from 'node:fs'
import { fileURLToPath, pathToFileURL } from 'node:url'
import path from 'node:path'

const sourceUrl = process.argv[2]
const timeoutMs = Number(process.argv[3] ?? '30') * 1000

if (!sourceUrl) {
  console.error('source URL is required')
  process.exit(2)
}

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../..')
const playwrightUrl = pathToFileURL(
  path.join(repoRoot, 'frontend/node_modules/playwright-core/index.mjs'),
).href
const { chromium } = await import(playwrightUrl)

const chromeCandidates = [
  process.env.CHROME_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
].filter(Boolean)
const executablePath = chromeCandidates.find((c) => existsSync(c))
if (!executablePath) {
  console.error('Chrome or Edge executable was not found')
  process.exit(2)
}

// CPU 절감: GPU/확장/백그라운드 네트워킹 비활성화 + 이미지 디코딩 끔.
const browser = await chromium.launch({
  executablePath,
  headless: process.env.NAVER_HOTEL_HEADLESS !== 'false',
  args: [
    '--no-sandbox',
    '--disable-dev-shm-usage',
    '--disable-gpu',
    '--disable-extensions',
    '--disable-background-networking',
    '--blink-settings=imagesEnabled=false',
  ],
})
const BLOCKED_RESOURCES = new Set(['image', 'media', 'font'])
try {
  const page = await browser.newPage({
    locale: 'ko-KR',
    viewport: { width: 1365, height: 920 },
    userAgent:
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
      '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
  })
  // 호텔명·가격·평점은 텍스트라 이미지/폰트/미디어는 받지 않아도 된다(렌더링 CPU↓).
  await page.route('**/*', (route) => {
    if (BLOCKED_RESOURCES.has(route.request().resourceType())) return route.abort()
    return route.continue()
  })
  await page.goto(sourceUrl, { waitUntil: 'domcontentloaded', timeout: timeoutMs })
  try {
    await page.waitForLoadState('networkidle', { timeout: Math.max(8000, timeoutMs - 8000) })
  } catch {}
  await page.waitForTimeout(3500)
  const text = await page.locator('body').innerText({ timeout: 5000 })
  process.stdout.write(JSON.stringify({ text, final_url: page.url() }))
} finally {
  await browser.close()
}
