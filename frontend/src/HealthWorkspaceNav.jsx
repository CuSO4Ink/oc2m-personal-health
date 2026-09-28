import React from 'react'
import { NavLink } from 'react-router-dom'
import { useLanguage } from './i18n'

export default function HealthWorkspaceNav() {
  const { t } = useLanguage()
  return <nav className="health-workspace-nav" aria-label={t("健康资料分类")}>
    <NavLink to="/profile">{t('Basic information & history')}</NavLink>
    <NavLink to="/records" end>{t('Reports & documents')}</NavLink>
  </nav>
}
