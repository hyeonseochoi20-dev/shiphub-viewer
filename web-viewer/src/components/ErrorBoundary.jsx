import React from 'react'

/**
 * 렌더 중 예외가 나면 React는 트리 전체를 언마운트한다 - 화면이 통째로 검게 비는 이유다.
 * (AI 쿼리 패널에서 서버가 500을 반환했을 때 실제로 그렇게 됐다.)
 * 경계를 쳐 두면 문제가 난 부분만 대체 화면으로 바뀌고 나머지 뷰어는 살아 있는다.
 */
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error('[ErrorBoundary]', this.props.label || '', error, info?.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="p-3 rounded bg-red-950/60 border border-red-800 text-[11px] text-red-200 space-y-1.5">
        <div className="font-medium">{this.props.label || '이 영역'}을 표시하지 못했습니다.</div>
        <div className="text-red-300/80 font-mono break-all">{String(this.state.error?.message || this.state.error)}</div>
        <button
          onClick={() => this.setState({ error: null })}
          className="px-2 py-1 rounded bg-red-800/60 hover:bg-red-700/60"
        >
          다시 시도
        </button>
      </div>
    )
  }
}
