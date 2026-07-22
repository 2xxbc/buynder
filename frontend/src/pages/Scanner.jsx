import { useState, useRef, useEffect } from 'react';
import { API_URL, apiFetch } from '../config';
function Scanner() {
  const [scanning, setScanning] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [preview, setPreview] = useState('');
  const [cameraOn, setCameraOn] = useState(false);
  const [cameras, setCameras] = useState([]);
  const [selectedCamera, setSelectedCamera] = useState('');
  const [tip, setTip] = useState('Hold card inside the box');
  const [tipColor, setTipColor] = useState('text-slate-300');
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const analyzeCanvasRef = useRef(null);
  const streamRef = useRef(null);
  const tipIntervalRef = useRef(null);
  useEffect(() => {
    return () => {
      stopCamera();
      if (tipIntervalRef.current) clearInterval(tipIntervalRef.current);
    };
  }, []);
  async function loadCameras() {
    try {
      const tempStream = await navigator.mediaDevices.getUserMedia({
        video: true
      });
      tempStream.getTracks().forEach(track => track.stop());
      const devices = await navigator.mediaDevices.enumerateDevices();
      const videoDevices = devices.filter(d => d.kind === 'videoinput');
      setCameras(videoDevices);
      if (videoDevices.length > 0 && !selectedCamera) {
        setSelectedCamera(videoDevices[0].deviceId);
        return videoDevices[0].deviceId;
      }
      return selectedCamera;
    } catch (err) {
      setError('Could not access camera: ' + err.message);
      return null;
    }
  }
  async function startCamera(deviceId) {
    setError('');
    setResult(null);
    setPreview('');
    let useId = deviceId || selectedCamera;
    if (!useId) {
      useId = await loadCameras();
      if (!useId) return;
    }
    setCameraOn(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          deviceId: {
            exact: useId
          }
        }
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
      tipIntervalRef.current = setInterval(analyzeFrame, 700);
    } catch (err) {
      setCameraOn(false);
      setError('Could not access camera: ' + err.message);
    }
  }
  function stopCamera() {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }
    if (tipIntervalRef.current) {
      clearInterval(tipIntervalRef.current);
      tipIntervalRef.current = null;
    }
    setCameraOn(false);
  }
  async function switchCamera(newDeviceId) {
    setSelectedCamera(newDeviceId);
    if (cameraOn) {
      stopCamera();
      setTimeout(() => startCamera(newDeviceId), 200);
    }
  }
  function analyzeFrame() {
    const video = videoRef.current;
    const canvas = analyzeCanvasRef.current;
    if (!video || !canvas || video.videoWidth === 0) return;
    canvas.width = 100;
    canvas.height = 140;
    const ctx = canvas.getContext('2d');
    const cropX = video.videoWidth * 0.25;
    const cropY = video.videoHeight * 0.15;
    const cropW = video.videoWidth * 0.5;
    const cropH = video.videoHeight * 0.7;
    ctx.drawImage(video, cropX, cropY, cropW, cropH, 0, 0, 100, 140);
    const imageData = ctx.getImageData(0, 0, 100, 140);
    const data = imageData.data;
    let totalBrightness = 0;
    let edgeCount = 0;
    let prevBrightness = 0;
    for (let i = 0; i < data.length; i += 4) {
      const brightness = (data[i] + data[i + 1] + data[i + 2]) / 3;
      totalBrightness += brightness;
      if (i > 0 && Math.abs(brightness - prevBrightness) > 30) edgeCount++;
      prevBrightness = brightness;
    }
    const avgBrightness = totalBrightness / (data.length / 4);
    const sharpness = edgeCount / (data.length / 4);
    if (avgBrightness < 60) {
      setTip('Too dark — add more light');
      setTipColor('text-yellow-400');
    } else if (avgBrightness > 220) {
      setTip('Too bright — reduce glare or move light away');
      setTipColor('text-yellow-400');
    } else if (sharpness < 0.05) {
      setTip('Looks blurry — hold steady or move closer');
      setTipColor('text-yellow-400');
    } else if (sharpness > 0.4) {
      setTip('Too busy — center card on a plain background');
      setTipColor('text-yellow-400');
    } else {
      setTip('Looks good — snap when ready');
      setTipColor('text-green-400');
    }
  }
  function snapPhoto() {
    if (!videoRef.current || !canvasRef.current) return;
    const video = videoRef.current;
    const canvas = canvasRef.current;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);
    canvas.toBlob(blob => {
      stopCamera();
      const file = new File([blob], 'snap.png', {
        type: 'image/png'
      });
      handleFile(file);
    });
  }
  function handleFile(file) {
    if (!file) return;
    setPreview(URL.createObjectURL(file));
    setScanning(true);
    setError('');
    setResult(null);
    const formData = new FormData();
    formData.append('image', file);
    apiFetch('/scan-card', {
      method: 'POST',
      body: formData
    }).then(res => res.json()).then(data => {
      setScanning(false);
      if (data.error) setError(data.error);else setResult(data);
    }).catch(err => {
      setScanning(false);
      setError('Scan failed: ' + err.message);
    });
  }
  function saveCard(cardId) {
    apiFetch(`/save-card/${cardId}`).then(() => alert('Added to your watchlist!'));
  }
  return <>
      <h2 className="text-3xl font-bold mb-8">Card Scanner</h2>

      <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 mb-8">
        <p className="text-slate-400 mb-4">
          Use your webcam, take a phone photo, or upload an image. Hold card flat, centered, and well-lit for best results.
        </p>

        {!cameraOn && <div className="flex flex-col sm:flex-row gap-3">
            <button onClick={() => startCamera()} className="flex-1 bg-red-500 hover:bg-red-600 text-white font-semibold py-3 px-6 rounded-lg">
              Use Webcam
            </button>
            <label className="flex-1 bg-slate-700 hover:bg-slate-600 text-white font-semibold py-3 px-6 rounded-lg text-center cursor-pointer">
              Upload Image
              <input type="file" accept="image/*" className="hidden" onChange={e => handleFile(e.target.files[0])} />
            </label>
          </div>}

        {cameraOn && <div>
            {cameras.length > 1 && <div className="mb-4">
                <label className="block text-sm text-slate-400 mb-1">Camera</label>
                <select value={selectedCamera} onChange={e => switchCamera(e.target.value)} className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-red-500">
                  {cameras.map((cam, i) => <option key={cam.deviceId} value={cam.deviceId}>
                      {cam.label || `Camera ${i + 1}`}
                    </option>)}
                </select>
              </div>}

            <div className="relative max-w-2xl">
              <video ref={videoRef} autoPlay playsInline className="w-full rounded-lg bg-black" />
              <div className="absolute pointer-events-none border-4 border-white/70 rounded-xl" style={{
            top: '15%',
            left: '25%',
            width: '50%',
            height: '70%',
            boxShadow: '0 0 0 9999px rgba(0,0,0,0.4)'
          }} />
              <div className="absolute top-3 left-1/2 -translate-x-1/2 bg-slate-900/90 px-4 py-2 rounded-lg">
                <p className={`text-sm font-semibold ${tipColor}`}>{tip}</p>
              </div>
            </div>

            <div className="flex gap-3 mt-4">
              <button onClick={snapPhoto} className="flex-1 bg-red-500 hover:bg-red-600 text-white font-semibold py-3 rounded-lg">
                Snap Photo
              </button>
              <button onClick={stopCamera} className="flex-1 bg-slate-700 hover:bg-slate-600 text-white font-semibold py-3 rounded-lg">
                Cancel
              </button>
            </div>

            <div className="mt-4 text-sm text-slate-400">
              <p className="font-semibold text-slate-300 mb-1">Tips for best results:</p>
              <ul className="list-disc pl-5 space-y-1">
                <li>Place card flat on a plain dark surface</li>
                <li>Use even lighting, no flash</li>
                <li>Fill the box with the card, top of card at the top</li>
                <li>Holo cards may not scan well, try matte cards first</li>
              </ul>
            </div>
          </div>}
      </div>

      <canvas ref={canvasRef} className="hidden" />
      <canvas ref={analyzeCanvasRef} className="hidden" />

      {preview && !cameraOn && <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 mb-8">
          <h3 className="text-lg font-semibold mb-3">Your image</h3>
          <img src={preview} alt="Preview" className="max-w-sm rounded-lg" />
        </div>}

      {scanning && <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 mb-8 text-center">
          <p className="text-slate-300">Scanning...</p>
        </div>}

      {error && <div className="bg-red-950 border border-red-800 rounded-xl p-6 mb-8">
          <p className="text-red-300 font-semibold">Error</p>
          <p className="text-red-400 text-sm mt-1">{error}</p>
        </div>}

      {result && <>
          <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 mb-6">
            <p className="text-sm text-slate-400 mb-1">Detected name</p>
            <p className="text-2xl font-bold">{result.detected_name}</p>
          </div>

          <h3 className="text-xl font-semibold mb-4">Matches</h3>

          {result.matches.length === 0 ? <p className="text-slate-400">No cards found with that name. Try a clearer photo.</p> : <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
              {result.matches.map(card => <div key={card.id} className="bg-slate-800 rounded-xl p-4 border border-slate-700 hover:border-red-500 transition-colors">
                  <img src={card.images.small} alt={card.name} className="w-full rounded-lg mb-3" />
                  <h4 className="font-semibold">{card.name}</h4>
                  <p className="text-sm text-slate-400 mb-3">{card.set.name}</p>
                  <button onClick={() => saveCard(card.id)} className="w-full bg-red-500 hover:bg-red-600 text-white text-sm font-semibold py-2 rounded">
                    Add to Watchlist
                  </button>
                </div>)}
            </div>}
        </>}
    </>;
}
export default Scanner;
