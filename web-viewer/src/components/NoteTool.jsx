import React, { useEffect, useRef, useState } from 'react'
import { attachPickHandler } from './clickIntent'
import { useThree } from '@react-three/fiber'
import { Html } from '@react-three/drei'
import * as THREE from 'three'
import { FiMessageSquare, FiX, FiTrash2 } from 'react-icons/fi'

function isAncestorTool(obj) {
  let p = obj
  while (p) {
    if (p.userData?.isTool) return true
    p = p.parent
  }
  return false
}

// 3D 노트/주석 도구 (VIZZARDX Markup.NoteManager 개념 참고)
// active일 때 클릭하면 그 지점(SnapEngine 스냅 우선)에 텍스트 노트를 붙인다. 노트는 도구가 꺼져도 항상 표시된다.
export default function NoteTool({ active, snapRef, notes, onAddNote, onDeleteNote }) {
  const { gl, camera, scene } = useThree()
  const [pendingPoint, setPendingPoint] = useState(null)
  const [draft, setDraft] = useState('')
  const [openNoteId, setOpenNoteId] = useState(null)
  const raycaster = useRef(new THREE.Raycaster())

  useEffect(() => {
    if (!active) {
      setPendingPoint(null)
      return
    }
    const onPick = (e) => {

      let hitPoint = snapRef?.current?.point
      if (!hitPoint) {
        const rect = gl.domElement.getBoundingClientRect()
        const ndc = new THREE.Vector2(
          ((e.clientX - rect.left) / rect.width) * 2 - 1,
          -((e.clientY - rect.top) / rect.height) * 2 + 1
        )
        raycaster.current.setFromCamera(ndc, camera)
        const hits = raycaster.current.intersectObjects(scene.children, true)
        const hit = hits.find((h) => !isAncestorTool(h.object))
        hitPoint = hit?.point
      }
      if (hitPoint) {
        setPendingPoint(hitPoint.clone())
        setDraft('')
      }
    }
    return attachPickHandler(gl.domElement, onPick)
  }, [active, gl, camera, scene, snapRef])

  const saveNote = () => {
    if (!pendingPoint || !draft.trim()) {
      setPendingPoint(null)
      return
    }
    onAddNote({ id: Date.now(), point: pendingPoint.toArray(), text: draft.trim() })
    setPendingPoint(null)
    setDraft('')
  }

  return (
    <group userData={{ isTool: true }}>
      {/* 기존 노트 마커 (도구 활성 여부와 무관하게 항상 표시) */}
      {notes.map((n) => (
        <group key={n.id}>
          <mesh position={n.point} onClick={(e) => { e.stopPropagation(); setOpenNoteId(openNoteId === n.id ? null : n.id) }}>
            <sphereGeometry args={[0.3, 8, 8]} />
            <meshBasicMaterial color="#f472b6" depthTest={false} />
          </mesh>
          <Html position={n.point} center>
            {openNoteId === n.id ? (
              <div className="bg-black/90 border border-pink-400/50 rounded px-2.5 py-2 text-xs text-gray-100 w-48 -translate-y-8 pointer-events-auto">
                <div className="flex items-start justify-between gap-2 mb-1">
                  <FiMessageSquare className="w-3 h-3 text-pink-400 shrink-0 mt-0.5" />
                  <p className="flex-1 break-words">{n.text}</p>
                  <button onClick={() => onDeleteNote(n.id)} className="shrink-0">
                    <FiTrash2 className="w-3 h-3 text-gray-500 hover:text-red-400" />
                  </button>
                </div>
              </div>
            ) : (
              <div className="-translate-y-6 pointer-events-none">
                <FiMessageSquare className="w-3 h-3 text-pink-400" />
              </div>
            )}
          </Html>
        </group>
      ))}

      {/* 신규 노트 입력 */}
      {pendingPoint && (
        <Html position={pendingPoint} center>
          <div className="bg-black/90 border border-cyan-400/50 rounded px-2.5 py-2 w-52 -translate-y-8 pointer-events-auto">
            <textarea
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="노트 내용 입력..."
              className="w-full bg-gray-900 border border-gray-700 rounded px-1.5 py-1 text-xs text-gray-100 resize-none"
              rows={2}
            />
            <div className="flex justify-end gap-1.5 mt-1.5">
              <button onClick={() => setPendingPoint(null)} className="p-1 rounded bg-gray-700 hover:bg-gray-600">
                <FiX className="w-3 h-3" />
              </button>
              <button onClick={saveNote} className="px-2 py-1 rounded bg-blue-600 hover:bg-blue-700 text-[10px] font-medium">
                저장
              </button>
            </div>
          </div>
        </Html>
      )}
    </group>
  )
}
