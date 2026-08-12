import React, { useState } from 'react'
import {
  FiGrid,
  FiCrosshair,
  FiLayers,
  FiAlertTriangle,
  FiCircle,
  FiTrendingUp,
  FiChevronDown,
  FiChevronRight,
  FiPlay,
  FiPause,
  FiBox,
  FiMessageSquare,
  FiRepeat,
} from 'react-icons/fi'

const GROUPS = [
  {
    id: 'measure_group',
    label: '측정',
    icon: FiCrosshair,
    children: [
      { id: 'measure', label: '거리측정 (2점)' },
      { id: 'radius', label: '반경/원통 (3점)' },
    ],
  },
  {
    id: 'section_group',
    label: '단면',
    icon: FiLayers,
    children: [{ id: 'section', label: '단면보기' }],
  },
  {
    id: 'review_group',
    label: '검토',
    icon: FiAlertTriangle,
    children: [
      { id: 'clash', label: '간섭검사' },
      { id: 'draft', label: '구배분석' },
    ],
  },
  {
    id: 'note_group',
    label: '주석',
    icon: FiMessageSquare,
    children: [{ id: 'note', label: '노트 추가' }],
  },
  {
    id: 'process_group',
    label: '생산공정',
    icon: FiBox,
    children: [{ id: 'erection', label: '탑재 시뮬레이션' }],
  },
]

