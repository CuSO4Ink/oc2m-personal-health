import React from 'react'
import { CommentOutlined, DeleteOutlined, ExclamationCircleOutlined, FlagOutlined, HeartFilled, HeartOutlined, LockOutlined, PlusOutlined, SafetyCertificateOutlined, SearchOutlined, TeamOutlined, UserOutlined } from '@ant-design/icons'
import { Alert, Avatar, Button, Card, Checkbox, Empty, Form, Input, List, Modal, Popconfirm, Select, Skeleton, Space, Statistic, Tabs, Tag, Typography, message } from 'antd'
import dayjs from 'dayjs'
import api, { apiMessage } from './api'

const { Title, Paragraph, Text } = Typography
const formatDate = (value) => dayjs(value).format('D MMM YYYY · HH:mm')

export default function CommunityPage() {
  const [profile, setProfile] = React.useState(null)
  const [circles, setCircles] = React.useState([])
  const [posts, setPosts] = React.useState([])
  const [safety, setSafety] = React.useState(null)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState('')
  const [saving, setSaving] = React.useState(false)
  const [postOpen, setPostOpen] = React.useState(false)
  const [reportPost, setReportPost] = React.useState(null)
  const [commenting, setCommenting] = React.useState(null)
  const [search, setSearch] = React.useState('')
  const [circleFilter, setCircleFilter] = React.useState('all')
  const [postForm] = Form.useForm()
  const [reportForm] = Form.useForm()
  const [commentForm] = Form.useForm()

  const load = React.useCallback(async () => {
    setLoading(true); setError('')
    try {
      const response = await api.get('/community')
      setProfile(response.data.profile); setCircles(response.data.circles)
      setPosts(response.data.posts); setSafety(response.data.safety)
    } catch (requestError) { setError(apiMessage(requestError)) }
    finally { setLoading(false) }
  }, [])

  React.useEffect(() => {
    let active = true
    api.get('/community').then((response) => {
      if (!active) return
      setProfile(response.data.profile); setCircles(response.data.circles)
      setPosts(response.data.posts); setSafety(response.data.safety)
    }).catch((requestError) => { if (active) setError(apiMessage(requestError)) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  async function setCommunityEnabled(enabled) {
    setSaving(true)
    try {
      const response = await api.patch('/community/profile', { enabled })
      setProfile(response.data.profile)
      if (enabled) { message.success('Community is now available for this account.'); await load() }
      else { setPosts([]); message.success('Community is off. You will not see community activity.') }
    } catch (requestError) { message.error(apiMessage(requestError)) }
    finally { setSaving(false) }
  }

  async function changeMembership(circle, join) {
    try {
      if (join) await api.post(`/community/circles/${circle.id}/membership`)
      else await api.delete(`/community/circles/${circle.id}/membership`)
      message.success(join ? `Joined ${circle.name}.` : `Left ${circle.name}.`)
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
    try { await api.post('/community/posts', values); message.success('Your experience was posted.'); setPostOpen(false); await load() }
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
    commentForm.resetFields(); commentForm.setFieldsValue({ anonymous: true }); setCommenting(post.id)
  }

  async function addComment(values) {
    setSaving(true)
    try {
      const response = await api.post(`/community/posts/${commenting}/comments`, values)
      setPosts((current) => current.map((item) => item.id === commenting ? response.data.post : item))
      commentForm.resetFields(); commentForm.setFieldsValue({ anonymous: true }); message.success('Comment added.')
    } catch (requestError) { message.error(apiMessage(requestError)) }
    finally { setSaving(false) }
  }

  async function deletePost(postId) {
    try { await api.delete(`/community/posts/${postId}`); message.success('Post deleted.'); await load() }
    catch (requestError) { message.error(apiMessage(requestError)) }
  }

  function openReport(post) { reportForm.resetFields(); setReportPost(post) }

  async function submitReport(values) {
    setSaving(true)
    try { await api.post(`/community/posts/${reportPost.id}/reports`, values); message.success('Report submitted for review.'); setReportPost(null) }
    catch (requestError) { message.error(apiMessage(requestError)) }
    finally { setSaving(false) }
  }

  const joinedCircles = circles.filter((circle) => circle.joined)
  const filteredPosts = posts.filter((post) => (circleFilter === 'all' || post.circle.id === circleFilter) && post.body.toLowerCase().includes(search.toLowerCase()))

  const feedPanel = <div className="community-panel">
    <div className="section-heading"><div><Title level={3}>Experiences from your circles</Title><Paragraph>Posts are written by members and are not checked medical guidance.</Paragraph></div><Space wrap><Input allowClear prefix={<SearchOutlined />} placeholder="Search posts" value={search} onChange={(event) => setSearch(event.target.value)} /><Select value={circleFilter} onChange={setCircleFilter} options={[{ value: 'all', label: 'All joined circles' }, ...joinedCircles.map((circle) => ({ value: circle.id, label: circle.name }))]} /><Button type="primary" icon={<PlusOutlined />} disabled={!joinedCircles.length} onClick={openPostComposer}>Share Experience</Button></Space></div>
    {!joinedCircles.length ? <Card><Empty description="Join a circle before reading or sharing experiences" /></Card> : filteredPosts.length === 0 ? <Card><Empty description="No posts match these filters" /></Card> : <div className="community-feed">{filteredPosts.map((post) => <Card key={post.id} className="community-post"><div className="post-author"><Avatar icon={post.anonymous ? <LockOutlined /> : <UserOutlined />} /><div><Space wrap><Text strong>{post.author_name}</Text>{post.is_owner && <Tag color="green">Your post</Tag>}<Tag>{post.circle.name}</Tag></Space><Text type="secondary">{formatDate(post.created_at)}</Text></div></div><Paragraph className="post-body">{post.body}</Paragraph><Alert className="peer-content-note" type="warning" showIcon message="Peer experience, not medical advice" /><div className="post-actions"><Button type="text" icon={post.liked ? <HeartFilled className="liked" /> : <HeartOutlined />} onClick={() => toggleLike(post)}>{post.like_count} helpful</Button><Button type="text" icon={<CommentOutlined />} onClick={() => openComments(post)}>{post.comment_count} comments</Button>{post.is_owner ? <Popconfirm title="Delete this post?" description="This removes it from the community feed." okButtonProps={{ danger: true }} onConfirm={() => deletePost(post.id)}><Button type="text" danger icon={<DeleteOutlined />}>Delete</Button></Popconfirm> : <Button type="text" icon={<FlagOutlined />} onClick={() => openReport(post)}>Report</Button>}</div>{post.comments.length > 0 && <List className="comment-list" dataSource={post.comments} renderItem={(comment) => <List.Item><List.Item.Meta avatar={<Avatar size="small" icon={comment.anonymous ? <LockOutlined /> : <UserOutlined />} />} title={<Space><Text strong>{comment.author_name}</Text><Text type="secondary">{formatDate(comment.created_at)}</Text></Space>} description={comment.body} /></List.Item>} />}{commenting === post.id && <Form className="comment-form" form={commentForm} layout="vertical" onFinish={addComment}><Form.Item name="body" rules={[{ required: true, min: 2, max: 500, message: 'Write a comment between 2 and 500 characters' }]}><Input.TextArea rows={2} placeholder="Reply with support or personal experience" maxLength={500} showCount /></Form.Item><div className="comment-controls"><Form.Item name="anonymous" valuePropName="checked" noStyle><Checkbox>Comment anonymously</Checkbox></Form.Item><Space><Button onClick={() => setCommenting(null)}>Cancel</Button><Button type="primary" htmlType="submit" loading={saving}>Comment</Button></Space></div></Form>}</Card>)}</div>}
  </div>

  const circlesPanel = <div className="community-panel"><div className="section-heading"><div><Title level={3}>Find a peer circle</Title><Paragraph>Join only the topics you want. Leaving a circle removes its posts from your feed.</Paragraph></div></div><div className="circle-grid">{circles.map((circle) => <Card key={circle.id} className="circle-card"><Tag color="blue">{circle.topic}</Tag><Title level={4}>{circle.name}</Title><Paragraph>{circle.description}</Paragraph><div className="circle-meta"><span><TeamOutlined /> {circle.member_count} members</span><span><SafetyCertificateOutlined /> Moderated reporting</span></div><Text type="secondary">{circle.guidance}</Text>{circle.joined ? <Popconfirm title={`Leave ${circle.name}?`} description="Posts from this circle will no longer appear in your feed." onConfirm={() => changeMembership(circle, false)}><Button>Leave circle</Button></Popconfirm> : <Button type="primary" onClick={() => changeMembership(circle, true)}>Join circle</Button>}</Card>)}</div></div>

  const guidancePanel = <div className="community-panel"><Card title="Community guidelines"><div className="guideline-list"><div><SafetyCertificateOutlined /><div><Text strong>Share experience safely</Text><Paragraph>Describe what happened to you. Do not diagnose another member, prescribe treatment or tell someone to stop medication.</Paragraph></div></div><div><LockOutlined /><div><Text strong>Your health records stay separate</Text><Paragraph>Community has no access to your records, measurements, appointments or sharing permissions. Publish only text you enter yourself.</Paragraph></div></div><div><FlagOutlined /><div><Text strong>Report concerning content</Text><Paragraph>Report medical advice, harassment, privacy concerns, unsafe content or spam for moderator review.</Paragraph></div></div><div><ExclamationCircleOutlined /><div><Text strong>Use professional and urgent care</Text><Paragraph>Contact a qualified healthcare professional for diagnosis or treatment. Use local emergency services for urgent danger.</Paragraph></div></div></div></Card><Alert type="info" showIcon message="Private messages are planned" description="Direct messaging will be added only after privacy, blocking and safeguarding responsibilities are agreed." /></div>

  return <div className="page-stack community-page">
    <div className="page-heading"><div><Title level={1}>Community</Title><Paragraph>An optional peer-support space for sharing personal experiences.</Paragraph></div>{profile?.enabled && <Popconfirm title="Turn off Community?" description="Your memberships are preserved, but community content will stop appearing until you turn it on again." onConfirm={() => setCommunityEnabled(false)}><Button loading={saving}>Turn off Community</Button></Popconfirm>}</div>
    {error && <Alert type="error" showIcon message="Community could not be loaded" description={error} action={<Button onClick={load}>Try again</Button>} />}
    {loading ? <Card><Skeleton active paragraph={{ rows: 10 }} /></Card> : !profile?.enabled ? <Card className="community-onboarding"><div className="onboarding-icon"><TeamOutlined /></div><Title level={2}>Community is off</Title><Paragraph>Choose whether to join peer-support circles. Your health records are never added to posts, and you can turn Community off again at any time.</Paragraph><div className="privacy-points"><span><LockOutlined /> Separate from your health record</span><span><UserOutlined /> Anonymous posting available</span><span><FlagOutlined /> Reporting and moderation workflow</span></div><Button type="primary" size="large" loading={saving} onClick={() => setCommunityEnabled(true)}>Turn on Community</Button></Card> : <><Alert type="success" showIcon icon={<LockOutlined />} message="Health data remains separate" description={safety?.message} /><div className="community-summary"><Card><Statistic title="Circles joined" value={joinedCircles.length} prefix={<TeamOutlined />} /></Card><Card><Statistic title="Experiences in your feed" value={posts.length} prefix={<CommentOutlined />} /></Card><Card><Statistic title="Health records connected" value={0} suffix="records" prefix={<LockOutlined />} /></Card></div><Tabs defaultActiveKey="feed" items={[{ key: 'feed', label: 'My Feed', children: feedPanel }, { key: 'circles', label: 'Find Circles', children: circlesPanel }, { key: 'guidance', label: 'Safety & Guidelines', children: guidancePanel }]} /></>}

    <Modal title="Share your experience" open={postOpen} onCancel={() => setPostOpen(false)} footer={null} destroyOnHidden><Alert type="info" showIcon message="Write this post manually" description="No information is copied from your health record." /><Form className="community-form" form={postForm} layout="vertical" onFinish={createPost}><Form.Item label="Circle" name="circle_id" rules={[{ required: true, message: 'Select a circle' }]}><Select options={joinedCircles.map((circle) => ({ value: circle.id, label: circle.name }))} /></Form.Item><Form.Item label="Your experience" name="body" rules={[{ required: true, min: 3, max: 1200, message: 'Write between 3 and 1,200 characters' }]}><Input.TextArea rows={6} maxLength={1200} showCount placeholder="Share what you experienced, what helped you organise daily life, or a question you asked a professional." /></Form.Item><Form.Item name="anonymous" valuePropName="checked"><Checkbox>Post anonymously</Checkbox></Form.Item><Form.Item name="acknowledged" valuePropName="checked" rules={[{ validator: (_, value) => value ? Promise.resolve() : Promise.reject(new Error('Confirm the community guidance before posting')) }]}><Checkbox>I am sharing personal experience, not diagnosis, prescribing or instructions to change treatment.</Checkbox></Form.Item><div className="form-actions"><Button onClick={() => setPostOpen(false)}>Cancel</Button><Button type="primary" htmlType="submit" loading={saving}>Publish Post</Button></div></Form></Modal>

    <Modal title="Report community post" open={Boolean(reportPost)} onCancel={() => setReportPost(null)} footer={null} destroyOnHidden><Paragraph>Reports are sent for moderator review. The author is not told who submitted the report.</Paragraph><Form form={reportForm} layout="vertical" onFinish={submitReport}><Form.Item label="Reason" name="reason" rules={[{ required: true, message: 'Select a reason' }]}><Select options={[{ value: 'medical_advice', label: 'Diagnosis or medical advice' }, { value: 'unsafe_content', label: 'Unsafe or harmful content' }, { value: 'harassment', label: 'Harassment' }, { value: 'privacy', label: 'Personal or private information' }, { value: 'spam', label: 'Spam' }, { value: 'other', label: 'Other concern' }]} /></Form.Item><Form.Item label="Additional details" name="details"><Input.TextArea rows={4} maxLength={500} showCount /></Form.Item><div className="form-actions"><Button onClick={() => setReportPost(null)}>Cancel</Button><Button type="primary" danger htmlType="submit" loading={saving}>Submit Report</Button></div></Form></Modal>
  </div>
}
