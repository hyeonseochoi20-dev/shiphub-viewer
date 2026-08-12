import React from 'react'
import { Html, useProgress } from '@react-three/drei'

// three.js의 DefaultLoadingManager를 실시간으로 추적하는 실제 진행률(가짜 애니메이션 아님)
export default function ModelLoader() {
  const { progress, item } = useProgress()

  return (
    <Html center>
      <div className="flex flex-col items-center gap-3 w-56 select-none">
        <div className="w-10 h-10 border-2 border-blue-500/30 border-t-blue-500 rounded-full animate-spin" />
        <div className="w-full">
          <div className="w-full h-1.5 bg-gray-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-blue-500 to-cyan-400 rounded-full transition-[width] duration-200 ease-out"
              style={{ width: `${Math.max(4, progress)}%` }}
            />
          </div>
          <div className="flex items-center justify-between mt-1.5">
            <span className="text-[11px] text-gray-400 truncate max-w-[140px]">{item ? item.split('/').pop() : '모델 로딩 중'}</span>
            <span className="text-[11px] font-mono text-blue-300 shrink-0 ml-2">{Math.round(progress)}%</span>
          </div>
        </div>
      </div>
    </Html>
  )
}
