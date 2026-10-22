import { useEffect, useMemo, useState } from 'react'

const API = import.meta.env.VITE_API_URL || '/api'

async function getJson(path) {
  const response = await fetch(`${API}${path}`)
  if (!response.ok) throw new Error(`API trả về lỗi ${response.status}`)
  return response.json()
}

export default function App() {
  const [learners, setLearners] = useState([])
  const [concepts, setConcepts] = useState([])
  const [learnerId, setLearnerId] = useState('')
  const [targetId, setTargetId] = useState('')
  const [state, setState] = useState([])
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(true)
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState('')

  const conceptById = useMemo(() => new Map(concepts.map((item) => [item.id, item])), [concepts])

  useEffect(() => {
    let active = true
    Promise.all([getJson('/learners'), getJson('/concepts')])
      .then(([learnerRows, conceptRows]) => {
        if (!active) return
        setLearners(learnerRows)
        setConcepts(conceptRows)
        setLearnerId(learnerRows[0] || '')
        setTargetId(conceptRows[0]?.id || '')
      })
      .catch((reason) => active && setError(reason.message))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (!learnerId) { setState([]); return }
    let active = true
    getJson(`/learners/${encodeURIComponent(learnerId)}/state`)
      .then((rows) => active && setState(rows))
      .catch((reason) => active && setError(reason.message))
    return () => { active = false }
  }, [learnerId])

  const known = state.filter((item) => item.status === 'observed').length
  const unknown = state.length - known

  async function submit(event) {
    event.preventDefault()
    if (!learnerId || !targetId) return
    setSearching(true)
    setError('')
    setResult(null)
    try {
      const response = await fetch(`${API}/recommendations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          learnerId, targetId, asOf: new Date().toISOString(),
          tau: 0.5, minInteractions: 1,
          wP: 0, wN: 0.1, wD: 0.4, wR: 0.5,
        }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.message || `API trả về lỗi ${response.status}`)
      setResult(data)
    } catch (reason) {
      setError(reason.message)
    } finally {
      setSearching(false)
    }
  }

  return (
    <main className="shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="LearnPath trang chủ"><span className="brand-mark">L</span>LearnPath</a>
        <span className="top-note"><i /> Demo nghiên cứu · Computer Science</span>
      </header>

      <section className="intro">
        <p className="eyebrow">CÁ NHÂN HÓA LỘ TRÌNH</p>
        <h1>Học điều cần học,<br /><em>theo đúng thứ tự.</em></h1>
        <p className="lede">Chọn người học và một concept mục tiêu. LearnPath sắp xếp các prerequisite dựa trên lịch sử làm bài và giải thích từng lựa chọn.</p>
      </section>

      {error && <div className="alert" role="alert"><span>Không kết nối được dữ liệu.</span> {error}<small>Kiểm tra backend tại localhost:8080 và PostgreSQL đã nạp dữ liệu.</small></div>}

      {loading ? <div className="empty"><span className="spinner" />Đang tải dữ liệu…</div> : learners.length === 0 || concepts.length === 0 ? (
        <div className="empty-panel">
          <div className="empty-icon">↗</div>
          <h2>Chưa có dữ liệu để đề xuất</h2>
          <p>Nạp các bảng MOOCCubeX đã xử lý vào PostgreSQL, sau đó tải lại trang.</p>
          <code>python -m src.pipeline --domain cs</code>
        </div>
      ) : (
        <div className="workspace">
          <aside className="sidebar">
            <div className="section-heading"><span className="step-number">01</span><div><h2>Thiết lập mục tiêu</h2><p>Chọn hồ sơ và đích học tập</p></div></div>
            <form onSubmit={submit}>
              <label htmlFor="learner">Người học</label>
              <select id="learner" value={learnerId} onChange={(event) => { setLearnerId(event.target.value); setResult(null) }}>
                {learners.map((id) => <option value={id} key={id}>{id}</option>)}
              </select>
              <label htmlFor="target">Concept mục tiêu · tên gốc tiếng Trung</label>
              <select id="target" value={targetId} onChange={(event) => { setTargetId(event.target.value); setResult(null) }}>
                {concepts.map((concept) => <option value={concept.id} key={concept.id}>{concept.name} · {concept.id}</option>)}
              </select>
              <div className="config-note"><span>CẤU HÌNH ĐÃ CHỌN TRÊN VALIDATION</span><strong>τ = 0,50 <b>·</b> tối thiểu 1 lượt</strong><small>Trọng số P/N/D/R = 0 / 0,1 / 0,4 / 0,5. NDCG@5 validation = 0 (5 learner có nhãn); chưa có bằng chứng cấu hình này tốt hơn.</small></div>
              <button className="primary" type="submit" disabled={searching || !learnerId || !targetId}>
                {searching ? <><span className="spinner light" />Đang tìm lộ trình</> : <>Tạo lộ trình <span>↗</span></>}
              </button>
            </form>
            <p className="method-note">Greedy Best-First · Không bảo đảm tối ưu toàn cục</p>
          </aside>

          <section className="main-panel">
            <div className="section-heading state-heading"><span className="step-number">02</span><div><h2>Trạng thái kiến thức</h2><p>Ước lượng từ các lần làm trước thời điểm hiện tại</p></div></div>
            <div className="stat-row">
              <div className="stat"><strong>{known}</strong><span>Có lịch sử · learner này</span></div>
              <div className="stat"><strong>{unknown}</strong><span>Chưa quan sát</span></div>
              <div className="stat muted"><strong>{state.length}</strong><span>Tổng concept</span></div>
            </div>
            <div className="mastery-list" aria-label="Mức thành thạo concept">
              {state.length === 0 ? <p className="subtle">Chọn người học để xem trạng thái.</p> : state.slice(0, 100).map((item) => (
                <div className="mastery-row" key={item.conceptId}>
                  <div className="mastery-name"><span>{item.conceptName}</span><small>{item.status === 'unknown' ? 'Chưa có dữ liệu' : `${item.correct}/${item.total} câu đúng`}</small></div>
                  {item.mastery == null ? <span className="unknown-pill">Chưa biết</span> : <div className="bar-wrap"><div className="bar"><i style={{ width: `${Math.round(item.mastery * 100)}%` }} /></div><b>{Math.round(item.mastery * 100)}%</b></div>}
                </div>
              ))}
              {state.length > 100 && <p className="subtle">Đang hiển thị 100 / {state.length} concept.</p>}
            </div>
          </section>

          <section className="route-panel">
            <div className="section-heading"><span className="step-number">03</span><div><h2>Lộ trình đề xuất</h2><p>Thứ tự và lý do chọn concept</p></div></div>
            {!result ? <div className="route-placeholder"><div className="route-glyph">↳</div><p>Chọn mục tiêu để xem thứ tự học được đề xuất.</p></div> : <RouteResult result={result} conceptById={conceptById} />}
          </section>
        </div>
      )}
      <footer><span>LearnPath</span><span>Best-First Search + Heuristic</span><span>Dữ liệu học tập là ẩn danh</span></footer>
    </main>
  )
}

function RouteResult({ result, conceptById }) {
  const statuses = {
    reached: ['Đã tìm thấy lộ trình', 'success'],
    target_already_mastered: ['Mục tiêu đã thành thạo', 'success'],
    no_path: ['Chưa có lộ trình phù hợp', 'warning'],
    budget_exhausted: ['Đã hết ngân sách tìm kiếm', 'warning'],
  }
  const [label, tone] = statuses[result.status] || ['Không thể tạo lộ trình', 'warning']
  return <div className="route-result">
    <div className={`status-pill ${tone}`}><i />{label}</div>
    <p className="route-summary">{result.message}</p>
    {result.steps?.length > 0 && <>
      <div className="route-meta"><span>{result.steps.length} bước</span><span>{result.expanded} trạng thái đã mở rộng</span></div>
      <ol className="steps">
        {result.steps.map((step, index) => <li key={`${step.conceptId}-${index}`}>
          <span className="step-index">{String(index + 1).padStart(2, '0')}</span>
          <div className="step-content"><strong>{step.conceptName || conceptById.get(step.conceptId)?.name || step.conceptId}</strong><small>{step.conceptId}</small>
            <div className="score-grid">{[['P', step.scores.p], ['N', step.scores.n], ['D', step.scores.d], ['R', step.scores.r], ['H', step.scores.h]].map(([name, value]) => <span key={name}><b>{name}</b> {Number(value).toFixed(2)}</span>)}</div>
            <p>{step.scores.explanation}</p>
          </div>
        </li>)}
      </ol>
    </>}
  </div>
}
