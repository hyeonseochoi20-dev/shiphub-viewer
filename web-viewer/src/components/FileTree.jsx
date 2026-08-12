import React, { useState, useEffect } from 'react'
import { FiFile, FiRefreshCw } from 'react-icons/fi'

// 고품질 실사형 모델만 (PBR 텍스처 있는 Sketchfab CC-BY) - 저품질/단색 모델은 제외
const FALLBACK_FILES = [
  { id: 1, category: '화물선/탱커', name: 'Tanker Ship (Suezmax, 322m)', url: '/models/tanker-ship/scene.gltf', size: '10MB', lod: 1 },
  { id: 2, category: '화물선/탱커', name: 'Container Ship', url: '/models/container-ship/scene.gltf', size: '19MB', lod: 1 },
  { id: 3, category: '해양플랜트', name: 'FLNG (부유식 액화천연가스 설비)', url: 'flng-plant', size: 'procedural', lod: 1, type: 'procedural' },
]

export default function FileTree({ onSelect }) {
  const [loading, setLoading] = useState(false)
  const [converted, setConverted] = useState([])

  // 변환된 파일 목록 가져오기 - 선종별 샘플 라이브러리는 항상 보여주고,
  // 실제 배치 변환 결과물이 있으면 별도 카테고리로 함께 보여줌
  const fetchFiles = async () => {
    setLoading(true)
    try {
      const response = await fetch('/api/models')
      const data = await response.json()
      setConverted(data)
    } catch (error) {
      console.error('Failed to fetch files:', error)
      setConverted([])
    }
    setLoading(false)
  }

  useEffect(() => {
    fetchFiles()
  }, [])

  const files = [...FALLBACK_FILES, ...converted.map((f, i) => ({ ...f, id: `conv-${i}`, category: '변환된 모델 (실시간)' }))]

  const groups = files.reduce((acc, f) => {
    const key = f.category || '기타'
    acc[key] = acc[key] || []
    acc[key].push(f)
    return acc
  }, {})

  return (
    <div className="p-4">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">모델 라이브러리</h2>
        <button
          onClick={fetchFiles}
          disabled={loading}
          className="p-2 rounded hover:bg-gray-700 transition-colors"
        >
          <FiRefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      <div className="space-y-4">
        {Object.entries(groups).map(([category, items]) => (
          <div key={category}>
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">{category}</p>
            <div className="space-y-2">
              {items.map((file) => (
                <div
                  key={file.id ?? file.name}
                  onClick={() => onSelect({
                    type: file.type || 'gltf',
                    url: file.url || `/models/${file.name}`,
                    name: file.name,
                    lod: file.lod
                  })}
                  className="flex items-center gap-3 p-3 rounded-lg bg-gray-700/50 hover:bg-gray-700 cursor-pointer transition-colors border border-gray-600"
                >
                  <FiFile className="w-5 h-5 text-blue-400" />
                  <div className="flex-1 min-w-0">
                    <p className="font-medium truncate">{file.name}</p>
                    <p className="text-sm text-gray-400">
                      {file.size} • LOD {file.lod}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
