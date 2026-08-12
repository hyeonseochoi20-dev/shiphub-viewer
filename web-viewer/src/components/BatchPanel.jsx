import React, { useState, useEffect, useRef } from 'react'
import { FiFolder, FiEdit2, FiSave, FiX, FiFile, FiExternalLink, FiList } from 'react-icons/fi'
import { API_BASE } from '../config'

export default function BatchPanel() {
  const [queue, setQueue] = useState([])
  const [isProcessing, setIsProcessing] = useState(false)
  const [batchError, setBatchError] = useState(null)
  const pollRef = useRef(null)

  const [inputDir, setInputDir] = useState('input_models/')
  const [lodLevel, setLodLevel] = useState(null)
  const [editingPath, setEditingPath] = useState(false)
  const [pathDraft, setPathDraft] = useState('')
  const [pathError, setPathError] = useState(null)

  const [browsing, setBrowsing] = useState(false)
  const [browseFiles, setBrowseFiles] = useState([])
  const [openError, setOpenError] = useState(null)

  const loadSettings = () => {
    fetch(`${API_BASE}/api/settings`)
      .then((res) => res.json())
      .then((data) => {
        setInputDir(data.input_dir)
        setLodLevel(data.lod_level)
      })
      .catch(() => {})
  }

  const LOD_LABELS = { 1: '10분의 1', 2: '1분의 1', 3: '원본' }

  const fetchBatchStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/batch-status`)
      const data = await res.json()
      setQueue(data.items || [])
      setIsProcessing(!!data.running)
      return data.running
    } catch {
      return false
    }
  }

  // 배치 진행 중일 때만 1.5초 간격으로 상태 폴링, 멈추면 자동으로 폴링도 중단
  useEffect(() => {
    if (!isProcessing) {
      if (pollRef.current) clearInterval(pollRef.current)
      return
    }
    pollRef.current = setInterval(async () => {
      const stillRunning = await fetchBatchStatus()
      if (!stillRunning && pollRef.current) clearInterval(pollRef.current)
    }, 1500)
    return () => clearInterval(pollRef.current)
  }, [isProcessing])

  useEffect(() => {
    loadSettings()
    fetchBatchStatus()
  }, [])

  const startBatch = async () => {
    setBatchError(null)
    try {
      const res = await fetch(`${API_BASE}/api/batch-start`, { method: 'POST' })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || '배치 변환을 시작할 수 없습니다')
      setQueue(data.items || [])
      setIsProcessing(true)
    } catch (e) {
      setBatchError(e.message)
    }
  }

  const stopBatch = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/batch-stop`, { method: 'POST' })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || '정지할 수 없습니다')
    } catch (e) {
      setBatchError(e.message)
    }
    fetchBatchStatus()
  }

  const openInExplorer = async () => {
    setOpenError(null)
    try {
      const res = await fetch(`${API_BASE}/api/open-folder`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dir: 'input' }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || '탐색기를 열 수 없습니다')
    } catch (e) {
      setOpenError(e.message)
    }
  }

  const openBrowse = () => {
    const next = !browsing
    setBrowsing(next)
    if (next) {
      fetch(`${API_BASE}/api/browse?dir=input`)
        .then((res) => res.json())
        .then(setBrowseFiles)
        .catch(() => setBrowseFiles([]))
    }
  }

  const startEdit = () => {
    setPathDraft(inputDir)
    setPathError(null)
    setEditingPath(true)
  }

  const savePath = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/settings/input-dir`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: pathDraft }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || '변경 실패')
      setInputDir(data.input_dir)
      setEditingPath(false)
      setPathError(null)
    } catch (e) {
      setPathError(e.message)
    }
  }

  return (
    <div className="bg-gray-800/90 backdrop-blur rounded-lg p-4 min-w-80 border border-gray-700">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-gray-300">배치 변환</h3>
        <div className="flex gap-2">
          <button
            onClick={startBatch}
            disabled={isProcessing}
            className="px-3 py-1 text-xs bg-green-600 hover:bg-green-700 rounded transition-colors disabled:opacity-50"
          >
            시작
          </button>
          <button
            onClick={stopBatch}
            disabled={!isProcessing}
            className="px-3 py-1 text-xs bg-red-600 hover:bg-red-700 rounded transition-colors disabled:opacity-50"
          >
            정지
          </button>
        </div>
      </div>

      {batchError && <p className="text-[11px] text-red-400 mb-2">{batchError}</p>}

      <div className="space-y-3">
        {queue.length === 0 && (
          <p className="text-xs text-gray-500">
            대기 중인 파일이 없습니다. 입력 폴더에 IFC/DXF 파일을 넣고 시작을 눌러주세요.
          </p>
        )}
        {queue.map((item) => (
          <div key={item.id} className="space-y-1">
            <div className="flex justify-between text-sm">
              <span className="truncate">{item.filename}</span>
              <span className={`text-xs px-2 py-0.5 rounded ${getStatusColor(item.status)}`}>
                {getStatusText(item.status)}
              </span>
            </div>
            <div className="w-full bg-gray-700 rounded-full h-2">
              <div
                className={`h-2 rounded-full transition-all ${item.status === 'error' ? 'bg-red-500' : 'bg-blue-500'}`}
                style={{ width: `${item.progress}%` }}
              />
            </div>
          </div>
        ))}
      </div>

      <div className="mt-4 pt-4 border-t border-gray-700">
        <p className="text-xs text-gray-400">
          LOD 설정: <span className="text-blue-400">
            {lodLevel ? `Level ${lodLevel} (${LOD_LABELS[lodLevel] ?? lodLevel})` : '불러오는 중...'}
          </span>
        </p>

        <div className="mt-1.5">
          {editingPath ? (
            <div className="space-y-1.5">
              <div className="flex items-center gap-1.5">
                <input
                  value={pathDraft}
                  onChange={(e) => setPathDraft(e.target.value)}
                  className="flex-1 bg-gray-900 border border-gray-600 rounded px-2 py-1 text-xs text-gray-200"
                  placeholder="input_models 경로"
                />
                <button onClick={savePath} className="p-1.5 rounded bg-blue-600 hover:bg-blue-700">
                  <FiSave className="w-3.5 h-3.5" />
                </button>
                <button onClick={() => setEditingPath(false)} className="p-1.5 rounded bg-gray-700 hover:bg-gray-600">
                  <FiX className="w-3.5 h-3.5" />
                </button>
              </div>
              {pathError && <p className="text-[10px] text-red-400">{pathError}</p>}
            </div>
          ) : (
            <div className="flex items-center gap-1.5 text-xs text-gray-400">
              <span>입력 폴더:</span>
              <button
                onClick={openInExplorer}
                className="flex items-center gap-1 text-blue-400 hover:text-blue-300 hover:underline"
                title="OS 탐색기로 열기"
              >
                <FiFolder className="w-3 h-3" />
                <code className="truncate max-w-[120px]">{inputDir}</code>
                <FiExternalLink className="w-2.5 h-2.5" />
              </button>
              <button onClick={openBrowse} className="p-1 rounded hover:bg-gray-700" title="앱 안에서 파일 목록 보기">
                <FiList className="w-3 h-3 text-gray-500" />
              </button>
              <button onClick={startEdit} className="p-1 rounded hover:bg-gray-700" title="경로 수정">
                <FiEdit2 className="w-3 h-3 text-gray-500" />
              </button>
            </div>
          )}
          {openError && <p className="text-[10px] text-red-400 mt-1">{openError}</p>}
        </div>

        {browsing && !editingPath && (
          <div className="mt-2 bg-gray-900/60 rounded p-2 max-h-32 overflow-y-auto">
            {browseFiles.length === 0 ? (
              <p className="text-[10px] text-gray-500">폴더가 비어있습니다.</p>
            ) : (
              browseFiles.map((f) => (
                <div key={f.name} className="flex items-center justify-between text-[10px] text-gray-400 py-0.5">
                  <span className="flex items-center gap-1 truncate">
                    <FiFile className="w-3 h-3 shrink-0" />
                    {f.name}
                  </span>
                  <span className="shrink-0 ml-2">{f.size_kb}KB</span>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function getStatusColor(status) {
  switch (status) {
    case 'completed': return 'bg-green-500/20 text-green-400'
    case 'processing': return 'bg-yellow-500/20 text-yellow-400'
    case 'pending': return 'bg-gray-500/20 text-gray-400'
    case 'error': return 'bg-red-500/20 text-red-400'
    default: return 'bg-gray-500/20 text-gray-400'
  }
}

function getStatusText(status) {
  switch (status) {
    case 'completed': return '완료'
    case 'processing': return '변환 중'
    case 'pending': return '대기'
    case 'error': return '실패'
    default: return status
  }
}
