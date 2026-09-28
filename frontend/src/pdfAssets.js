// Bundle the PDF renderer resources locally so Chinese fonts and scanned reports
// work without sending a document or requesting assets from a third-party CDN.
const maps = import.meta.glob('/node_modules/pdfjs-dist/cmaps/*.bcmap', { eager: true, query: '?url&no-inline', import: 'default' })
const fonts = import.meta.glob('/node_modules/pdfjs-dist/standard_fonts/*.{pfb,ttf}', { eager: true, query: '?url&no-inline', import: 'default' })
const decoders = import.meta.glob('/node_modules/pdfjs-dist/wasm/*.wasm', { eager: true, query: '?url&no-inline', import: 'default' })
const assets = Object.fromEntries(Object.entries({ ...maps, ...fonts, ...decoders }).map(([path, url]) => [path.split('/').pop(), url]))

export class LocalPdfDataFactory {
  async fetch({ filename }) {
    const url = assets[filename]
    if (!url) throw new Error('Unsupported PDF rendering resource.')
    const response = await fetch(url)
    if (!response.ok) throw new Error('PDF rendering resource is unavailable.')
    return new Uint8Array(await response.arrayBuffer())
  }
}
