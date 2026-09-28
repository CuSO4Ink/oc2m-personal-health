import React from 'react'
import { Select } from 'antd'
import { useLanguage } from './i18n'
import './LanguageSwitch.css'

export default function LanguageSwitch() {
  const { language, setLanguage, t } = useLanguage()
  return <Select className="language-switch" aria-label={t('Language')} value={language} onChange={setLanguage} popupMatchSelectWidth={false} options={[{value:'en',label:'English'},{value:'zh',label:'简体中文'}]} />
}
