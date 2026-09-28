import zhCN from 'antd/locale/zh_CN'
import enUS from 'antd/locale/en_US'
import 'dayjs/locale/zh-cn'
import dayjs from 'dayjs'
import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ConfigProvider } from 'antd'
import App from './App'
import './styles.css'
import { useLanguage } from './i18n'

const theme = {
  token: {
    colorPrimary: '#397f78',
    colorText: '#182847',
    colorTextSecondary: '#667085',
    colorBorder: '#dfe3e8',
    borderRadius: 12,
    fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    controlHeight: 44,
  },
}

export function LocalizedApp() {
  const { language } = useLanguage()
  React.useEffect(() => { dayjs.locale(language === 'zh' ? 'zh-cn' : 'en'); document.documentElement.lang = language === 'zh' ? 'zh-CN' : 'en' }, [language])
  return <ConfigProvider locale={language === 'zh' ? zhCN : enUS} theme={theme}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ConfigProvider>
}
ReactDOM.createRoot(document.getElementById('root')).render(<React.StrictMode><LocalizedApp /></React.StrictMode>)

