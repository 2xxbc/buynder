import { useState, useRef, useEffect } from 'react'
import { apiFetch } from '../config'
import CardImage from '../components/CardImage'
import { btn, field, label } from '../components/ui'

// Card numbers are written "4", "004" or "4/102" depending on the source — compare just the number
const cardNo = n => String(n || '').split('/')[0].replace(/^0+(?=.)/, '').toLowerCase()
const setKey = s => (s || '').toLowerCase().replace(/[^a-z0-9]/g, '')

// Scan matches come from pokemontcg.io. Find the same card in PokeTrace (same number, same or
// similar set name) so it can be saved like every other card. Returns null if there's no clear match.
function findPoketraceMatch(card, results) {
  const sameNo = results.filter(r => r.poketrace_id && cardNo(r.number) === cardNo(card.number))
  const set = setKey(card.set?.name)
  return sameNo.find(r => setKey(r.set_name) === set)
    || sameNo.find(r => set && (setKey(r.set_name).includes(set) || set.includes(setKey(r.set_name))))
    || null
}

// Tip text color on the dark overlay above the video
const TIP_COLOR = { neutral: 'text-chalk', warn: 'text-butter-deep', good: 'text-up-bright' }

function Scanner() {
  const [scanning, setScanning] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [savingId, setSavingId] = useState(null)
  const [preview, setPreview] = useState('')
  const [cameraOn, setCameraOn] = useState(false)
  const [cameras, setCameras] = useState([])
  const [selectedCamera, setSelectedCamera] = useState('')
  const [tip, setTip] = useState('Hold card inside the box')
  const [tipTone, setTipTone] = useState('neutral')
  const videoRef = useRef(null)
  const canvasRef = useRef(null)
  const analyzeCanvasRef = useRef(null)
  const streamRef = useRef(null)
  const tipIntervalRef = useRef(null)

  useEffect(() => {
    return () => {
      stopCamera()
      if (tipIntervalRef.current) clearInterval(tipIntervalRef.current)
    }
  }, [])

  async function loadCameras() {
    try {
      const tempStream = await navigator.mediaDevices.getUserMedia({ video: true })
      tempStream.getTracks().forEach(track => track.stop())
      const devices = await navigator.mediaDevices.enumerateDevices()
      const videoDevices = devices.filter(d => d.kind === 'videoinput')
      setCameras(videoDevices)
      if (videoDevices.length > 0 && !selectedCamera) {
        setSelectedCamera(videoDevices[0].deviceId)
        return videoDevices[0].deviceId
      }
      return selectedCamera
    } catch (err) {
      setError('Could not access camera: ' + err.message)
      return null
    }
  }

  async function startCamera(deviceId) {
    setError('')
    setResult(null)
    setPreview('')
    let useId = deviceId || selectedCamera
    if (!useId) {
      useId = await loadCameras()
      if (!useId) return
    }
    setCameraOn(true)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { deviceId: { exact: useId } }
      })
      streamRef.current = stream
      if (videoRef.current) {
        videoRef.current.srcObject = stream
      }
      tipIntervalRef.current = setInterval(analyzeFrame, 700)
    } catch (err) {
      setCameraOn(false)
      setError('Could not access camera: ' + err.message)
    }
  }

  function stopCamera() {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop())
      streamRef.current = null
    }
    if (tipIntervalRef.current) {
      clearInterval(tipIntervalRef.current)
      tipIntervalRef.current = null
    }
    setCameraOn(false)
  }

  async function switchCamera(newDeviceId) {
    setSelectedCamera(newDeviceId)
    if (cameraOn) {
      stopCamera()
      setTimeout(() => startCamera(newDeviceId), 200)
    }
  }

  function analyzeFrame() {
    const video = videoRef.current
    const canvas = analyzeCanvasRef.current
    if (!video || !canvas || video.videoWidth === 0) return

    canvas.width = 100
    canvas.height = 140
    const ctx = canvas.getContext('2d')

    const cropX = video.videoWidth * 0.25
    const cropY = video.videoHeight * 0.15
    const cropW = video.videoWidth * 0.5
    const cropH = video.videoHeight * 0.7
    ctx.drawImage(video, cropX, cropY, cropW, cropH, 0, 0, 100, 140)

    const imageData = ctx.getImageData(0, 0, 100, 140)
    const data = imageData.data

    let totalBrightness = 0
    let edgeCount = 0
    let prevBrightness = 0

    for (let i = 0; i < data.length; i += 4) {
      const brightness = (data[i] + data[i + 1] + data[i + 2]) / 3
      totalBrightness += brightness
      if (i > 0 && Math.abs(brightness - prevBrightness) > 30) edgeCount++
      prevBrightness = brightness
    }

    const avgBrightness = totalBrightness / (data.length / 4)
    const sharpness = edgeCount / (data.length / 4)

    if (avgBrightness < 60) {
      setTip('Too dark — add more light')
      setTipTone('warn')
    } else if (avgBrightness > 220) {
      setTip('Too bright — reduce glare or move light away')
      setTipTone('warn')
    } else if (sharpness < 0.05) {
      setTip('Looks blurry — hold steady or move closer')
      setTipTone('warn')
    } else if (sharpness > 0.4) {
      setTip('Too busy — center card on a plain background')
      setTipTone('warn')
    } else {
      setTip('Looks good — snap when ready')
      setTipTone('good')
    }
  }

  function snapPhoto() {
    if (!videoRef.current || !canvasRef.current) return
    const video = videoRef.current
    const canvas = canvasRef.current
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    canvas.getContext('2d').drawImage(video, 0, 0)
    canvas.toBlob(blob => {
      stopCamera()
      const file = new File([blob], 'snap.png', { type: 'image/png' })
      handleFile(file)
    })
  }

  function handleFile(file) {
    if (!file) return
    setPreview(URL.createObjectURL(file))
    setScanning(true)
    setError('')
    setResult(null)
    const formData = new FormData()
    formData.append('image', file)
    apiFetch('/scan-card', {
      method: 'POST',
      body: formData
    })
      .then(res => res.json())
      .then(data => {
        setScanning(false)
        if (data.error) setError(data.error)
        else setResult(data)
      })
      .catch(err => {
        setScanning(false)
        setError('Scan failed: ' + err.message)
      })
  }

  // Same save as the Market search: look the card up in PokeTrace, then /save-card-poketrace
  async function saveCard(card) {
    setSavingId(card.id)
    try {
      const res = await apiFetch(`/poketrace-search/${encodeURIComponent(card.name)}`)
      const data = await res.json()
      const match = findPoketraceMatch(card, data.results || [])
      if (!match) {
        alert(`Couldn't find this exact ${card.name} in our price data. Try searching for it on the Market.`)
        return
      }
      const saved = await (await apiFetch(`/save-card-poketrace/${encodeURIComponent(match.poketrace_id)}`)).json()
      if (saved.success) alert(`Added ${saved.name || card.name} to your watchlist!`)
      else alert(saved.error || 'Could not add this card. Please try again.')
    } catch {
      alert('Could not add this card. Please try again.')
    } finally {
      setSavingId(null)
    }
  }

  return (
    <>
      <h1 className="font-display text-3xl sm:text-4xl font-semibold tracking-tight">Scan a card</h1>
      <p className="text-chalk-soft mt-2 mb-6 max-w-2xl">
        Use your webcam, take a phone photo, or upload an image. Hold the card flat, centered and well lit for best results.
      </p>

      <section className="glass rounded-panel p-5 sm:p-6 mb-8">
        {!cameraOn && (
          <div className="flex flex-col sm:flex-row gap-3">
            <button type="button" onClick={() => startCamera()} className={`${btn.primary} flex-1 py-3.5`}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5" aria-hidden="true">
                <path d="M23 7l-7 5 7 5V7z" /><rect x="1" y="5" width="15" height="14" rx="2" />
              </svg>
              Use webcam
            </button>
            {/* The file input stays focusable (sr-only, not hidden) so keyboard users can reach it */}
            <label className={`${btn.secondary} flex-1 py-3.5 cursor-pointer focus-within:outline-2 focus-within:outline-offset-[3px] focus-within:outline-chalk`}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5" aria-hidden="true">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><path d="M17 8l-5-5-5 5" /><path d="M12 3v12" />
              </svg>
              Upload or take a photo
              <input
                type="file"
                accept="image/*"
                className="sr-only"
                onChange={e => handleFile(e.target.files[0])}
              />
            </label>
          </div>
        )}

        {cameraOn && (
          <div>
            {cameras.length > 1 && (
              <div className="mb-4 max-w-sm">
                <label htmlFor="camera-select" className={label}>Camera</label>
                <select id="camera-select" value={selectedCamera} onChange={e => switchCamera(e.target.value)} className={field}>
                  {cameras.map((cam, i) => (
                    <option key={cam.deviceId} value={cam.deviceId}>
                      {cam.label || `Camera ${i + 1}`}
                    </option>
                  ))}
                </select>
              </div>
            )}

            <div className="relative max-w-2xl overflow-hidden rounded-[20px] bg-chalk">
              <video
                ref={videoRef}
                autoPlay
                playsInline
                className="w-full"
              />
              {/* Card-shaped guide box; the shadow darkens everything outside it */}
              <div
                className="absolute pointer-events-none border-2 border-butter/80 rounded-[14px] shadow-[0_0_0_9999px_rgb(23_21_15/0.45)]"
                style={{ top: '15%', left: '25%', width: '50%', height: '70%' }}
              />
              <div className="absolute top-3 left-1/2 -translate-x-1/2 max-w-[90%] bg-chalk/90 px-4 py-2 rounded-full">
                <p aria-live="polite" className={`text-sm font-semibold text-center ${TIP_COLOR[tipTone]}`}>{tip}</p>
              </div>
            </div>

            <div className="flex gap-3 mt-4 max-w-2xl">
              <button type="button" onClick={snapPhoto} className={`${btn.primary} flex-1`}>Snap photo</button>
              <button type="button" onClick={stopCamera} className={`${btn.secondary} flex-1`}>Cancel</button>
            </div>

            <div className="mt-5 text-sm text-chalk-soft">
              <p className="font-semibold text-chalk mb-1">Tips for best results</p>
              <ul className="list-disc pl-5 space-y-1">
                <li>Place the card flat on a plain dark surface</li>
                <li>Use even lighting, no flash</li>
                <li>Fill the box with the card, top of the card at the top</li>
                <li>Holo cards may not scan well, so try matte cards first</li>
              </ul>
            </div>
          </div>
        )}
      </section>

      <canvas ref={canvasRef} className="hidden" />
      <canvas ref={analyzeCanvasRef} className="hidden" />

      {preview && !cameraOn && (
        <section className="glass rounded-panel p-5 sm:p-6 mb-8">
          <h2 className="font-semibold mb-3">Your image</h2>
          {/* The user's own photo (any shape), so a plain img rather than CardImage */}
          <img src={preview} alt="Your uploaded card" className="max-w-full sm:max-w-sm max-h-96 rounded-[14px]" />
        </section>
      )}

      {scanning && (
        <div className="glass rounded-panel p-6 mb-8 text-center" role="status">
          <p className="text-chalk-soft">Scanning…</p>
        </div>
      )}

      {error && (
        <div className="rounded-panel bg-chalk/[0.06] border border-down-bright/30 p-5 sm:p-6 mb-8" role="alert">
          <p className="font-semibold text-down-bright">Something went wrong</p>
          <p className="text-sm text-chalk mt-1">{error}</p>
        </div>
      )}

      {result && (
        <>
          <section className="glass rounded-panel p-5 sm:p-6 mb-6">
            <p className="text-sm text-chalk-soft">Detected name</p>
            <p className="font-display text-2xl font-semibold mt-1 break-words">{result.detected_name}</p>
          </section>

          <h2 className="font-display text-xl font-semibold mb-4">Matches</h2>

          {result.matches.length === 0 ? (
            <p className="text-chalk-soft">No cards found with that name. Try a clearer photo.</p>
          ) : (
            <ul className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 sm:gap-4">
              {result.matches.map(card => (
                <li key={card.id} className="glass rounded-[20px] p-3 sm:p-4 flex flex-col">
                  <CardImage src={card.images?.small} alt={card.name} className="w-full mb-3" />
                  <p className="font-semibold truncate">{card.name}</p>
                  <p className="text-sm text-chalk-soft mb-3 truncate">{card.set?.name}</p>
                  <button type="button" onClick={() => saveCard(card)} disabled={savingId !== null}
                    className="mt-auto w-full rounded-full bg-chalk text-stage text-sm font-semibold py-2 hover:bg-chalk/85 transition-colors disabled:opacity-60 disabled:cursor-wait">
                    {savingId === card.id ? 'Adding…' : 'Add to watchlist'}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </>
  )
}

export default Scanner