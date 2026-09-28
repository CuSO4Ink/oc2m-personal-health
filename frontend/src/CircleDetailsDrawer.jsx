import React from 'react'
import { Alert, Avatar, Button, Drawer, Empty, List, Pagination, Skeleton, Space, Tabs, Tag, Typography, message } from 'antd'
import { UserOutlined } from '@ant-design/icons'
import api, { apiMessage } from './api'
import { useLanguage } from './i18n'

const { Title, Paragraph, Text } = Typography

export default function CircleDetailsDrawer({ circle, onClose, onChanged, onDiscussion, onConnections }) {
  const { t } = useLanguage()
  const [detail, setDetail] = React.useState(circle)
  const [members, setMembers] = React.useState([])
  const [total, setTotal] = React.useState(0)
  const [page, setPage] = React.useState(1)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState('')
  const [busy, setBusy] = React.useState(null)
  const [tab, setTab] = React.useState('about')
  async function loadMembers(nextPage = 1) {
    setLoading(true); setError('')
    try {
      const { data } = await api.get(`/community/circles/${circle.id}/members`, { params: { page: nextPage } })
      setMembers(data.members); setTotal(data.total); setPage(data.page); setDetail((current) => ({ ...current, member_count: data.total }))
    } catch (failure) { setError(apiMessage(failure)) }
    finally { setLoading(false) }
  }
  React.useEffect(() => {
    let active = true
    async function load() {
      try {
        const { data } = await api.get(`/community/circles/${circle.id}`)
        if (!active) return
        setDetail(data.circle)
        if (data.circle.joined) {
          const response = await api.get(`/community/circles/${circle.id}/members`, { params: { page: 1 } })
          if (active) { setMembers(response.data.members); setTotal(response.data.total); setPage(response.data.page); setDetail((current) => ({ ...current, member_count: response.data.total })) }
        }
      } catch (failure) { if (active) setError(apiMessage(failure)) }
      finally { if (active) setLoading(false) }
    }
    load()
    return () => { active = false }
  }, [circle.id])
  async function join() {
    setBusy('join'); setError('')
    try {
      const { data } = await api.post(`/community/circles/${circle.id}/membership`)
      setDetail(data.circle); await onChanged?.(); setTab('members'); await loadMembers()
      message.success(t('You joined this circle.'))
    } catch (failure) { setError(apiMessage(failure)) }
    finally { setBusy(null) }
  }
  async function requestFriend(member) {
    setBusy(member.public_id)
    try {
      const { data } = await api.post('/community/connections', { circle_id: circle.id, public_id: member.public_id })
      setMembers((current) => current.map((item) => item.public_id === member.public_id ? { ...item, connection_status: 'outgoing', can_request: false, connection_id: data.connection.id } : item))
      message.success(t('Friend request sent. They choose whether to accept.'))
    } catch (failure) { message.error(apiMessage(failure)); await loadMembers(page) }
    finally { setBusy(null) }
  }
  function action(member) {
    if (member.connection_status === 'self') return <Tag>{t('You')}</Tag>
    if (member.connection_status === 'friends') return <Button onClick={() => onConnections(member.connection_id)}>{t('Message')}</Button>
    if (member.connection_status === 'incoming') return <Button onClick={() => onConnections()}>{t('Review friend request')}</Button>
    if (member.connection_status === 'outgoing') return <Tag color="blue">{t('Request sent')}</Tag>
    return <Button disabled={!member.can_request} loading={busy === member.public_id} onClick={() => requestFriend(member)}>{t('Add friend')}</Button>
  }
  return <Drawer className="community-drawer community-circle-details" title={detail.name} open onClose={onClose} size={560}>
    <Space wrap><Tag>{detail.topic}</Tag>{detail.joined && <Tag color="green">{t('Joined')}</Tag>}<Text type="secondary">{t('{count} visible members', { count: detail.member_count })}</Text></Space>
    {error && <Alert type="error" showIcon title={error} />}
    <Tabs activeKey={tab} onChange={setTab} items={[
      { key: 'about', label: t('About this circle'), children: <div className="circle-about"><Title level={4}>{t('What we talk about')}</Title><Paragraph>{detail.description}</Paragraph>{detail.guidance && <><Title level={5}>{t('Circle guidelines')}</Title><Paragraph type="secondary">{detail.guidance}</Paragraph></>}<Paragraph type="secondary">{t('Joining a circle does not share your health records. Anonymous posts keep their author private.')}</Paragraph><Space wrap>{detail.joined ? <><Button type="primary" onClick={() => onDiscussion(detail)}>{t('View discussions')}</Button><Button onClick={() => setTab('members')}>{t('Meet members')}</Button></> : <Button type="primary" loading={busy === 'join'} onClick={join}>{t('Join circle')}</Button>}</Space></div> },
      { key: 'members', label: t('Members'), children: !detail.joined ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('Join this circle to see its member directory.')}><Button type="primary" loading={busy === 'join'} onClick={join}>{t('Join circle')}</Button></Empty> : <div className="circle-member-directory"><Paragraph type="secondary">{t('Only members who allow discovery are listed here, along with your own profile. Anonymous posts never identify their author.')}</Paragraph><Button size="small" onClick={() => loadMembers(page)} loading={loading}>{t('Refresh members')}</Button>{loading ? <Skeleton active paragraph={{ rows: 3 }} /> : members.length ? <List dataSource={members} renderItem={(member) => <List.Item actions={[<React.Fragment key="connection">{action(member)}</React.Fragment>]}><List.Item.Meta avatar={<Avatar icon={<UserOutlined />} />} title={member.nickname} description={member.connection_status === 'friends' ? t('Already friends') : member.connection_status === 'self' ? t('Your community profile') : t('Circle member')} /></List.Item>} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('No discoverable members to show yet.')} />}{total > 20 && <Pagination current={page} pageSize={20} total={total} showSizeChanger={false} onChange={loadMembers} />}</div> },
    ]} />
  </Drawer>
}
