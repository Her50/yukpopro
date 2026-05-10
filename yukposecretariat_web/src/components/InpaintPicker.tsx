/**
 * PUSH-4 — InpaintPicker : retouche d'image par zone masquée (Flux Fill).
 *
 * Workflow :
 *   1. Utilisateur uploade une image (PNG/JPEG, ≤ 2K) ou la passe en prop.
 *   2. Peint au pinceau la ZONE à modifier (masque blanc sur transparent).
 *   3. Tape le prompt ("ajoute un logo", "change le fond en bleu",
 *      "supprime cette personne").
 *   4. Clic Inpaint → POST /bureau/infographie-pro/inpaint avec
 *      image_b64 + mask_b64 + prompt.
 *   5. Reçoit le PNG retouché, l'affiche, peut le re-télécharger.
 *
 * Outils : pinceau (taille slider), gomme, reset, undo (stack canvas snapshots).
 * Mobile-friendly : événements pointer (touch + souris).
 */
import { useEffect, useRef, useState } from 'react'
import { Loader2, Brush, Eraser, Undo2, RotateCcw, Wand2, Download } from 'lucide-react'
import toast from 'react-hot-toast'
import { infographieProAPI } from '../api/client'

interface Props {
  /** Source image as data URL (data:image/png;base64,...) ou URL distante. */
  initialImage?: string
  onResult?: (resultB64: string) => void
}

type Tool = 'brush' | 'eraser'

