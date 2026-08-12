import React, { useState } from 'react'
import { FiCamera, FiTrash2, FiChevronDown, FiChevronRight } from 'react-icons/fi'

// 저장된 뷰 북마크 패널 (VIZZARDX Markup.SnapshotManager 개념 참고)
export default function SavedViewsPanel({ views, onSave, onJump, onDelete }) {
  const [open, setOpen] = useState(false)
  const [nameDraft, setNameDraft] = useState('')

  const handleSave = () => {
    const name = nameDraft.trim() || `뷰 ${views.length + 1}`
    onSave(name)
    setNameDraft('')
  }

  return (
    <div className="bg-gray-800/90 backdrop-blur border border-gray-700 rounded-lg p-3 w-64 text-sm">
      <button onClick={() => setOpen((v) => !v)} className="w-full flex items-center gap-1.5 text-gray-200 font-semibold">
        <FiCamera className="w-3.5 h-3.5 text-cyan-400" />
        <span className="flex-1 text-left">저장된 뷰</span>
        <span className="text-xs text-gray-500">{views.length}</span>
        {open ? <FiChevronDown className="w-3.5 h-3.5" /> : <FiChevronRight className="w-3.5 h-3.5" />}
      </button>

      {open && (
        <div className="mt-2 space-y-2">
          <div className="flex gap-1.5">
            <input
              value={nameDraft}
              onChange={(e) => setNameDraft(e.target.value)}
              placeholder="뷰 이름 (선택)"
              className="flex-1 bg-gray-900 border border-gray-600 rounded px-2 py-1 text-xs text-gray-200"
              onKeyDown={(e) => e.key === 'Enter' && handleSave()}
            />
            <button onClick={handleSave} className="px-2 py-1 rounded bg-blue-600 hover:bg-blue-700 text-xs font-medium">
              저장
            </button>
          </div>

          {views.length === 0 ? (
            <p className="text-xs text-gray-500">현재 카메라 각도를 저장해보세요.</p>
          ) : (
            <div className="space-y-1 max-h-40 overflow-y-auto">
              {views.map((v) => (
                <div key={v.id} className="flex items-center justify-between bg-gray-700/40 rounded px-2 py-1.5">
                  <button onClick={() => onJump(v)} className="text-xs text-gray-200 hover:text-cyan-300 truncate flex-1 text-left">
                    {v.name}
                  </button>
                  <button onClick={() => onDelete(v.id)} className="p-1 rounded hover:bg-gray-600">
                    <FiTrash2 className="w-3 h-3 text-gray-500" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
