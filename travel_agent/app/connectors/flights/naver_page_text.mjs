import { existsSync } from 'node:fs'
import { fileURLToPath, pathToFileURL } from 'node:url'
import path from 'node:path'

// 사용법:
//   단일: node naver_page_text.mjs <url> <timeoutSec>
//         -> stdout: {"text": "...", "final_url": "..."}
//   배치: node naver_page_text.mjs --batch <timeoutSec> <concurrency>
//         URL 목록은 stdin(줄바꿈 구분)으로 전달
//         -> stdout: JSONL, 한 줄당 {"url","text","final_url"}
//
// 핵심: 날짜마다 Chrome을 새로 띄우지 않고, 한 번 띄운 브라우저에서 여러 페이지를
// (제한된 동시성으로) 처리한다. 이미지/폰트/미디어는 차단해 렌더링 CPU를 줄인다.

const args = process.argv.slice(2)
const batchMode = args[0] === '--batch'
const timeoutSec = Number((batchMode ? args[1] : args[1]) ?? '35')
const timeoutMs = timeoutSec * 1000
const concurrency = batchMode ? Math.max(1, Math.min(4, Number(args[2] ?? '2'))) : 1

async function readStdinUrls() {
  const chunks = []
  for await (const chunk of process.stdin) chunks.push(chunk)
  return Buffer.concat(chunks)
    .toString('utf-8')
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
}

let urls = []
if (batchMode) {
  urls = await readStdinUrls()
} else {
  if (!args[0]) {
    console.error('source URL is required')
    process.exit(2)
  }
  urls = [args[0]]
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

const executablePath = chromeCandidates.find((candidate) => existsSync(candidate))

if (!executablePath) {
  console.error('Chrome or Edge executable was not found')
  process.exit(2)
}

// CPU 절감: GPU/확장/백그라운드 네트워킹 비활성화 + 이미지 디코딩 끔.
const browser = await chromium.launch({
  executablePath,
  headless: process.env.NAVER_FLIGHT_HEADLESS !== 'false',
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

// 페이지가 운임을 다 그릴 때까지 기다릴 준비조건(소스별로 다름).
function readyPatternFor(targetUrl) {
  if (targetUrl.includes('google.com/travel/flights')) {
    return '₩[\\d,]{3,}\\s*(왕복|편도)'
  }
  // 네이버 항공권
  return '[가-힣A-Za-z,\\s]+(항공|에어)[\\s\\S]{0,500}왕복\\s+[\\d,]+원~'
}

async function extractOne(context, url) {
  const page = await context.newPage()
  try {
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: timeoutMs })
    await page.waitForFunction(
      (pattern) => new RegExp(pattern).test(document.body?.innerText ?? ''),
      readyPatternFor(url),
      { timeout: Math.max(5000, timeoutMs - 5000) },
    )
    await page.waitForTimeout(Math.min(3000, Math.max(800, timeoutMs / 10)))
    const text = await page.locator('body').innerText({ timeout: 5000 })
    return { url, text, final_url: page.url() }
  } catch (error) {
    return { url, text: '', final_url: null, error: String(error?.message ?? error) }
  } finally {
    await page.close()
  }
}

async function runPool(items, limit, worker) {
  const results = new Array(items.length)
  let cursor = 0
  async function next() {
    while (cursor < items.length) {
      const index = cursor++
      results[index] = await worker(items[index])
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, next))
  return results
}

try {
  const context = await browser.newContext({
    locale: 'ko-KR',
    viewport: { width: 1365, height: 920 },
    userAgent:
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
      '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
  })
  await context.route('**/*', (route) => {
    if (BLOCKED_RESOURCES.has(route.request().resourceType())) return route.abort()
    return route.continue()
  })

  const results = await runPool(urls, concurrency, (url) => extractOne(context, url))

  if (batchMode) {
    process.stdout.write(results.map((item) => JSON.stringify(item)).join('\n'))
  } else {
    const first = results[0]
    process.stdout.write(JSON.stringify({ text: first.text, final_url: first.final_url }))
  }
} finally {
  await browser.close()
}
