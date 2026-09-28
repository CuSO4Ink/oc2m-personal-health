import React from 'react'
import { CommentOutlined, FlagOutlined, HeartFilled, HeartOutlined, LockOutlined, MoreOutlined, PlusOutlined, SearchOutlined, SettingOutlined, TeamOutlined, UserOutlined } from '@ant-design/icons'
import { Alert, Avatar, Button, Card, Checkbox, Drawer, Dropdown, Empty, Form, Input, List, Modal, Popconfirm, Select, Skeleton, Space, Tabs, Tag, Typography, message } from 'antd'
import dayjs from 'dayjs'
import api, { apiMessage } from './api'
import { useSearchParams } from 'react-router-dom'
import CommunityConnections, { CommunitySettingsDrawer } from './CommunityConnections'
import Guidance from './Guidance'
import CircleDetailsDrawer from './CircleDetailsDrawer'
import { useLanguage, t } from './i18n'
import './community.css'

const { Title, Paragraph, Text } = Typography
const formatDate = (value) => dayjs(value).format('YYYY-MM-DD HH:mm')

function NicknameHint({ profile, onChoose }) {
  useLanguage()
  const storageKey = `community-nickname-hint:${profile.public_id}`
  const [dismissed, setDismissed] = React.useState(() => { try { return localStorage.getItem(storageKey) === 'done' } catch { return false } })
  if (dismissed || !/^Member [0-9a-f]{6}$/i.test(profile.nickname || '')) return null
  function finish(choose) {
    setDismissed(true)
    try { localStorage.setItem(storageKey, 'done') } catch { /* Storage is optional. */ }
    if (choose) onChoose()
  }
  return <div className="community-nickname-hint"><Text>{t("当前交流昵称为 ")}<strong>{profile.nickname}</strong>{t("，也可以设置你喜欢的昵称。")}</Text><Space><Button size="small" onClick={() => finish(true)}>{t("设置昵称")}</Button><Button size="small" type="text" onClick={() => finish(false)}>{t("稍后")}</Button></Space></div>
}