export default function ToolsPanel({
  showGrid,
  onToggleGrid,
  activeTool,
  onSetTool,
  sectionAxis,
  onSectionAxisChange,
  sectionPos,
  onSectionPosChange,
  sectionFlipped,
  onSectionFlipToggle,
  clashResults,
  erectionProgress,
  onErectionProgressChange,
  erectionPlaying,
  onToggleErectionPlaying,
  erectionStage,
  deckFraction,
  onDeckFractionChange,
  deckFractionDefault = 0.37,
  deckFractionVerified = false,
}) {
  const [expandedGroup, setExpandedGroup] = useState(null)

  // 외부(예: ShipGrid 노드 클릭)에서 activeTool이 바뀌면 해당 그룹을 자동으로 펼침
  React.useEffect(() => {
    if (!activeTool) return
    const owner = GROUPS.find((g) => g.children.some((c) => c.id === activeTool))
    if (owner) setExpandedGroup(owner.id)
  }, [activeTool])

  const selectTool = (id) => {
    onSetTool(activeTool === id ? null : id)
  }

  return (
    <div className="bg-gray-800/90 backdrop-blur border border-gray-700 rounded-lg p-3 w-[min(16rem,90vw)] text-sm">
      <h3 className="font-semibold mb-2 text-gray-200">검토 도구</h3>

      {/* ShipGrid - 단독 토글 (0뎁스) */}
      <button
        onClick={onToggleGrid}
        className={`w-full flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs font-medium mb-1.5 transition-colors ${
          showGrid ? 'bg-blue-600 text-white' : 'bg-gray-700/70 text-gray-300 hover:bg-gray-700'
        }`}
      >
        <FiGrid className="w-3.5 h-3.5" />
        ShipGrid
      </button>

      {/* 카테고리(0뎁스) -> 세부도구(1뎁스) 아코디언 */}
      <div className="space-y-1">
        {GROUPS.map((group) => {
          const isOpen = expandedGroup === group.id
          const groupHasActive = group.children.some((c) => c.id === activeTool)
          return (
            <div key={group.id}>
              <button
                onClick={() => setExpandedGroup(isOpen ? null : group.id)}
                className={`w-full flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs font-medium transition-colors ${
                  groupHasActive ? 'bg-blue-600/80 text-white' : 'bg-gray-700/70 text-gray-300 hover:bg-gray-700'
                }`}
              >
                <group.icon className="w-3.5 h-3.5" />
                <span className="flex-1 text-left">{group.label}</span>
                {isOpen ? <FiChevronDown className="w-3.5 h-3.5" /> : <FiChevronRight className="w-3.5 h-3.5" />}
              </button>

              {isOpen && (
                <div className="pl-3 mt-1 space-y-1 border-l-2 border-gray-700 ml-2">
                  {group.children.map((child) => (
                    <button
                      key={child.id}
                      onClick={() => selectTool(child.id)}
                      className={`w-full text-left px-2.5 py-1.5 rounded text-xs font-medium transition-colors ${
                        activeTool === child.id ? 'bg-blue-600 text-white' : 'bg-gray-700/40 text-gray-300 hover:bg-gray-700'
                      }`}
                    >
                      {child.label}
                    </button>
                  ))}

                  {/* 선택된 도구별 세부 컨트롤 (2뎁스 성격의 옵션 영역) */}
                  {activeTool === 'section' && (
                    <div className="mt-1 space-y-1.5 pt-1">
                      <div className="flex gap-1">
                        {['x', 'y', 'z'].map((axis) => (
                          <button
                            key={axis}
                            onClick={() => onSectionAxisChange(axis)}
                            className={`flex-1 py-1 rounded text-xs uppercase ${
                              sectionAxis === axis ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-300'
                            }`}
                          >
                            {axis}
                          </button>
                        ))}
                        <button
                          onClick={onSectionFlipToggle}
                          title="클리핑 방향 반전"
                          className={`flex items-center justify-center px-2 rounded text-xs ${
                            sectionFlipped ? 'bg-pink-600 text-white' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                          }`}
                        >
                          <FiRepeat className="w-3.5 h-3.5" />
                        </button>
                      </div>
                      <input
                        type="range"
                        min={-150}
                        max={150}
                        step={1}
                        value={sectionPos}
                        onChange={(e) => onSectionPosChange(parseFloat(e.target.value))}
                        className="w-full"
                      />
                      <p className="text-xs text-gray-400">
                        위치: {sectionPos.toFixed(1)}
                        {sectionFlipped && <span className="text-pink-400"> · 방향 반전됨</span>}
                      </p>
                    </div>
                  )}

                  {activeTool === 'measure' && (
                    <p className="text-xs text-gray-400 mt-1 pt-1">모델 위 두 지점을 클릭하면 축별(X/Y/Z) 거리를 표시합니다.</p>
                  )}

                  {activeTool === 'radius' && (
                    <p className="text-xs text-gray-400 mt-1 pt-1">원통/곡면 위 세 점을 클릭하면 외접원의 중심·반지름·지름·원주를 계산합니다.</p>
                  )}

                  {activeTool === 'clash' && (
                    <div className="mt-1 pt-1">
                      {clashResults.length === 0 ? (
                        <p className="text-xs text-green-400">간섭 없음</p>
                      ) : (
                        <div className="space-y-1 max-h-32 overflow-y-auto">
                          <p className="text-xs text-red-400 mb-1">{clashResults.length}건 간섭 발견</p>
                          {clashResults.map((c, i) => (
                            <p key={i} className="text-xs text-gray-300 truncate">
                              {c.a} ↔ {c.b}
                            </p>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {activeTool === 'note' && (
                    <p className="text-xs text-gray-400 mt-1 pt-1">모델 위를 클릭하면 그 지점에 텍스트 노트를 붙일 수 있습니다. 마커 클릭으로 열람/삭제.</p>
                  )}

                  {activeTool === 'draft' && (
                    <div className="mt-1 pt-1 space-y-1">
                      <p className="text-xs text-gray-400">표면 법선의 수직(Z)축 대비 각도로 구배 색상 표시</p>
                      <div className="flex items-center gap-2 text-xs">
                        <span className="inline-block w-3 h-3 rounded-full" style={{ background: 'hsl(0,85%,50%)' }} />
                        <span className="text-gray-400">수평(0°) - 구배 부족 주의</span>
                      </div>
                      <div className="flex items-center gap-2 text-xs">
                        <span className="inline-block w-3 h-3 rounded-full" style={{ background: 'hsl(120,85%,50%)' }} />
                        <span className="text-gray-400">수직(90°) - 안전</span>
                      </div>
                    </div>
                  )}

                  {activeTool === 'erection' && (
                    <div className="mt-1 pt-1 space-y-1.5">
                      <button
                        onClick={onToggleErectionPlaying}
                        className="w-full flex items-center justify-center gap-1.5 py-1.5 rounded bg-gray-700 hover:bg-gray-600 text-xs font-medium"
                      >
                        {erectionPlaying ? <FiPause className="w-3.5 h-3.5" /> : <FiPlay className="w-3.5 h-3.5" />}
                        {erectionPlaying ? '일시정지' : '재생'}
                      </button>
                      <input
                        type="range"
                        min={0}
                        max={100}
                        step={0.5}
                        value={erectionProgress}
                        onChange={(e) => onErectionProgressChange(parseFloat(e.target.value))}
                        className="w-full"
                      />
                      <p className="text-xs text-cyan-400 font-medium">{erectionStage}</p>
                      <p className="text-xs text-gray-400">진행률: {erectionProgress.toFixed(0)}%</p>

                      <div className="pt-2 mt-1 border-t border-gray-700 space-y-1">
                        <div className="flex items-center justify-between">
                          <p className="text-xs text-gray-400">선체/거주구 경계 (데크 안 보이면 조절)</p>
                          <button
                            onClick={() => onDeckFractionChange(deckFractionDefault)}
                            className={`text-[10px] px-1.5 py-0.5 rounded ${deckFraction === deckFractionDefault ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-400'}`}
                          >
                            기본값
                          </button>
                        </div>
                        <input
                          type="range"
                          min={0}
                          max={1}
                          step={0.01}
                          value={deckFraction ?? deckFractionDefault}
                          onChange={(e) => onDeckFractionChange(parseFloat(e.target.value))}
                          className="w-full"
                        />
                        <p className="text-[10px] text-gray-500">하부 {Math.round((deckFraction ?? deckFractionDefault) * 100)}% 지점까지 선체로 표시</p>
                        <p className={`text-[10px] ${deckFractionVerified ? 'text-emerald-500' : 'text-amber-500'}`}>
                          {deckFractionVerified
                            ? '✓ 이 선종은 단면 도구로 실측 검증된 값입니다'
                            : '⚠ 이 선종은 미검증 추정치입니다 · 단면(Z축) 도구로 데크 위치를 확인 후 조절하세요'}
                        </p>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
