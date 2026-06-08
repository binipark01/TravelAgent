import { Plane } from 'lucide-react'
import { Link, NavLink } from 'react-router-dom'

export function Header() {
  return (
    <header className="site-header">
      <Link to="/" className="brand" aria-label="여행 계획 홈">
        <Plane aria-hidden="true" />
        <span>여행 플래너</span>
      </Link>
      <nav className="header-nav" aria-label="주요 메뉴">
        <NavLink to="/">새 여행</NavLink>
        <NavLink to="/trips">최근 여행</NavLink>
        <NavLink to="/settings">설정</NavLink>
      </nav>
    </header>
  )
}