export default function InpaintPicker({ initialImage, onResult }: Props) {
  const [imageDataUrl, setImageDataUrl] = useState<string | null>(initialImage ?? null)
  const [prompt, setPrompt] = useState('')
  const [tool, setTool] = useState<Tool>('brush')
  const [brushSize, setBrushSize] = useState(40)
  const [strength, setStrength] = useState(0.85)
  const [busy, setBusy] = useState(false)
  const [resultB64, setResultB64] = useState<string | null>(null)
  const [imgDims, setImgDims] = useState<{ w: number; h: number } | null>(null)

  const imgCanvasRef = useRef<HTMLCanvasElement>(null)
  const maskCanvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const drawingRef = useRef(false)
  const lastPointRef = useRef<{ x: number; y: number } | null>(null)
  const undoStackRef = useRef<ImageData[]>([])

  // Charge l'image source dans le canvas + setup masque.
  useEffect(() => {
    if (!imageDataUrl || !imgCanvasRef.current || !maskCanvasRef.current) return
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => {
      const maxW = 800
      const ratio = Math.min(1, maxW / img.width)
      const w = Math.round(img.width * ratio)
      const h = Math.round(img.height * ratio)
      setImgDims({ w, h })
      const ic = imgCanvasRef.current!
      const mc = maskCanvasRef.current!
      ic.width = w; ic.height = h
      mc.width = w; mc.height = h
      ic.getContext('2d')!.drawImage(img, 0, 0, w, h)
      mc.getContext('2d')!.clearRect(0, 0, w, h)
      undoStackRef.current = []
    }
    img.onerror = () => toast.error('Impossible de charger l\'image source')
    img.src = imageDataUrl
  }, [imageDataUrl])

  const onUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (!f) return
    const reader = new FileReader()
    reader.onload = () => setImageDataUrl(reader.result as string)
    reader.readAsDataURL(f)
  }

  // ── Dessin sur le masque (pinceau / gomme) ─────────────────────────────
  const getPointerPos = (evt: React.PointerEvent<HTMLCanvasElement>) => {
    const rect = (evt.target as HTMLCanvasElement).getBoundingClientRect()
    return {
      x: ((evt.clientX - rect.left) / rect.width) * (maskCanvasRef.current?.width ?? 1),
      y: ((evt.clientY - rect.top) / rect.height) * (maskCanvasRef.current?.height ?? 1),
    }
  }

  const beginDraw = (evt: React.PointerEvent<HTMLCanvasElement>) => {
    if (!maskCanvasRef.current) return
    drawingRef.current = true
    const ctx = maskCanvasRef.current.getContext('2d')!
    // Snapshot pour undo
    undoStackRef.current.push(ctx.getImageData(0, 0, maskCanvasRef.current.width, maskCanvasRef.current.height))
    if (undoStackRef.current.length > 30) undoStackRef.current.shift()
    lastPointRef.current = getPointerPos(evt)
    drawAt(evt)
  }

  const drawAt = (evt: React.PointerEvent<HTMLCanvasElement>) => {
    if (!drawingRef.current || !maskCanvasRef.current) return
    const ctx = maskCanvasRef.current.getContext('2d')!
    const p = getPointerPos(evt)
    const last = lastPointRef.current ?? p
    ctx.lineWidth = brushSize
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'
    if (tool === 'brush') {
      ctx.globalCompositeOperation = 'source-over'
      ctx.strokeStyle = 'rgba(255,255,255,0.9)'
    } else {
      ctx.globalCompositeOperation = 'destination-out'
      ctx.strokeStyle = 'rgba(0,0,0,1)'
    }
    ctx.beginPath()
    ctx.moveTo(last.x, last.y)
    ctx.lineTo(p.x, p.y)
    ctx.stroke()
    lastPointRef.current = p
  }

  const endDraw = () => { drawingRef.current = false; lastPointRef.current = null }

  const undo = () => {
    if (!maskCanvasRef.current || undoStackRef.current.length === 0) return
    const ctx = maskCanvasRef.current.getContext('2d')!
    const snap = undoStackRef.current.pop()!
    ctx.putImageData(snap, 0, 0)
  }

  const reset = () => {
    if (!maskCanvasRef.current) return
    const ctx = maskCanvasRef.current.getContext('2d')!
    ctx.clearRect(0, 0, maskCanvasRef.current.width, maskCanvasRef.current.height)
    undoStackRef.current = []
  }

  // ── Convertit le masque canvas en PNG noir/blanc pour Flux Fill ───────
  // Format attendu par fal.ai : PNG où BLANC = zone à modifier, NOIR = zone
  // à conserver. On lit le canvas et on binarise alpha → blanc, sinon noir.
  const buildMaskPng = (): string | null => {
    if (!maskCanvasRef.current) return null
    const src = maskCanvasRef.current
    const tmp = document.createElement('canvas')
    tmp.width = src.width; tmp.height = src.height
    const tctx = tmp.getContext('2d')!
    // Fond noir puis on copie alpha source en blanc
    tctx.fillStyle = '#000000'
    tctx.fillRect(0, 0, tmp.width, tmp.height)
    const srcData = src.getContext('2d')!.getImageData(0, 0, src.width, src.height)
    const dstData = tctx.getImageData(0, 0, tmp.width, tmp.height)
    for (let i = 0; i < srcData.data.length; i += 4) {
      const alpha = srcData.data[i + 3]
      if (alpha > 32) {
        dstData.data[i] = 255
        dstData.data[i + 1] = 255
        dstData.data[i + 2] = 255
        dstData.data[i + 3] = 255
      }
    }
    tctx.putImageData(dstData, 0, 0)
    return tmp.toDataURL('image/png')
  }

  const lancerInpaint = async () => {
    if (!imageDataUrl) { toast.error('Charge une image source'); return }
    if (!prompt.trim()) { toast.error('Décris la modification à appliquer'); return }
    const maskUri = buildMaskPng()
    if (!maskUri) { toast.error('Masque non généré'); return }

    setBusy(true); setResultB64(null)
    try {
      const r = await infographieProAPI.inpaint({
        image_b64: imageDataUrl,
        mask_b64: maskUri,
        prompt: prompt.trim(),
        strength,
        accepter_cout: true,
      })
      const b64 = (r.data as { png_base64?: string }).png_base64 || ''
      if (!b64) throw new Error('Réponse vide du backend')
      setResultB64(b64)
      onResult?.(b64)
      toast.success('Retouche appliquée')
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      if (e?.response?.status === 402 ||
          (typeof detail === 'string' && detail.includes('CREDITS_EPUISES'))) {
        toast.error('Crédits insuffisants. Recharger pour continuer.', { duration: 6000 })
      } else {
        toast.error(detail || e?.message || 'Inpainting échoué')
      }
    } finally { setBusy(false) }
  }

  const downloadResult = () => {
    if (!resultB64) return
    const bytes = atob(resultB64)
    const arr = new Uint8Array(bytes.length)
    for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i)
    const url = URL.createObjectURL(new Blob([arr], { type: 'image/png' }))
    const a = document.createElement('a')
    a.href = url; a.download = `inpaint_${Date.now()}.png`; a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-3">
      <div className="bg-fuchsia-50 border border-fuchsia-200 rounded-xl p-3 space-y-1">
        <p className="text-sm font-bold text-fuchsia-900">🪄 Retouche par zone (Flux Fill)</p>
        <p className="text-[11px] text-fuchsia-800">
          Peins la zone à modifier au pinceau, décris ce que tu veux à la place,
          clique Appliquer. Idéal : changer un logo, supprimer un objet,
          ajouter un élément, remplacer un fond.
        </p>
      </div>

      {!imageDataUrl && (
        <div className="border-2 border-dashed border-gray-300 rounded-xl p-6 text-center cursor-pointer hover:border-fuchsia-400 hover:bg-fuchsia-50"
             onClick={() => fileInputRef.current?.click()}>
          <p className="text-sm text-gray-500">Clique pour charger une image (PNG/JPEG)</p>
          <input ref={fileInputRef} type="file" accept="image/*" className="hidden"
                 onChange={onUpload} />
        </div>
      )}

      {imageDataUrl && imgDims && (
        <>
          <div ref={containerRef}
               className="relative inline-block max-w-full bg-gray-50 border border-gray-200 rounded-xl overflow-hidden"
               style={{ width: imgDims.w, maxWidth: '100%' }}>
            <canvas ref={imgCanvasRef}
                    className="block max-w-full h-auto"
                    style={{ width: '100%', height: 'auto' }} />
            <canvas ref={maskCanvasRef}
                    className="absolute top-0 left-0 cursor-crosshair touch-none"
                    style={{ width: '100%', height: '100%',
                             mixBlendMode: 'screen', opacity: 0.55,
                             background: 'transparent' }}
                    onPointerDown={beginDraw}
                    onPointerMove={drawAt}
                    onPointerUp={endDraw}
                    onPointerLeave={endDraw} />
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button onClick={() => setTool('brush')} type="button"
                    className={`p-2 rounded-lg border ${tool === 'brush'
                      ? 'bg-fuchsia-600 text-white border-fuchsia-700'
                      : 'bg-white text-gray-700 border-gray-300'}`}
                    title="Pinceau (peindre la zone à modifier)">
              <Brush size={16} />
            </button>
            <button onClick={() => setTool('eraser')} type="button"
                    className={`p-2 rounded-lg border ${tool === 'eraser'
                      ? 'bg-fuchsia-600 text-white border-fuchsia-700'
                      : 'bg-white text-gray-700 border-gray-300'}`}
                    title="Gomme">
              <Eraser size={16} />
            </button>
            <button onClick={undo} type="button"
                    className="p-2 rounded-lg border bg-white text-gray-700 border-gray-300"
                    title="Annuler dernier trait">
              <Undo2 size={16} />
            </button>
            <button onClick={reset} type="button"
                    className="p-2 rounded-lg border bg-white text-gray-700 border-gray-300"
                    title="Effacer tout le masque">
              <RotateCcw size={16} />
            </button>
            <label className="flex items-center gap-1 text-xs text-gray-700 ml-2">
              <span>Pinceau</span>
              <input type="range" min={4} max={200} value={brushSize}
                     onChange={e => setBrushSize(parseInt(e.target.value))}
                     className="w-24 accent-fuchsia-500" />
              <span className="tabular-nums w-8 text-right">{brushSize}</span>
            </label>
            <label className="flex items-center gap-1 text-xs text-gray-700">
              <span>Force</span>
              <input type="range" min={0} max={100} value={Math.round(strength * 100)}
                     onChange={e => setStrength(parseInt(e.target.value) / 100)}
                     className="w-24 accent-fuchsia-500" />
              <span className="tabular-nums w-8 text-right">{Math.round(strength * 100)}%</span>
            </label>
            <button onClick={() => { setImageDataUrl(null); setResultB64(null) }} type="button"
                    className="ml-auto text-xs text-gray-500 hover:text-gray-700 underline">
              Changer d'image
            </button>
          </div>

          <textarea value={prompt} onChange={e => setPrompt(e.target.value)} rows={2}
                    placeholder="Ex : remplace par un ciel coucher de soleil orangé, ajoute un drapeau Cameroun en haut à droite, supprime la voiture rouge…"
                    className="w-full border border-gray-300 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-fuchsia-500 resize-none" />

          <button onClick={lancerInpaint} disabled={busy || !prompt.trim()}
                  className="w-full bg-fuchsia-600 hover:bg-fuchsia-700 disabled:opacity-50 text-white font-semibold py-2.5 rounded-xl flex items-center justify-center gap-2">
            {busy ? <Loader2 size={16} className="animate-spin" /> : <Wand2 size={16} />}
            {busy ? 'Retouche en cours…' : 'Appliquer la retouche'}
          </button>

          {resultB64 && (
            <div className="space-y-2 bg-emerald-50 border border-emerald-200 rounded-xl p-3">
              <p className="text-xs font-bold text-emerald-900">✓ Résultat</p>
              <img src={`data:image/png;base64,${resultB64}`} alt="Résultat inpaint"
                   className="max-w-full rounded border border-emerald-100" />
              <div className="flex gap-2">
                <button onClick={downloadResult}
                        className="bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-medium px-3 py-1.5 rounded-lg flex items-center gap-1">
                  <Download size={12} /> Télécharger PNG
                </button>
                <button onClick={() => { setImageDataUrl(`data:image/png;base64,${resultB64}`); setResultB64(null) }}
                        className="bg-fuchsia-100 hover:bg-fuchsia-200 text-fuchsia-800 text-xs font-medium px-3 py-1.5 rounded-lg">
                  Itérer sur ce résultat
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
