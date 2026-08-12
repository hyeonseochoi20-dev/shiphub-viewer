import React, { useState, useEffect, useRef } from 'react'
import { FiSearch, FiZap, FiX, FiMessageCircle } from 'react-icons/fi'
import { API_BASE } from '../config'

// MariaDB 생산 DB를 REST로 직접 조회하는 패널 (converter.py의 /api/ai/* 엔드포인트,
// production_data.py 공용 로직 - mcp_server.py와 동일한 쿼리/모델을 로컬 HTTP로 노출)
export default function AIQueryPanel() {
  const [open, setOpen] = useState(false)
  const [mode, setMode] = useState('faq') // 'faq' | 'query' | 'predict'
  const [filters, setFilters] = useState(null)
  const [faq, setFaq] = useState(null)
  const [chatLog, setChatLog] = useState([]) // [{role:'user'|'assistant', text, note}]
  const [typing, setTyping] = useState(false)
  const chatEndRef = useRef(null)
  const [queryParams, setQueryParams] = useState({ ship_type: '', department: '', priority: '', qa_status: '' })
  const [results, setResults] = useState([])
  const [similar, setSimilar] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const [predictForm, setPredictForm] = useState({
    triangle_count: 80000, file_size_mb: 1.8, lod_level: 1, planned_days: 14,
    department: '', process_stage: '', priority: '', ship_type: '',
  })
  const [predictResult, setPredictResult] = useState(null)

  useEffect(() => {
    if (!open || filters) return
    fetch(`${API_BASE}/api/ai/filters`)
      .then((r) => r.json())
      .then(setFilters)
      .catch(() => setError('필터 목록을 불러오지 못했습니다 (converter.py가 MariaDB에 연결되어 있는지 확인)'))
  }, [open, filters])

  useEffect(() => {
    if (!open || faq) return
    fetch(`${API_BASE}/api/ai/faq`)
      .then((r) => r.json())
      .then(setFaq)
      .catch(() => setError('FAQ를 불러오지 못했습니다'))
  }, [open, faq])

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [chatLog, typing])

  const askFaq = (item) => {
    setChatLog((log) => [...log, { role: 'user', text: item.question }])
    setTyping(true)
    setTimeout(() => {
      setChatLog((log) => [...log, { role: 'assistant', text: item.answer, note: item.note }])
      setTyping(false)
    }, 420 + Math.random() * 260)
  }

  const runQuery = async () => {
    setLoading(true)
    setError(null)
    setSimilar(null)
    try {
      const params = new URLSearchParams()
      Object.entries(queryParams).forEach(([k, v]) => { if (v) params.set(k, v) })
      params.set('limit', '15')
      const res = await fetch(`${API_BASE}/api/ai/blocks?${params}`)
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || '조회 실패')
      setResults(data)
    } catch (e) {
      setError(e.message)
    }
    setLoading(false)
  }

  const findSimilar = async (blockId) => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/api/ai/blocks/${blockId}/similar?top_k=5`)
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || '조회 실패')
      setSimilar(data)
    } catch (e) {
      setError(e.message)
    }
    setLoading(false)
  }

  const runPredict = async () => {
    setLoading(true)
    setError(null)
    setPredictResult(null)
    try {
      const res = await fetch(`${API_BASE}/api/ai/predict`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(predictForm),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || '예측 실패')
      setPredictResult(data)
    } catch (e) {
      setError(e.message)
    }
    setLoading(false)
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border bg-gray-800/90 border-gray-700 text-gray-300 hover:bg-gray-700"
      >
        <FiZap className="w-3.5 h-3.5" />
        AI 쿼리
      </button>
    )
  }

  const selectClass = 'bg-gray-900 border border-gray-600 rounded px-2 py-1 text-xs text-gray-200'

  return (
    <div className="bg-gray-800/90 backdrop-blur rounded-lg p-4 w-96 border border-gray-700 max-h-[70vh] overflow-y-auto">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-300 flex items-center gap-1.5">
          <FiZap className="w-3.5 h-3.5" /> AI 쿼리 (MariaDB 실시간)
        </h3>
        <button onClick={() => setOpen(false)} className="p-1 rounded hover:bg-gray-700">
          <FiX className="w-3.5 h-3.5" />
        </button>
      </div>

      <div className="flex gap-1 mb-3">
        <button
          onClick={() => setMode('faq')}
          className={`flex-1 py-1 rounded text-xs ${mode === 'faq' ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-300'}`}
        >
          자주 묻는 질문
        </button>
        <button
          onClick={() => setMode('query')}
          className={`flex-1 py-1 rounded text-xs ${mode === 'query' ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-300'}`}
        >
          블록 조회
        </button>
        <button
          onClick={() => setMode('predict')}
          className={`flex-1 py-1 rounded text-xs ${mode === 'predict' ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-300'}`}
        >
          지연 예측
        </button>
      </div>

      {error && <p className="text-[11px] text-red-400 mb-2">{error}</p>}

      {mode === 'faq' && (
        <div className="flex flex-col">
          {!faq && <p className="text-[11px] text-gray-500">불러오는 중...</p>}

          {chatLog.length === 0 && faq && (
            <div className="flex items-start gap-2 mb-3">
              <div className="w-6 h-6 rounded-full bg-blue-600/80 flex items-center justify-center shrink-0">
                <FiMessageCircle className="w-3.5 h-3.5 text-white" />
              </div>
              <div className="bg-gray-900 rounded-lg rounded-tl-sm px-3 py-2 text-[11px] text-gray-300">
                안녕하세요, ShipHub 생산 DB에 대해 물어보세요. 아래 질문 중 하나를 눌러보세요.
              </div>
            </div>
          )}

          {chatLog.length > 0 && (
            <div className="space-y-2.5 mb-3 max-h-56 overflow-y-auto pr-1">
              {chatLog.map((m, i) =>
                m.role === 'user' ? (
                  <div key={i} className="flex justify-end">
                    <div className="bg-blue-600 text-white rounded-lg rounded-tr-sm px-3 py-1.5 text-[11px] max-w-[85%]">
                      {m.text}
                    </div>
                  </div>
                ) : (
                  <div key={i} className="flex items-start gap-2">
                    <div className="w-6 h-6 rounded-full bg-blue-600/80 flex items-center justify-center shrink-0 mt-0.5">
                      <FiMessageCircle className="w-3.5 h-3.5 text-white" />
                    </div>
                    <div className="bg-gray-900 rounded-lg rounded-tl-sm px-3 py-2 text-[11px] text-gray-300 whitespace-pre-line leading-relaxed max-w-[85%]">
                      {m.text}
                      {m.note && <p className="mt-1.5 text-[10px] text-yellow-500/80">※ {m.note}</p>}
                    </div>
                  </div>
                )
              )}
              {typing && (
                <div className="flex items-center gap-2">
                  <div className="w-6 h-6 rounded-full bg-blue-600/80 flex items-center justify-center shrink-0">
                    <FiMessageCircle className="w-3.5 h-3.5 text-white" />
                  </div>
                  <div className="bg-gray-900 rounded-lg rounded-tl-sm px-3 py-2 flex gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-gray-500 animate-bounce" style={{ animationDelay: '0ms' }} />
                    <span className="w-1.5 h-1.5 rounded-full bg-gray-500 animate-bounce" style={{ animationDelay: '120ms' }} />
                    <span className="w-1.5 h-1.5 rounded-full bg-gray-500 animate-bounce" style={{ animationDelay: '240ms' }} />
                  </div>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>
          )}

          <div className="flex flex-wrap gap-1.5">
            {faq && faq.map((item, i) => (
              <button
                key={i}
                onClick={() => askFaq(item)}
                disabled={typing}
                className="bg-gray-900/70 hover:bg-gray-900 disabled:opacity-40 rounded-full px-2.5 py-1 text-[10.5px] text-gray-300 transition-colors border border-gray-700"
              >
                {item.question}
              </button>
            ))}
          </div>
        </div>
      )}

      {(mode === 'query' || mode === 'predict') && !filters && !error && <p className="text-[11px] text-gray-500">불러오는 중...</p>}

      {mode === 'query' && filters && (
        <div className="space-y-2">
          <div className="grid grid-cols-2 gap-1.5">
            <select value={queryParams.ship_type} onChange={(e) => setQueryParams((q) => ({ ...q, ship_type: e.target.value }))} className={selectClass}>
              <option value="">전체 선종</option>
              {filters.ship_type.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
            <select value={queryParams.department} onChange={(e) => setQueryParams((q) => ({ ...q, department: e.target.value }))} className={selectClass}>
              <option value="">전체 부서</option>
              {filters.department.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
            <select value={queryParams.priority} onChange={(e) => setQueryParams((q) => ({ ...q, priority: e.target.value }))} className={selectClass}>
              <option value="">전체 우선순위</option>
              {filters.priority.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
            <select value={queryParams.qa_status} onChange={(e) => setQueryParams((q) => ({ ...q, qa_status: e.target.value }))} className={selectClass}>
              <option value="">전체 QA상태</option>
              {filters.qa_status.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </div>
          <button
            onClick={runQuery}
            disabled={loading}
            className="w-full py-1.5 rounded bg-blue-600 hover:bg-blue-700 text-xs font-medium disabled:opacity-50 flex items-center justify-center gap-1.5"
          >
            <FiSearch className="w-3.5 h-3.5" /> {loading ? '조회 중...' : '조회 (지연일수 내림차순)'}
          </button>

          <div className="space-y-1.5 mt-2">
            {results.map((r) => (
              <div key={r.block_id} className="bg-gray-900/60 rounded p-2 text-[11px]">
                <div className="flex justify-between gap-2">
                  <span className="font-mono text-gray-300 truncate">{r.block_name}</span>
                  <span className={`shrink-0 ${r.delay_days > 5 ? 'text-red-400' : r.delay_days > 2 ? 'text-yellow-400' : 'text-green-400'}`}>
                    {r.delay_days}일 지연
                  </span>
                </div>
                <div className="text-gray-500 mt-0.5">{r.ship_type} · {r.department} · QA {r.qa_status}</div>
                <button onClick={() => findSimilar(r.block_id)} className="text-blue-400 hover:underline mt-1 text-[10px]">
                  유사 블록 찾기
                </button>
              </div>
            ))}
          </div>

          {similar && (
            <div className="mt-2 border-t border-gray-700 pt-2">
              <p className="text-[10px] text-gray-500 mb-1">{similar.method}</p>
              {similar.results.map((r) => (
                <div key={r.block_id} className="text-[11px] text-gray-300 py-0.5 flex justify-between gap-2">
                  <span className="font-mono truncate">{r.block_name}</span>
                  <span className="text-gray-500 shrink-0">거리 {r.similarity_distance}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {mode === 'predict' && filters && (
        <div className="space-y-1.5">
          <div className="grid grid-cols-2 gap-1.5">
            <select value={predictForm.ship_type} onChange={(e) => setPredictForm((f) => ({ ...f, ship_type: e.target.value }))} className={selectClass}>
              <option value="">선종 선택</option>
              {filters.ship_type.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
            <select value={predictForm.department} onChange={(e) => setPredictForm((f) => ({ ...f, department: e.target.value }))} className={selectClass}>
              <option value="">부서 선택</option>
              {filters.department.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
            <select value={predictForm.process_stage} onChange={(e) => setPredictForm((f) => ({ ...f, process_stage: e.target.value }))} className={selectClass}>
              <option value="">공정 선택</option>
              {filters.process_stage.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
            <select value={predictForm.priority} onChange={(e) => setPredictForm((f) => ({ ...f, priority: e.target.value }))} className={selectClass}>
              <option value="">우선순위 선택</option>
              {filters.priority.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-1.5">
            <input
              type="number"
              value={predictForm.triangle_count}
              onChange={(e) => setPredictForm((f) => ({ ...f, triangle_count: +e.target.value }))}
              placeholder="삼각형 수"
              className={selectClass}
            />
            <input
              type="number"
              value={predictForm.planned_days}
              onChange={(e) => setPredictForm((f) => ({ ...f, planned_days: +e.target.value }))}
              placeholder="계획일수"
              className={selectClass}
            />
          </div>
          <button
            onClick={runPredict}
            disabled={loading || !predictForm.ship_type || !predictForm.department || !predictForm.process_stage || !predictForm.priority}
            className="w-full py-1.5 rounded bg-blue-600 hover:bg-blue-700 text-xs font-medium disabled:opacity-50"
          >
            {loading ? '예측 중...' : '예측하기'}
          </button>
          {predictResult && (
            <div className="bg-gray-900/60 rounded p-2 text-xs space-y-1.5">
              <div className="flex justify-between">
                <span className="text-gray-400">예상 지연일수</span>
                <span className="font-semibold text-gray-200">{predictResult.predicted_delay_days}일</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">QA 합격 확률</span>
                <span className="font-semibold text-gray-200">{(predictResult.qa_pass_probability * 100).toFixed(1)}%</span>
              </div>
              <div
                className={`text-center py-1 rounded font-medium ${
                  predictResult.risk_level === '고위험'
                    ? 'bg-red-500/20 text-red-400'
                    : predictResult.risk_level === '주의'
                    ? 'bg-yellow-500/20 text-yellow-400'
                    : 'bg-green-500/20 text-green-400'
                }`}
              >
                {predictResult.risk_level}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
