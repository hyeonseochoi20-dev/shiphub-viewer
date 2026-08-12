import React, { useEffect, useState } from 'react'
import { FiCheckCircle, FiClock } from 'react-icons/fi'
import { API_BASE } from '../config'

const FALLBACK_MODULES = [
  { id: 'ifc', name: 'IFC (BIM)', engine: 'IfcOpenShell', status: 'active' },
  { id: 'dxf', name: 'DXF (2D/3D 도면)', engine: 'ezdxf', status: 'active' },
  { id: 'step218', name: 'STEP AP218 (Ship Structures)', engine: 'Open Cascade (예정)', status: 'planned' },
  { id: 'tribon', name: 'AVEVA Marine / Tribon', engine: '예정', status: 'planned' },
  { id: 'cadmatic', name: 'CADMATIC Hull/Outfitting', engine: '예정', status: 'planned' },
  { id: 'foran', name: 'FORAN', engine: '예정', status: 'planned' },
  { id: 'rvt', name: 'Revit (RVT, 해양플랜트 설비동)', engine: 'IFC 익스포트 경유', status: 'planned' },
]

export default function ModulePanel() {
  const [modules, setModules] = useState(FALLBACK_MODULES)

  useEffect(() => {
    fetch(`${API_BASE}/api/modules`)
      .then((res) => res.json())
      .then((data) => setModules(data))
      .catch(() => setModules(FALLBACK_MODULES))
  }, [])

  return (
    <div className="bg-gray-800/90 backdrop-blur border border-gray-700 rounded-lg p-3 w-[min(16rem,90vw)] text-sm">
      <h3 className="font-semibold mb-2 text-gray-200">지원 포맷 모듈</h3>
      <div className="space-y-1.5">
        {modules.map((m) => (
          <div key={m.id} className="flex items-center justify-between text-gray-300">
            <div className="flex items-center gap-2 min-w-0">
              {m.status === 'active' ? (
                <FiCheckCircle className="w-4 h-4 text-green-400 shrink-0" />
              ) : (
                <FiClock className="w-4 h-4 text-yellow-500 shrink-0" />
              )}
              <span className="truncate">{m.name}</span>
            </div>
            <span className="text-xs text-gray-500 shrink-0 ml-2">{m.engine}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
