import { existsSync } from 'node:fs'
import { fileURLToPath, pathToFileURL } from 'node:url'
import path from 'node:path'

// 호텔명으로 구글 호텔 상세를 열어 객실 목록 텍스트를 가져온다(침대 타입 확인용).
// 배치: node google_hotel_rooms.mjs --batch <timeoutSec> <concurrency>
//   stdin: 검색 URL(호텔명) 한 줄당 하나
//   stdout: JSONL {"url","text","final_url"}

const args = process.argv.slice(2)
const batchMode = args[0] === '--batch'
const timeoutMs = Number(args[1] ?? '30') * 1000
const concurrency = batchMode ? Math.max(1, Math.min(4, Number(args[2] ?? '3'))) : 1

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
} else if (args[0]) {
  urls = [args[0]]
} else {
  console.error('url required')
  process.exit(2)
}

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../..')
const { chromium } = await import(
  pathToFileURL(path.join(repoRoot, 'frontend/node_modules/playwright-core/index.mjs')).href
)
const chromeCandidates = [
  process.env.CHROME_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
].filter(Boolean)
const executablePath = chromeCandidates.find((c) => existsSync(c))
if (!executablePath) {
  console.error('Chrome or Edge executable was not found')
  process.exit(2)
}

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
    '--disable-blink-features=AutomationControlled',
  ],
})
const BLOCKED = new Set(['image', 'media', 'font'])

async function extractOne(context, url) {
  const page = await context.newPage()
  try {
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: timeoutMs })
    try {
      await page.waitForFunction(
        () => /(룸|객실|room|침대)/i.test(document.body?.innerText ?? ''),
        undefined,
        { timeout: Math.max(6000, timeoutMs - 6000) },
      )
    } catch {}
    await page.waitForTimeout(2500)
    const text = await page.locator('body').innerText({ timeout: 6000 })
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
    viewport: { width: 1366, height: 900 },
    userAgent:
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
      '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
  })
  await context.route('**/*', (route) =>
    BLOCKED.has(route.request().resourceType()) ? route.abort() : route.continue(),
  )
  const results = await runPool(urls, concurrency, (url) => extractOne(context, url))
  process.stdout.write(results.map((item) => JSON.stringify(item)).join('\n'))
} finally {
  await browser.close()
}
