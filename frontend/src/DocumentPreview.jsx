import React from 'react'
import { Alert, Button, Space, Spin, Typography } from 'antd'
import api, { apiMessage } from './api'
import { useLanguage } from './i18n'
import './document-preview.css'

// All reads keep the API's session and permission checks. No permanent public URL is created.
function ProtectedDocument({ url, filename, contentType = 'application/pdf', initialPage = 1, downloadUrl }) {
  const { t } = useLanguage()
  const canvas = React.useRef(null)
  const container = React.useRef(null)
  const [document, setDocument] = React.useState(null)
  const [imageUrl, setImageUrl] = React.useState('')
  const [page, setPage] = React.useState(initialPage)
  const [width, setWidth] = React.useState(760)
  const [loading, setLoading] = React.useState(true)
  const [rendering, setRendering] = React.useState(false)
  const [error, setError] = React.useState('')
  const [retry, setRetry] = React.useState(0)
  const protectedUrl = /^\/api\//.test(url || '') ? url : ''

  React.useEffect(() => {
    let active = true, task, loaded, imageObjectUrl
    const controller = new AbortController()
    async function load() {
      try {
        if (!protectedUrl) throw new Error('The document address is unavailable.')
        const response = await api.get(protectedUrl.slice(4), { responseType: 'arraybuffer', signal: controller.signal })
        if (!active) return
        if (contentType === 'application/pdf') {
          const [pdfjs, worker, assets] = await Promise.all([import('pdfjs-dist'), import('pdfjs-dist/build/pdf.worker.min.mjs?url'), import('./pdfAssets')])
          if (!active) return
          pdfjs.GlobalWorkerOptions.workerSrc = worker.default
          task = pdfjs.getDocument({ data: new Uint8Array(response.data), isEvalSupported: false, BinaryDataFactory: assets.LocalPdfDataFactory, useWorkerFetch: false, cMapPacked: true })
          loaded = await task.promise
          if (active) { setDocument(loaded); setPage(Math.max(1, Math.min(initialPage, loaded.numPages))) }
        } else {
          imageObjectUrl = URL.createObjectURL(new Blob([response.data], { type: contentType }))
          if (active) setImageUrl(imageObjectUrl)
        }
      } catch (failure) {
        if (active) setError(failure.response ? apiMessage(failure) : t('This document could not be displayed. Try again, or use the file controls below.'))
      } finally { if (active) setLoading(false) }
    }
    load()
    return () => { active = false; controller.abort(); task?.destroy(); if (imageObjectUrl) URL.revokeObjectURL(imageObjectUrl) }
  }, [protectedUrl, contentType, initialPage, retry, t])

  React.useEffect(() => {
    if (!container.current || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(240, entry.contentRect.width - 24)))
    observer.observe(container.current)
    return () => observer.disconnect()
  }, [])

  React.useEffect(() => {
    if (!document || !canvas.current) return
    let active = true, renderTask
    setRendering(true)
    document.getPage(page).then(async (pdfPage) => {
      if (!active || !canvas.current) return
      const natural = pdfPage.getViewport({ scale: 1 })
      const viewport = pdfPage.getViewport({ scale: Math.min(1.7, width / natural.width) })
      const ratio = Math.min(window.devicePixelRatio || 1, 2), element = canvas.current
      element.width = Math.floor(viewport.width * ratio); element.height = Math.floor(viewport.height * ratio)
      element.style.width = `${viewport.width}px`; element.style.height = `${viewport.height}px`
      renderTask = pdfPage.render({ canvasContext: element.getContext('2d'), viewport, transform: ratio === 1 ? null : [ratio, 0, 0, ratio, 0, 0] })
      await renderTask.promise
    }).catch((failure) => { if (active && failure.name !== 'RenderingCancelledException') setError(t('This page could not be displayed. You can still open or download the original file.')) })
      .finally(() => { if (active) setRendering(false) })
    return () => { active = false; renderTask?.cancel() }
  }, [document, page, width, t])

  return <div className="document-viewer" ref={container}>
    <div className="document-viewer-toolbar"><Space wrap>
      {document && <><Button disabled={page <= 1 || rendering} onClick={() => setPage((value) => value - 1)}>{t('Previous page')}</Button><Typography.Text aria-live="polite">{t('Page {page} of {total}', { page, total: document.numPages })}</Typography.Text><Button disabled={page >= document.numPages || rendering} onClick={() => setPage((value) => value + 1)}>{t('Next page')}</Button></>}
      {protectedUrl && <Button href={`${protectedUrl}#page=${page}`} target="_blank" rel="noreferrer">{t('Open in a new tab')}</Button>}
      {downloadUrl && /^\/api\//.test(downloadUrl) && <Button href={downloadUrl}>{t('Download original')}</Button>}
    </Space></div>
    {error && <Alert type="warning" showIcon message={error} action={<Button onClick={() => { setDocument(null); setImageUrl(''); setError(''); setLoading(true); setRetry((value) => value + 1) }}>{t('Retry')}</Button>} />}
    {loading ? <div className="document-viewer-loading"><Spin tip={t('Loading document')}><div /></Spin></div> : imageUrl ? <img className="attachment-image" src={imageUrl} alt={filename} /> : document && <div className="document-viewer-page" aria-busy={rendering}><canvas ref={canvas} role="img" aria-label={t('{filename}, page {page}', { filename, page })} /></div>}
  </div>
}

export default function DocumentPreview(props) {
  return <ProtectedDocument key={`${props.url}:${props.initialPage || 1}`} {...props} />
}
