interface ErrorStateProps {
  message?: string
}

export function ErrorState({ message = '오류가 발생했습니다.' }: ErrorStateProps) {
  return <div className="state-box error-state">{message}</div>
}
