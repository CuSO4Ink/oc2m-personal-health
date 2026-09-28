import { useSyncExternalStore } from 'react'

const packs = import.meta.glob('./locales/*.json', { eager: true, import: 'default' })
const en = new Map(), zh = new Map()
// General copy first; curated feature terminology takes precedence.
const priority = (path) => path.endsWith('/interface.json') ? 0 : path.endsWith('/common.json') ? 1 : 2
for (const [, pack] of Object.entries(packs).sort(([a],[b]) => priority(a)-priority(b))) for (const [source, target] of Object.entries(pack)) {
  if (/[\u3400-\u9fff]/.test(source)) { en.set(source, target); zh.set(target, source) }
  else { zh.set(source, target); en.set(target, source) }
}
const escape = (value) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
function patterns(map) {
  return [...map].filter(([key]) => /\{\w+\}/.test(key)).map(([key, value]) => {
    const names = [...key.matchAll(/\{(\w+)\}/g)].map((item) => item[1])
    return { regex: new RegExp('^' + key.split(/\{\w+\}/g).map(escape).join('(.+?)') + '$'), names, value }
  })
}
const dynamic = { en: patterns(en), zh: patterns(zh) }
let language = 'en'
try { language = localStorage.getItem('health-language') === 'zh' ? 'zh' : 'en' } catch { /* Optional preference. */ }
const listeners = new Set()
export function setLanguage(next) {
  if (!['en', 'zh'].includes(next) || next === language) return
  language = next
  try { localStorage.setItem('health-language', next) } catch { /* Optional preference. */ }
  if (typeof document !== 'undefined') document.documentElement.lang = next === 'zh' ? 'zh-CN' : 'en'
  listeners.forEach((listener) => listener())
}
export function t(value, variables) {
  if (typeof value !== 'string') return value
  const map = language === 'zh' ? zh : en
  let result = map.get(value)
  if (result === undefined) {
    for (const item of dynamic[language]) {
      const match = value.match(item.regex)
      if (match) { result = item.value.replace(/\{(\w+)\}/g, (_, key) => match[item.names.indexOf(key) + 1] || ''); break }
    }
  }
  result ??= value
  return variables ? result.replace(/\{(\w+)\}/g, (match, key) => variables[key] ?? match) : result
}
export function useLanguage() {
  const current = useSyncExternalStore((listener) => { listeners.add(listener); return () => listeners.delete(listener) }, () => language, () => 'en')
  return { language: current, setLanguage, t }
}
