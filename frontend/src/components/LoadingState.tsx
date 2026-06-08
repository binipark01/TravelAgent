interface LoadingStateProps {
  label?: string
}

export function LoadingState({ label = '불러오는 중입니다.' }: LoadingStateProps) {
  return <div className="state-box loading-state">{label}</div>
}
