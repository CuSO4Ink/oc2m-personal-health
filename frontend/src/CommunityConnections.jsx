import React from 'react'
import { Alert, Avatar, Badge, Button, Card, Checkbox, Divider, Drawer, Dropdown, Empty, Form, Input, List, Modal, Popconfirm, Skeleton, Space, Tabs, Tag, Typography, message } from 'antd'
import { MessageOutlined, MoreOutlined, PlusOutlined, UserOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { useSearchParams } from 'react-router-dom'
import api, { apiMessage } from './api'
import Guidance from './Guidance'
import { useLanguage } from './i18n'
import './community.css'

const { Paragraph, Text, Title } = Typography

export function CommunitySettingsDrawer({ open, onClose, profile, onProfileChange, onDisable, saving }) {
  const { t } = useLanguage()
  const [form] = Form.useForm()
  const [busy, setBusy] = React.useState(false)
  React.useEffect(() => { if (open) form.setFieldsValue({ nickname: profile.nickname, discoverable: profile.discoverable }) }, [open, form, profile.nickname, profile.discoverable])
  async function save(values) {
    setBusy(true)
    try { const { data } = await api.patch('/community/identity', values); onProfileChange(data.profile); message.success(t('已保存社区身份。')); onClose() }
    catch (error) { message.error(apiMessage(error)) }
    finally { setBusy(false) }
  }
  async function replaceInvite() {
    setBusy(true)
    try { const { data } = await api.post('/community/identity/rotate-invite'); onProfileChange({ ...profile, invite_code: data.invite_code }); message.success(t('已更换邀请码。')) }
    catch (error) { message.error(apiMessage(error)) }
    finally { setBusy(false) }
  }
  return <Drawer className="community-drawer" title={t("社区设置")} open={open} onClose={onClose} size={480}>
    <Form form={form} layout="vertical" onFinish={save}>
      <Form.Item label={t("社区昵称")} name="nickname" extra={t("使用你愿意公开的昵称，与账号姓名分开。")} rules={[{ required: true, min: 2, max: 40, whitespace: true }]}><Input maxLength={40} /></Form.Item>
      <Form.Item name="discoverable" valuePropName="checked"><Checkbox>{t('Let people find me by nickname, non-anonymous posts, and the member lists of circles I join.')}</Checkbox></Form.Item>
      <Button type="primary" htmlType="submit" loading={busy}>{t("保存社区身份")}</Button>
    </Form>
    <Divider />
    <Title level={5}>{t("我的专属邀请码")}</Title><Paragraph type="secondary">{t("把邀请码私下告诉希望结识的人，对方申请后仍由你决定是否接受。")}</Paragraph>
    <div className="community-invite"><Text code copyable>{profile.invite_code}</Text><Popconfirm title={t("更换邀请码？")} description={t("旧邀请码立即失效，已有好友不受影响。")} onConfirm={replaceInvite}><Button loading={busy}>{t("更换邀请码")}</Button></Popconfirm></div>
    <Divider />
    <Guidance id="community-rules" title={t("社区规则与隐私")}>
      <Paragraph>{t("分享自己的经历和支持。不要诊断、开药、要求他人改变治疗、骚扰他人或强迫其提供资料；遇到不当内容、隐私问题或广告可举报。")}</Paragraph>
      <Paragraph>{t("档案、指标和预约不会自动加入帖子。匿名帖子不公开昵称及联系入口，双方接受好友关系后才能私聊。")}</Paragraph>
      <Paragraph>{t('Share only the personal details you feel comfortable sharing. For diagnosis or treatment, speak with a qualified professional.')}</Paragraph>
    </Guidance>
    <Divider />
    <Title level={5}>{t("暂时退出交流")}</Title><Paragraph type="secondary">{t("之后可在“账号与安全”重新开启。")}</Paragraph>
    <Popconfirm title={t("关闭病友交流？")} description={t("保留圈子及已有好友，取消待处理申请，暂停消息与提醒。重新开启后不会恢复旧的未读标记。")} onConfirm={onDisable} okText={t("关闭")}><Button danger loading={saving}>{t("关闭病友交流")}</Button></Popconfirm>
  </Drawer>
}

export default function CommunityConnections({ profile, onReport, onChanged, onOpenSettings }) {
  const { t } = useLanguage()
  const [params, setParams] = useSearchParams()
  const [connections, setConnections] = React.useState({ friends: [], incoming: [], outgoing: [] })
  const [members, setMembers] = React.useState([])
  const [search, setSearch] = React.useState('')
  const [invite, setInvite] = React.useState('')
  const [error, setError] = React.useState('')
  const [busy, setBusy] = React.useState(false)
  const [loading, setLoading] = React.useState(true)
  const [addOpen, setAddOpen] = React.useState(false)
  const [requestsOpen, setRequestsOpen] = React.useState(false)
  const [searched, setSearched] = React.useState(false)
  const [chat, setChat] = React.useState(null)
  const [messages, setMessages] = React.useState([])
  const [hasOlder, setHasOlder] = React.useState(false)
  const [chatError, setChatError] = React.useState('')
  const [olderLoading, setOlderLoading] = React.useState(false)
  const [sending, setSending] = React.useState(false)
  const [messageForm] = Form.useForm()
  const latestRef = React.useRef(0)
  const chatRef = React.useRef(null)
  const endRef = React.useRef(null)
  const deliveryRef = React.useRef(null)
  const lastMessageId = messages.at(-1)?.id

  const load = React.useCallback(async () => {
    try { const { data } = await api.get('/community/connections'); setConnections(data); setError(''); return data }
    catch (requestError) { setError(apiMessage(requestError)); return null }
  }, [])

  React.useEffect(() => {
    let active = true
    const refresh = async () => {
      if (document.visibilityState === 'hidden') return
      try { const { data } = await api.get('/community/connections'); if (active) { setConnections(data); setError('') } }
      catch (requestError) { if (active) setError(apiMessage(requestError)) }
      finally { if (active) setLoading(false) }
    }
    refresh()
    const timer = window.setInterval(refresh, 15000)
    document.addEventListener('visibilitychange', refresh)
    return () => { active = false; window.clearInterval(timer); document.removeEventListener('visibilitychange', refresh) }
  }, [])

  const openChat = React.useCallback((connection) => {
    chatRef.current = connection.id; latestRef.current = 0; deliveryRef.current = null
    setChat(connection); setMessages([]); setHasOlder(false); setChatError(''); messageForm.resetFields()
  }, [messageForm])

  React.useEffect(() => {
    const id = Number(params.get('conversation'))
    const friend = connections.friends.find((item) => item.id === id)
    if (friend && chatRef.current !== id) {
      // A notification deep link explicitly selects this conversation.
      openChat(friend)
    }
  }, [connections.friends, openChat, params])

  React.useEffect(() => {
    if (!chat) return
    let active = true
    let requesting = false
    const refresh = async () => {
      if (requesting || document.visibilityState === 'hidden') return
      requesting = true
      try {
        const { data } = await api.get(`/community/connections/${chat.id}/messages`, { params: latestRef.current ? { after_id: latestRef.current, limit: 100 } : { limit: 30 } })
        if (!active) return
        setChatError('')
        if (!latestRef.current) setHasOlder(data.has_more)
        if (data.messages.length) {
          const through = data.messages[data.messages.length - 1].id
          latestRef.current = through
          setMessages((current) => [...current, ...data.messages.filter((item) => !current.some((existing) => existing.id === item.id))])
          if (data.messages.some((item) => !item.is_owner && !item.read)) {
            await api.patch(`/community/connections/${chat.id}/messages/read`, { through_id: through })
            if (active) await load()
          }
        }
        if (!data.connection.can_message) setChatError(t('该成员暂不可联系。历史消息保留，发送已暂停。'))
      } catch (requestError) { if (active) setChatError(apiMessage(requestError)) }
      finally { requesting = false }
    }
    refresh()
    const timer = window.setInterval(refresh, 8000)
    document.addEventListener('visibilitychange', refresh)
    return () => { active = false; window.clearInterval(timer); document.removeEventListener('visibilitychange', refresh) }
  }, [chat, load, t])

  React.useEffect(() => { if (lastMessageId) endRef.current?.scrollIntoView({ block: 'nearest' }) }, [lastMessageId])

  async function mutate(action) {
    setBusy(true)
    try { await action(); await load(); onChanged?.() }
    catch (requestError) { message.error(apiMessage(requestError)) }
    finally { setBusy(false) }
  }

  async function requestFriend(payload) {
    await mutate(async () => { await api.post('/community/connections', payload); setInvite(''); message.success(t('好友申请已发送，对方接受后可以私聊。')) })
  }

  async function searchMembers() {
    setBusy(true)
    if (search.trim().length < 2) { setBusy(false); return }
    try { setMembers((await api.get('/community/members', { params: { q: search } })).data.members); setSearched(true) }
    catch (requestError) { message.error(apiMessage(requestError)) }
    finally { setBusy(false) }
  }

  function closeChat() {
    chatRef.current = null; setChat(null)
    if (params.has('conversation')) { const next = new URLSearchParams(params); next.delete('conversation'); setParams(next, { replace: true }) }
  }

  function closeRequests() {
    setRequestsOpen(false)
    if (params.has('requests')) { const next = new URLSearchParams(params); next.delete('requests'); setParams(next, { replace: true }) }
  }

  async function send(values) {
    setSending(true)
    const id = chat.id
    try {
      if (!deliveryRef.current || deliveryRef.current.connection !== id || deliveryRef.current.body !== values.body) {
        deliveryRef.current = { connection: id, body: values.body, nonce: crypto.randomUUID() }
      }
      await api.post(`/community/connections/${id}/messages`, { ...values, client_nonce: deliveryRef.current.nonce })
      if (chatRef.current !== id) return
      deliveryRef.current = null
      messageForm.resetFields()
      const { data } = await api.get(`/community/connections/${id}/messages`, { params: { after_id: latestRef.current, limit: 100 } })
      if (chatRef.current !== id) return
      if (data.messages.length) {
        latestRef.current = data.messages.at(-1).id
        setMessages((current) => [...current, ...data.messages.filter((item) => !current.some((existing) => existing.id === item.id))])
        await api.patch(`/community/connections/${id}/messages/read`, { through_id: latestRef.current })
      }
      await load()
    } catch (requestError) { message.error(apiMessage(requestError)) }
    finally { setSending(false) }
  }

  async function older() {
    setOlderLoading(true)
    const id = chat.id
    try {
      const { data } = await api.get(`/community/connections/${id}/messages`, { params: { before_id: messages[0].id, limit: 30 } })
      if (chatRef.current !== id) return
      setMessages((current) => [...data.messages, ...current]); setHasOlder(data.has_more)
    } catch (requestError) { message.error(apiMessage(requestError)) }
    finally { setOlderLoading(false) }
  }

  return <div className="community-connections">
    {error && <Alert type="error" showIcon message={error} action={<Button onClick={load}>{t("重试")}</Button>} />}
    <div className="community-section-heading">
      <div><Title level={3}>{t("好友与私聊")}</Title><Text type="secondary">{t("双方成为好友后，即可开始文字私聊。")}</Text></div>
      <Space wrap><Button onClick={() => setRequestsOpen(true)}>{t("好友申请 ")}<Badge count={connections.incoming.length} /></Button><Button type="primary" icon={<PlusOutlined />} onClick={() => setAddOpen(true)}>{t("添加好友")}</Button></Space>
    </div>
    {connections.incoming.length > 0 && <div className="community-request-notice"><Text>{t("有 ")}{connections.incoming.length}{t(" 条好友申请待处理。")}</Text><Button type="link" onClick={() => setRequestsOpen(true)}>{t("查看申请")}</Button></div>}
    <Card className="community-friends-card">
      {loading ? <Skeleton active paragraph={{ rows: 3 }} /> : connections.friends.length ? <List dataSource={connections.friends} renderItem={(connection) => <List.Item actions={[
        <Button key="chat" icon={<MessageOutlined />} onClick={() => openChat(connection)}>{t("消息 ")}<Badge count={connection.unread} /></Button>,
        <Dropdown key="more" trigger={['click']} menu={{ items: [{ key: 'remove', label: t('解除好友') }, { key: 'block', label: t('拉黑成员'), danger: true }], onClick: ({ key }) => Modal.confirm({ title: key === 'block' ? t('拉黑这个成员？') : t('解除好友关系？'), content: key === 'block' ? t('双方将无法继续联系，解除拉黑不会自动恢复好友。') : t('双方将无法发送消息，需要重新申请并接受好友。'), okText: key === 'block' ? t('拉黑成员') : t('解除好友'), okButtonProps: { danger: true }, onOk: () => mutate(() => key === 'block' ? api.post('/community/connections/' + connection.id + '/block') : api.patch('/community/connections/' + connection.id, { action: 'remove' })) }) }}><Button type="text" aria-label={t('好友菜单：') + connection.nickname} icon={<MoreOutlined />} /></Dropdown>
      ]}><List.Item.Meta avatar={<Avatar icon={<UserOutlined />} />} title={<Space wrap><Text strong>{connection.nickname}</Text>{!connection.can_message && <Tag>{t("暂不可联系")}</Tag>}</Space>} description={connection.unread ? connection.unread + t(' 条未读消息') : t('私聊')} /></List.Item>} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={<><Text strong>{t("你的好友会话会显示在这里")}</Text><Paragraph type="secondary">{t("通过邀请码或公开昵称添加好友。")}</Paragraph></>}><Button type="primary" onClick={() => setAddOpen(true)}>{t("添加第一位好友")}</Button></Empty>}
    </Card>
    <Guidance id="community-friends" title={t("好友关系与隐私")}><Paragraph>{t('Your community nickname is separate from your account name and health records. Anonymous posts keep their author private. Only accepted friends can message you, and blocking stops contact.')}</Paragraph><Button size="small" onClick={onOpenSettings}>{t("修改昵称与隐私")}</Button></Guidance>
    <Drawer className="community-drawer" title={t("添加好友")} open={addOpen} onClose={() => setAddOpen(false)} size={480}>
      <Title level={5}>{t("使用对方邀请码")}</Title>
      <Space.Compact className="community-search"><Input aria-label={t("好友邀请码")} placeholder={t("粘贴对方的邀请码")} value={invite} onChange={(event) => setInvite(event.target.value)} /><Button type="primary" disabled={!invite.trim()} loading={busy} onClick={() => requestFriend({ invite_code: invite })}>{t("发送申请")}</Button></Space.Compact>
      <Divider /><Title level={5}>{t("搜索公开昵称")}</Title>
      <Space.Compact className="community-search"><Input aria-label={t("搜索社区昵称")} placeholder={t("至少输入 2 个字符")} value={search} onChange={(event) => { setSearch(event.target.value); setSearched(false) }} onPressEnter={searchMembers} /><Button disabled={search.trim().length < 2} loading={busy} onClick={searchMembers}>{t("查找成员")}</Button></Space.Compact>
      {members.length > 0 ? <List dataSource={members} renderItem={(member) => <List.Item actions={[<Button key="invite" loading={busy} onClick={() => requestFriend({ public_id: member.public_id })}>{t("申请好友")}</Button>]}><Text>{member.nickname}</Text></List.Item>} /> : searched ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("未找到公开昵称，试试其他关键词或使用邀请码。")} /> : <Paragraph type="secondary">{t("这里只显示主动允许被搜索的成员。")}</Paragraph>}
      <Divider /><Title level={5}>{t("邀请对方找到我")}</Title><Paragraph type="secondary">{t("私下分享你的邀请码，对方申请后可接受或拒绝。")}</Paragraph><Text code copyable>{profile.invite_code}</Text>
      <div className="community-drawer-footer"><Button onClick={() => { setAddOpen(false); onOpenSettings?.() }}>{t("修改昵称与隐私")}</Button></div>
    </Drawer>
    <Drawer className="community-drawer" title={t("好友申请")} open={requestsOpen || params.get('requests') === '1'} onClose={closeRequests} size={480}>
      <Tabs items={[['incoming', t('收到的')], ['outgoing', t('发出的')]].map(([key, title]) => ({ key, label: title + ' (' + connections[key].length + ')', children: connections[key].length ? <List dataSource={connections[key]} renderItem={(connection) => <List.Item actions={(key === 'incoming' ? ['accept', 'reject'] : ['withdraw']).map((action) => <Button key={action} loading={busy} type={action === 'accept' ? 'primary' : 'default'} onClick={() => mutate(() => api.patch('/community/connections/' + connection.id, { action }))}>{{ accept: t('接受'), reject: t('拒绝'), withdraw: t('撤回') }[action]}</Button>)}><List.Item.Meta avatar={<Avatar icon={<UserOutlined />} />} title={connection.nickname} description={key === 'incoming' ? t('希望与你成为好友') : t('等待对方接受')} /></List.Item>} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={key === 'incoming' ? t('暂无收到的申请') : t('暂无待处理的已发送申请')} /> }))} />
    </Drawer>
    <Modal className="community-chat-modal" width={760} title={chat ? t(`私聊 · ${chat.nickname}`) : t('私聊')} open={Boolean(chat)} onCancel={closeChat} footer={null} destroyOnHidden>
      <Guidance id="community-chat" title={t("关于私信")}><Paragraph>{t('Offer support and share everyday experiences. Respect boundaries: do not pressure someone to share personal information or change their treatment.')}</Paragraph></Guidance>
      {chatError && <Alert type="warning" showIcon message={chatError} />}
      <div className="community-message-list" role="log" aria-live="polite" aria-label={t("私聊消息")}>
        {hasOlder && <Button loading={olderLoading} onClick={older}>{t("加载更早消息")}</Button>}
        {!messages.length && !chatError && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("还没有消息，先打个招呼吧。")} />}
        {messages.map((item) => <div key={item.id} className={`community-message ${item.is_owner ? 'mine' : ''}`}><Text strong>{item.is_owner ? t('我') : chat?.nickname}</Text><Paragraph>{item.body}</Paragraph><Space><Text type="secondary">{dayjs(item.created_at).format('YYYY-MM-DD HH:mm')}</Text>{!item.is_owner && <Button size="small" type="link" onClick={() => onReport(item, 'message')}>{t("举报私信")}</Button>}</Space></div>)}<div ref={endRef} />
      </div>
      <Form form={messageForm} onFinish={send}><Form.Item name="body" rules={[{ required: true, whitespace: true, max: 2000, message: t('请输入最多 2000 个字符。') }]}><Input.TextArea aria-label={t("私信内容")} rows={3} maxLength={2000} showCount placeholder={t("输入私信内容")} disabled={Boolean(chatError)} /></Form.Item><div className="community-message-actions"><Popconfirm title={t("拉黑这个成员？")} onConfirm={() => mutate(async () => { await api.post(`/community/connections/${chat.id}/block`); closeChat() })}><Button danger>{t("拉黑成员")}</Button></Popconfirm><Button type="primary" htmlType="submit" loading={sending} disabled={Boolean(chatError)}>{t("发送消息")}</Button></div></Form>
    </Modal>
  </div>
}
