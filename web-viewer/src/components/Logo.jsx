import React from 'react'

// 삼성중공업 공식 로고 (Wikimedia Commons, 정식 과정용)
export default function Logo() {
  return (
    <div className="flex items-center gap-2 md:gap-3 min-w-0">
      <div className="bg-white rounded-md px-2 md:px-3 py-1 md:py-1.5 shadow-lg shadow-black/20 shrink-0">
        <img src="/samsung-shi-logo.svg" alt="Samsung Heavy Industries" className="h-3.5 md:h-4 w-auto" />
      </div>
      <div className="leading-tight min-w-0 hidden sm:block">
        <h1 className="text-[13px] md:text-[15px] font-semibold text-gray-100 tracking-tight truncate">
          삼성중공업 <span className="text-gray-400 font-normal hidden md:inline">스마트조선소 AI 전문가 양성 과정</span>
        </h1>
        <p className="text-[10px] text-sky-400/80 font-medium tracking-[0.08em] uppercase">ShipHub Platform</p>
      </div>
    </div>
  )
}
