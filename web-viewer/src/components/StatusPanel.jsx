import React, { useState, useEffect } from 'react'
import { API_BASE } from '../config'

export default function StatusPanel() {
  const [stats, setStats] = useState({
    conversionCount: 0,
    lastConverted: '-',
    queue: 0
  })

  useEffect(() => {
    // 실시간 상태 가져오기
    const fetchStats = async () => {
      try {
        const response = await fetch(`${API_BASE}/api/stats`)
        const data = await response.json()
        setStats(data)
      } catch (error) {
        console.error('Failed to fetch stats:', error)
      }
    }

    const interval = setInterval(fetchStats, 3000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="bg-gray-800/80 backdrop-blur rounded-lg p-4 w-[min(16rem,90vw)] border border-gray-700">
      <h3 className="text-sm font-semibold mb-3 text-gray-300">시스템 상태</h3>

      <div className="space-y-2">
        <div className="flex justify-between text-sm">
          <span className="text-gray-400">변환 완료</span>
          <span className="font-mono">{stats.conversionCount}건</span>
        </div>

        <div className="flex justify-between text-sm">
          <span className="text-gray-400">대기 중</span>
          <span className="font-mono">{stats.queue}건</span>
        </div>

        <div className="flex justify-between text-sm">
          <span className="text-gray-400">최근 변환</span>
          <span>{stats.lastConverted}</span>
        </div>
      </div>

      <div className="mt-3 pt-3 border-t border-gray-700">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
          <span className="text-xs text-gray-400">서버 연결됨</span>
        </div>
      </div>
    </div>
  )
}