export default function CommunityPage() {
  const { t } = useLanguage()
  const [params, setParams] = useSearchParams()
  const [blocks, setBlocks] = React.useState([])
  const [reports, setReports] = React.useState([])
  const [profile, setProfile] = React.useState(null)
  const [circles, setCircles] = React.useState([])
  const [selectedCircle, setSelectedCircle] = React.useState(null)
  const [posts, setPosts] = React.useState([])
  const [postHasMore, setPostHasMore] = React.useState(false)
  const [postLoading, setPostLoading] = React.useState(false)
  const [safety, setSafety] = React.useState(null)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState('')
  const [saving, setSaving] = React.useState(false)
  const [postOpen, setPostOpen] = React.useState(false)
  const [reportPost, setReportPost] = React.useState(null)
  const [commenting, setCommenting] = React.useState(null)
  const [search, setSearch] = React.useState('')
  const [circleFilter, setCircleFilter] = React.useState('all')
  const [settingsOpen, setSettingsOpen] = React.useState(false)
  const [reportsOpen, setReportsOpen] = React.useState(false)
  const [postForm] = Form.useForm()
  const [reportForm] = Form.useForm()
  const [commentForm] = Form.useForm()

  const load = React.useCallback(async () => {
    setError('')
    try {
      const response = await api.get('/community')
      setProfile(response.data.profile); setCircles(response.data.circles)
      setPosts(response.data.posts); setPostHasMore(response.data.has_more || false); setSafety(response.data.safety); setBlocks(response.data.blocks); setReports(response.data.reports)
    } catch (requestError) { setError(apiMessage(requestError)) }
    finally { setLoading(false) }
  }, [])

  React.useEffect(() => {
    let active = true
    api.get('/community').then((response) => {
      if (!active) return
      setProfile(response.data.profile); setCircles(response.data.circles)
      setPosts(response.data.posts); setPostHasMore(response.data.has_more || false); setSafety(response.data.safety); setBlocks(response.data.blocks); setReports(response.data.reports)
    }).catch((requestError) => { if (active) setError(apiMessage(requestError)) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  async function setCommunityEnabled(enabled) {
    setSaving(true)
    try {
      const response = await api.patch('/community/profile', { enabled })
      setProfile(response.data.profile)
      window.dispatchEvent(new Event('community:changed'))
      if (enabled) { message.success(t('已为当前账号开启病友交流。')); await load() }
      else { setPosts([]); setSettingsOpen(false); setReportsOpen(false); setParams({}); message.success(t('已关闭病友交流，社区动态和消息提醒将暂停。')) }
    } catch (requestError) { message.error(apiMessage(requestError)) }
    finally { setSaving(false) }
  }

  async function changeMembership(circle, join) {
    try {
      if (join) await api.post(`/community/circles/${circle.id}/membership`)
      else await api.delete(`/community/circles/${circle.id}/membership`)
      if (!join && circleFilter === circle.id) setCircleFilter('all')
      message.success(join ? t(`已加入 ${circle.name}。`) : t(`已退出 ${circle.name}。`))
      await load()
    } catch (requestError) { message.error(apiMessage(requestError)) }
  }

  function openPostComposer() {
    const joined = circles.filter((circle) => circle.joined)
    postForm.resetFields(); postForm.setFieldsValue({ circle_id: joined[0]?.id, anonymous: true, acknowledged: false })
    setPostOpen(true)
  }

  async function createPost(values) {
    setSaving(true)
    try { await api.post('/community/posts', values); message.success(t('已发布你的经历。')); setPostOpen(false); await load() }
    catch (requestError) { message.error(apiMessage(requestError)) }
    finally { setSaving(false) }
  }

  async function toggleLike(post) {
    try {
      const response = await api.post(`/community/posts/${post.id}/like`)
      setPosts((current) => current.map((item) => item.id === post.id ? response.data.post : item))
    } catch (requestError) { message.error(apiMessage(requestError)) }
  }

  function openComments(post) {
    commentForm.resetFields(); commentForm.setFieldsValue({ anonymous: true }); setCommenting(commenting === post.id ? null : post.id)
  }

  async function addComment(values) {
    setSaving(true)
    try {
      const response = await api.post(`/community/posts/${commenting}/comments`, values)
      setPosts((current) => current.map((item) => item.id === commenting ? response.data.post : item))
      commentForm.resetFields(); commentForm.setFieldsValue({ anonymous: true }); message.success(t('已发表评论。'))
    } catch (requestError) { message.error(apiMessage(requestError)) }
    finally { setSaving(false) }
  }

  async function deletePost(postId) {
    try { await api.delete(`/community/posts/${postId}`); message.success(t('已删除帖子。')); await load() }
    catch (requestError) { message.error(apiMessage(requestError)) }
  }

  function openReport(post, kind = 'post') { reportForm.resetFields(); setReportPost({...post, target_type: kind}) }

  async function submitReport(values) {
    setSaving(true)
    try { await api.post(`/community/${reportPost.target_type === 'comment' ? 'comments' : reportPost.target_type === 'message' ? 'messages' : 'posts'}/${reportPost.id}/reports`, values); message.success(t('Report submitted. Status: pending review.')); setReportPost(null); await load() }
    catch (requestError) { message.error(apiMessage(requestError)) }
    finally { setSaving(false) }
  }

  async function deleteComment(id) {
    try { await api.delete(`/community/comments/${id}`); message.success(t('已删除评论。')); await load() }
    catch(error) {message.error(apiMessage(error))}
  }
  async function blockMember(target, kind) {
    try {await api.post('/community/blocks', {target_type: kind, target_id: target.id}); message.success(t('已拉黑该成员。')); setCommenting(null); await load()}
    catch(error) {message.error(apiMessage(error))}
  }
  async function unblockMember(id) {
    try {await api.delete(`/community/blocks/${id}`); message.success(t('已解除拉黑。')); await load()}
    catch(error) {message.error(apiMessage(error))}
  }

  async function searchPosts(more = false) {
    setPostLoading(true)
    try {
      const { data } = await api.get('/community/posts', {params: {q: search, circle_id: circleFilter === 'all' ? undefined : circleFilter, before_id: more ? posts.at(-1)?.id : undefined}})
      setPosts((current) => more ? [...current, ...data.posts.filter((post) => !current.some((existing) => existing.id === post.id))] : data.posts); setPostHasMore(data.has_more || false)
    } catch (error) { message.error(apiMessage(error)) }
    finally { setPostLoading(false) }
  }

  async function simulateReview(id) {
    try { const { data } = await api.post(`/community/reports/${id}/simulate-review`); setReports(data.reports); message.info(data.message) }
    catch (error) { message.error(apiMessage(error)) }
  }

  async function requestPostFriend(postId) {
    try { await api.post('/community/connections', {post_id: postId}); message.success(t('好友申请已发送，对方接受后才能私聊。')) }
    catch (error) { message.error(apiMessage(error)) }
  }

  const joinedCircles = circles.filter((circle) => circle.joined)
  const filteredPosts = posts.filter((post) => (circleFilter === 'all' || post.circle.id === circleFilter) && post.body.toLowerCase().includes(search.toLowerCase()))

  function changeTab(tab) { setParams({ tab }) }
  function closeUtility(kind) {
    if (kind === 'settings') setSettingsOpen(false)
    else setReportsOpen(false)
    if (['guidance', 'management'].includes(params.get('tab'))) setParams({ tab: 'feed' }, { replace: true })
  }
  function confirmBlock(target, kind) {
    Modal.confirm({ title: t('拉黑这个成员？'), content: t('双方动态和评论将隐藏，也无法互相联系。匿名身份仍保密；解除拉黑不会自动恢复好友。'), okText: t('拉黑成员'), okButtonProps: { danger: true }, onOk: () => blockMember(target, kind) })
  }
  function postMenu(post) {
    const items = post.is_owner ? [{ key: 'delete', label: t('删除帖子'), danger: true }] : [
      ...(post.can_connect ? [{ key: 'friend', label: t('申请好友') }] : []),
      { key: 'report', label: t('举报帖子') }, { key: 'block', label: t('拉黑成员'), danger: true }
    ]
    return { items, onClick: ({ key }) => {
      if (key === 'report') openReport(post)
      if (key === 'friend') requestPostFriend(post.id)
      if (key === 'block') confirmBlock(post, 'post')
      if (key === 'delete') Modal.confirm({ title: t('删除这个帖子？'), content: t('该帖子及评论将从动态中移除。'), okText: t('删除帖子'), okButtonProps: { danger: true }, onOk: () => deletePost(post.id) })
    } }
  }

  const feedPanel = <div className="community-panel community-feed-panel">
    <div className="community-section-heading"><div><Title level={3}>{t("我的动态")}</Title><Text type="secondary">{t("查看你加入圈子里的日常经历。")}</Text></div><Button type="primary" icon={<PlusOutlined />} disabled={!joinedCircles.length} onClick={openPostComposer}>{t("分享经历")}</Button></div>
    {joinedCircles.length > 0 && <div className="community-feed-filters">
      <Input allowClear aria-label={t("搜索圈子帖子")} prefix={<SearchOutlined />} placeholder={t("搜索经历")} value={search} onChange={(event) => setSearch(event.target.value)} onPressEnter={() => searchPosts()} />
      <Select aria-label={t("筛选圈子")} value={circleFilter} onChange={setCircleFilter} options={[{ value: 'all', label: t('全部已加入圈子') }, ...joinedCircles.map((circle) => ({ value: circle.id, label: circle.name }))]} />
      <Button loading={postLoading} onClick={() => searchPosts()}>{t("搜索")}</Button>
    </div>}
    {!joinedCircles.length ? <Card className="community-empty-card"><Empty image={<TeamOutlined className="community-empty-icon" />} description={<><Title level={4}>{t("找到适合你的圈子")}</Title><Paragraph>{t("先加入一个圈子，再阅读和分享日常健康经历。")}</Paragraph></>}><Button type="primary" onClick={() => changeTab('circles')}>{t("浏览圈子")}</Button></Empty></Card>
      : filteredPosts.length === 0 ? <Card className="community-empty-card"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={<><Text strong>{search || circleFilter !== 'all' ? t('没有符合筛选条件的帖子') : t('来聊聊你的日常经历')}</Text><Paragraph type="secondary">{search || circleFilter !== 'all' ? t('换个关键词，或查看全部已加入圈子。') : t('分享一点日常经验，也可以向病友寻求支持。')}</Paragraph></>}>
        {search || circleFilter !== 'all' ? <Button onClick={() => { setSearch(''); setCircleFilter('all'); load() }}>{t("清除筛选")}</Button> : <Button type="primary" onClick={openPostComposer}>{t("分享第一条经历")}</Button>}
      </Empty></Card>
      : <div className="community-feed">{filteredPosts.map((post) => <Card key={post.id} className="community-post">
        <div className="community-post-heading"><div className="post-author"><Avatar icon={post.anonymous ? <LockOutlined /> : <UserOutlined />} /><div><Space wrap><Text strong>{post.author_name}</Text>{post.is_owner && <Tag>{t("我的帖子")}</Tag>}</Space><div className="community-post-meta"><Text>{post.circle.name}</Text><span aria-hidden="true">·</span><Text type="secondary">{formatDate(post.created_at)}</Text></div></div></div><Dropdown trigger={['click']} menu={postMenu(post)}><Button type="text" aria-label={t('帖子菜单：') + post.author_name} icon={<MoreOutlined />} /></Dropdown></div>
        <Paragraph className="post-body">{post.body}</Paragraph>
        <div className="post-actions"><Button type="text" icon={post.liked ? <HeartFilled className="liked" /> : <HeartOutlined />} aria-pressed={post.liked} onClick={() => toggleLike(post)}>{post.like_count}{t(" 人觉得有帮助")}</Button><Button type="text" icon={<CommentOutlined />} aria-expanded={commenting === post.id} onClick={() => openComments(post)}>{post.comment_count}{t(" 条评论")}</Button><Text type="secondary" className="community-peer-label">{t("病友经历")}</Text></div>
        {commenting === post.id && <div className="community-comments">
          {post.comments.length > 0 && <List className="comment-list" dataSource={post.comments} renderItem={(comment) => <List.Item actions={comment.is_owner ? [<Popconfirm key="delete" title={t("删除这条评论？")} onConfirm={() => deleteComment(comment.id)}><Button danger type="link" size="small">{t("删除")}</Button></Popconfirm>] : [<Button key="report" type="link" size="small" onClick={() => openReport(comment, 'comment')}>{t("举报")}</Button>, <Button key="block" danger type="link" size="small" onClick={() => confirmBlock(comment, 'comment')}>{t("拉黑")}</Button>]}><List.Item.Meta avatar={<Avatar size="small" icon={comment.anonymous ? <LockOutlined /> : <UserOutlined />} />} title={<Space wrap><Text strong>{comment.author_name}</Text><Text type="secondary">{formatDate(comment.created_at)}</Text></Space>} description={comment.body} /></List.Item>} />}
          <Form className="comment-form" form={commentForm} layout="vertical" onFinish={addComment}><Form.Item name="body" rules={[{ required: true, min: 2, max: 500, message: t('评论需为 2 至 500 个字符') }]}><Input.TextArea aria-label={t("我的评论")} rows={2} placeholder={t("分享支持或自己的经历")} maxLength={500} showCount /></Form.Item><div className="comment-controls"><Form.Item name="anonymous" valuePropName="checked" noStyle><Checkbox>{t("匿名评论")}</Checkbox></Form.Item><Space><Button onClick={() => setCommenting(null)}>{t("关闭")}</Button><Button type="primary" htmlType="submit" loading={saving}>{t("评论")}</Button></Space></div></Form>
        </div>}
      </Card>)}</div>}
    {postHasMore && joinedCircles.length > 0 && <Button className="community-load-more" loading={postLoading} onClick={() => searchPosts(true)}>{t("加载更多经历")}</Button>}
    <Guidance id="community-intro" title={t("病友交流如何使用")}><Paragraph>{t("这里交流个人经历，不提供诊断或治疗指令。健康档案保持独立；匿名帖子不展示昵称和联系入口。帖子菜单可举报或拉黑，社区设置中可查看规则。")}</Paragraph></Guidance>
  </div>

  const circlesPanel = <div className="community-panel">
    <div className="community-section-heading"><div><Title level={3}>{t("发现圈子")}</Title><Text type="secondary">{t("选择感兴趣的圈子，随时加入或退出。")}</Text></div><Tag>{t("已加入 ")}{joinedCircles.length}{t(" 个")}</Tag></div>
    <div className="community-circle-grid">{circles.map((circle) => <Card key={circle.id} className="community-circle-card">
      <div className="community-circle-title"><Tag color={circle.joined ? 'green' : 'blue'}>{circle.joined ? t('已加入') : circle.topic}</Tag><Text type="secondary"><TeamOutlined /> {t('{count} visible members', { count: circle.member_count })}</Text></div>
      <Title level={4}>{circle.name}</Title><Paragraph>{circle.description}</Paragraph>
      <Button onClick={() => setSelectedCircle(circle)}>{t('About & members')}</Button>
      {circle.guidance && <details className="community-circle-guidance"><summary>{t("圈子说明")}</summary><Paragraph type="secondary">{circle.guidance}</Paragraph></details>}
      <div className="community-circle-actions">{circle.joined ? <><Button type="primary" onClick={() => { setCircleFilter(circle.id); setSearch(''); changeTab('feed') }}>{t("查看动态")}</Button><Popconfirm title={t('退出 ') + circle.name + '？'} description={t("退出后，其帖子不再出现在你的动态中。")} onConfirm={() => changeMembership(circle, false)}><Button type="text">{t("退出圈子")}</Button></Popconfirm></> : <Button type="primary" onClick={() => changeMembership(circle, true)}>{t("加入圈子")}</Button>}</div>
    </Card>)}</div>
    {!circles.length && <Empty description={t("暂时没有圈子，你仍可以添加好友。")}><Button onClick={() => changeTab('connections')}>{t("寻找好友")}</Button></Empty>}
  </div>

  const reportList = <div className="community-management">
    <Paragraph type="secondary">{t('Reports stay pending until a review outcome is recorded.')}</Paragraph>
    {reports.length ? <List pagination={{pageSize: 8}} dataSource={reports} renderItem={(report) => <List.Item><div className="community-report-row"><Space wrap><Text strong>{report.target_type === 'comment' ? t('评论举报') : report.target_type === 'message' ? t('私信举报') : t('帖子举报')}</Text><Tag color="orange">{report.status === 'submitted' ? t('Pending review') : report.status}</Tag>{report.simulation_stage && <Tag color="gold">{t(report.simulation_stage === 'in_review' ? 'Reviewing (demo)' : 'Completed (demo)')}</Tag>}</Space><Text type="secondary">{report.reason.replaceAll('_', ' ')} · {formatDate(report.created_at)}</Text>{report.details && <Paragraph>{report.details}</Paragraph>}{report.simulation_note && <Paragraph type="secondary">{t('Demo review only illustrates the steps. It does not resolve your report or remove content.')}</Paragraph>}{report.simulation_stage !== 'closed_demo' && <Button size="small" disabled={safety?.demo_review_available === false} onClick={() => simulateReview(report.id)}>{t(report.simulation_stage ? 'Demo result' : 'Demo review')}</Button>}</div></List.Item>} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("暂无举报。遇到不妥内容时，可在帖子、评论或私信中举报。")} />}
  </div>
  const blockedList = <div className="community-management"><Paragraph type="secondary">{t("拉黑会停止双方联系并隐藏双方内容。解除拉黑不会恢复好友，也不会公开匿名身份。")}</Paragraph>{blocks.length ? <List dataSource={blocks} renderItem={(block) => <List.Item actions={[<Popconfirm key="unblock" title={t("解除拉黑？")} description={t("对方可以再次互动，之前解除的好友关系不会自动恢复。")} onConfirm={() => unblockMember(block.id)}><Button>{t("解除拉黑")}</Button></Popconfirm>]}><List.Item.Meta title={block.label} description={t('拉黑时间：') + formatDate(block.created_at)} /></List.Item>} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("暂无拉黑成员")} />}</div>

  return <div className="page-stack community-page">
    <div className="page-heading community-heading"><div><Title level={1}>{t("病友交流")}</Title><Paragraph>{t("交流日常经历，自主选择圈子和好友。")}</Paragraph></div>{profile?.enabled && <Space wrap><Button icon={<FlagOutlined />} onClick={() => setReportsOpen(true)}>{t("举报与拉黑")}</Button><Button icon={<SettingOutlined />} onClick={() => setSettingsOpen(true)}>{t("社区设置")}</Button></Space>}</div>
    {error && <Alert type="error" showIcon message={t("暂时无法加载病友交流")} description={error} action={<Button onClick={load}>{t("重试")}</Button>} />}
    {loading ? <Card><Skeleton active paragraph={{ rows: 6 }} /></Card> : profile && (!profile.enabled ? <Card className="community-off-card"><TeamOutlined className="community-empty-icon" /><Title level={2}>{t("和病友交流经历")}</Title><Paragraph>{t("病友交流当前关闭。开启后可用昵称或匿名发帖、加入圈子和结交好友；健康档案保持独立。")}</Paragraph><Button type="primary" loading={saving} onClick={() => setCommunityEnabled(true)}>{t("开启病友交流")}</Button></Card> : <>
      <NicknameHint key={profile.public_id} profile={profile} onChoose={() => setSettingsOpen(true)} />
      <Tabs className="community-main-tabs" activeKey={['feed', 'circles', 'connections'].includes(params.get('tab')) ? params.get('tab') : 'feed'} onChange={changeTab} items={[
        { key: 'feed', label: t('动态'), children: feedPanel },
        { key: 'circles', label: t('圈子'), children: circlesPanel },
        { key: 'connections', label: t('好友与私聊'), children: <CommunityConnections profile={profile} onReport={openReport} onChanged={load} onOpenSettings={() => setSettingsOpen(true)} /> }
      ]} />
      <CommunitySettingsDrawer open={settingsOpen || params.get('tab') === 'guidance'} onClose={() => closeUtility('settings')} profile={profile} onProfileChange={setProfile} onDisable={() => setCommunityEnabled(false)} saving={saving} />
      {selectedCircle && <CircleDetailsDrawer key={selectedCircle.id} circle={selectedCircle} onClose={() => setSelectedCircle(null)} onChanged={load} onDiscussion={(circle) => { setSelectedCircle(null); setCircleFilter(circle.id); setSearch(''); changeTab('feed') }} onConnections={(id) => { setSelectedCircle(null); setParams(id ? { tab: 'connections', conversation: String(id) } : { tab: 'connections', requests: '1' }) }} />}
      <Drawer className="community-drawer" title={t("举报与拉黑")} open={reportsOpen || params.get('tab') === 'management'} onClose={() => closeUtility('reports')} size={560}><Tabs items={[{ key: 'reports', label: t('我的举报（') + reports.length + ')', children: reportList }, { key: 'blocks', label: t('已拉黑（') + blocks.length + ')', children: blockedList }]} /></Drawer>
    </>)}

    <Modal title={t("分享我的经历")} open={postOpen} onCancel={() => setPostOpen(false)} footer={null} destroyOnHidden><Guidance id="community-composer" title={t("发布与隐私")}><Paragraph>{t("只发布你主动填写的文字，不会复制健康档案。匿名帖子隐藏昵称与联系入口。两次发帖间隔至少 30 秒，评论间隔至少 10 秒。")}</Paragraph></Guidance><Form className="community-form" form={postForm} layout="vertical" onFinish={createPost}><Form.Item label={t("圈子")} name="circle_id" rules={[{ required: true, message: t('请选择圈子') }]}><Select options={joinedCircles.map((circle) => ({ value: circle.id, label: circle.name }))} /></Form.Item><Form.Item label={t("我的经历")} name="body" rules={[{ required: true, min: 3, max: 1200, message: t('请输入 3 至 1200 个字符') }]}><Input.TextArea rows={6} maxLength={1200} showCount placeholder={t("聊聊你的经历、日常管理经验，或向专业人员咨询过的问题。")} /></Form.Item><Form.Item name="anonymous" valuePropName="checked"><Checkbox>{t("匿名发布")}</Checkbox></Form.Item><Form.Item name="acknowledged" valuePropName="checked" rules={[{ validator: (_, value) => value ? Promise.resolve() : Promise.reject(new Error(t('发布前请确认交流规则'))) }]}><Checkbox>{t("我分享的是个人经历，不作诊断、开药或要求他人改变治疗。")}</Checkbox></Form.Item><div className="form-actions"><Button onClick={() => setPostOpen(false)}>{t("取消")}</Button><Button type="primary" htmlType="submit" loading={saving}>{t("发布帖子")}</Button></div></Form></Modal>

    <Modal title={reportPost?.target_type === 'comment' ? t('举报评论') : reportPost?.target_type === 'message' ? t('举报私信') : t('举报帖子')} open={Boolean(reportPost)} onCancel={() => setReportPost(null)} footer={null} destroyOnHidden><Paragraph>{t('Choose a reason and add any useful context. You can follow the status in Reports & blocked members. Your identity is not shown to the reported member.')}</Paragraph><Form form={reportForm} layout="vertical" onFinish={submitReport}><Form.Item label={t("举报原因")} name="reason" rules={[{ required: true, message: t('请选择原因') }]}><Select options={[{ value: 'medical_advice', label: t('诊断或治疗建议') }, { value: 'unsafe_content', label: t('危险或有害内容') }, { value: 'harassment', label: t('骚扰') }, { value: 'privacy', label: t('个人隐私') }, { value: 'spam', label: t('垃圾广告') }, { value: 'other', label: t('其他问题') }]} /></Form.Item><Form.Item label={t("补充说明")} name="details"><Input.TextArea rows={4} maxLength={500} showCount /></Form.Item><div className="form-actions"><Button onClick={() => setReportPost(null)}>{t("取消")}</Button><Button type="primary" danger htmlType="submit" loading={saving}>{t("提交举报")}</Button></div></Form></Modal>
  </div>
}
