import { useState, useEffect, useRef, useCallback } from "react";

// ── Config ────────────────────────────────────────────────────────────────────
const API = "http://localhost:8000";

// ── API helpers ───────────────────────────────────────────────────────────────
function useApi() {
  const token = localStorage.getItem("token");
  const headers = { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) };
  const get  = (url) => fetch(API+url, { headers }).then(r => r.json());
  const post = (url, body) => fetch(API+url, { method:"POST", headers, body:JSON.stringify(body) }).then(r => r.json());
  const put  = (url, body) => fetch(API+url, { method:"PUT",  headers, body:JSON.stringify(body) }).then(r => r.json());
  return { get, post, put };
}

// ── Mastery ring ──────────────────────────────────────────────────────────────
function MasteryRing({ pct, size=48, color="#6366f1" }) {
  const r = (size/2) - 5;
  const circ = 2*Math.PI*r;
  const filled = circ * (pct/100);
  return (
    <svg width={size} height={size}>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="#1e2035" strokeWidth="4"/>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color}
        strokeWidth="4" strokeDasharray={`${filled} ${circ}`}
        strokeLinecap="round"
        transform={`rotate(-90 ${size/2} ${size/2})`}
        style={{transition:"stroke-dasharray .5s ease"}}/>
      <text x={size/2} y={size/2+5} textAnchor="middle"
        fill="#e2e8ff" fontSize="11" fontFamily="'Fira Code',monospace" fontWeight="600">
        {pct}%
      </text>
    </svg>
  );
}

// ── Difficulty badge ──────────────────────────────────────────────────────────
function DiffBadge({ diff }) {
  const colors = { easy:"#34d399", medium:"#fbbf24", hard:"#f87171" };
  return (
    <span style={{
      display:"inline-block", padding:"2px 8px", borderRadius:6,
      fontSize:".68rem", fontWeight:600, letterSpacing:".06em",
      background:`${colors[diff]}18`, color:colors[diff],
      border:`1px solid ${colors[diff]}40`, textTransform:"uppercase",
    }}>{diff}</span>
  );
}

// ── Source badge ──────────────────────────────────────────────────────────────
function SourceBadge({ source, confidence }) {
  const map = { rag:["NCERT","#4ade80"], web:["Web","#fbbf24"], none:["No source","#f87171"] };
  const [label,color] = map[source] || map.none;
  return (
    <span style={{display:"inline-flex",alignItems:"center",gap:4,fontSize:".68rem",color,fontFamily:"'Fira Code',monospace"}}>
      <span style={{width:5,height:5,borderRadius:"50%",background:color,display:"inline-block"}}/>
      {label} {confidence ? `${Math.round(confidence*100)}%` : ""}
    </span>
  );
}

// ── Markdown-ish renderer ─────────────────────────────────────────────────────
function ResponseText({ text }) {
  // Convert **bold**, `code`, numbered lists to JSX
  const lines = text.split("\n");
  return (
    <div style={{lineHeight:1.75, fontSize:".88rem", color:"#c8d0f0"}}>
      {lines.map((line, i) => {
        if (!line.trim()) return <div key={i} style={{height:8}}/>;
        // Formula box
        if (line.startsWith("Formula:") || line.startsWith("KEY FORMULA")) {
          return <div key={i} style={{background:"#0d1326",border:"1px solid #3b82f6",borderRadius:8,
            padding:"8px 12px",margin:"8px 0",fontFamily:"'Fira Code',monospace",fontSize:".82rem",color:"#93c5fd"}}>{line}</div>;
        }
        // Numbered
        if (/^\d+\.\s/.test(line)) {
          return <div key={i} style={{display:"flex",gap:8,margin:"4px 0"}}>
            <span style={{color:"#6366f1",fontWeight:700,flexShrink:0}}>{line.match(/^\d+/)[0]}.</span>
            <span dangerouslySetInnerHTML={{__html: line.replace(/^\d+\.\s/,"").replace(/\*\*(.*?)\*\*/g,"<strong>$1</strong>").replace(/`(.*?)`/g,'<code style="background:#0d1326;padding:1px 5px;border-radius:4px;font-family:monospace;color:#a78bfa">$1</code>')}}/>
          </div>;
        }
        return <p key={i} style={{margin:"4px 0"}} dangerouslySetInnerHTML={{__html:
          line.replace(/\*\*(.*?)\*\*/g,"<strong style='color:#e2e8ff'>$1</strong>")
              .replace(/`(.*?)`/g,'<code style="background:#0d1326;padding:1px 5px;border-radius:4px;font-family:monospace;color:#a78bfa;font-size:.85em">$1</code>')
        }}/>;
      })}
    </div>
  );
}

// ── Auth screen ───────────────────────────────────────────────────────────────
function AuthScreen({ onLogin }) {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ email:"", password:"", name:"", grade:10 });
  const [err,  setErr]  = useState("");
  const [loading, setLoading] = useState(false);
  const api = useApi();

  const submit = async () => {
    setErr(""); setLoading(true);
    try {
      const endpoint = mode === "login" ? "/auth/login" : "/auth/register";
      const data = await api.post(endpoint, form);
      if (data.token) {
        localStorage.setItem("token", data.token);
        localStorage.setItem("user_id", data.user_id);
        onLogin(data.user_id);
      } else {
        setErr(data.detail || "Auth failed");
      }
    } catch { setErr("Network error"); }
    setLoading(false);
  };

  return (
    <div style={{minHeight:"100vh",display:"flex",alignItems:"center",justifyContent:"center",
      background:"#07080f",fontFamily:"'Space Grotesk',sans-serif"}}>
      <div style={{width:360,padding:36,background:"#0d0f1c",borderRadius:16,border:"1px solid #1a1f38"}}>
        <div style={{marginBottom:28}}>
          <div style={{fontFamily:"'Fira Code',monospace",fontSize:".65rem",letterSpacing:".15em",
            color:"#4a5280",textTransform:"uppercase",marginBottom:8}}>NCERT AI Tutor · v3</div>
          <h1 style={{color:"#e2e8ff",fontSize:"1.6rem",fontWeight:700,margin:0}}>
            {mode === "login" ? "Welcome back" : "Create account"}
          </h1>
        </div>

        {["email","password"].concat(mode==="register" ? ["name"] : []).map(f => (
          <div key={f} style={{marginBottom:12}}>
            <input
              type={f==="password"?"password":"text"}
              placeholder={f.charAt(0).toUpperCase()+f.slice(1)}
              value={form[f]} onChange={e=>setForm({...form,[f]:e.target.value})}
              onKeyDown={e=>e.key==="Enter"&&submit()}
              style={{width:"100%",background:"#111425",border:"1px solid #1a1f38",
                borderRadius:8,padding:"10px 14px",color:"#c8d0f0",fontSize:".85rem",boxSizing:"border-box",
                outline:"none",fontFamily:"inherit"}}
            />
          </div>
        ))}

        {mode === "register" && (
          <select value={form.grade} onChange={e=>setForm({...form,grade:+e.target.value})}
            style={{width:"100%",background:"#111425",border:"1px solid #1a1f38",
              borderRadius:8,padding:"10px 14px",color:"#c8d0f0",fontSize:".85rem",marginBottom:12,
              fontFamily:"inherit",boxSizing:"border-box"}}>
            {[6,7,8,9,10,11,12].map(g => <option key={g} value={g}>Class {g}</option>)}
          </select>
        )}

        {err && <div style={{color:"#f87171",fontSize:".78rem",marginBottom:8}}>{err}</div>}

        <button onClick={submit} disabled={loading}
          style={{width:"100%",padding:"12px",background:"#6366f1",color:"#fff",border:"none",
            borderRadius:8,fontWeight:600,fontSize:".9rem",cursor:"pointer",fontFamily:"inherit",marginTop:4}}>
          {loading ? "…" : mode==="login" ? "Sign in" : "Register"}
        </button>

        <div style={{textAlign:"center",marginTop:16,fontSize:".78rem",color:"#4a5280"}}>
          {mode==="login" ? "No account? " : "Have an account? "}
          <span onClick={()=>setMode(mode==="login"?"register":"login")}
            style={{color:"#6366f1",cursor:"pointer",textDecoration:"underline"}}>
            {mode==="login" ? "Register" : "Sign in"}
          </span>
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// Main App
// ══════════════════════════════════════════════════════════════════════════════
export default function App() {
  const [userId,   setUserId]   = useState(localStorage.getItem("user_id") || "");
  const [tab,      setTab]      = useState("chat");     // chat | mastery | quiz | settings
  const [messages, setMessages] = useState([]);
  const [input,    setInput]    = useState("");
  const [topic,    setTopic]    = useState("");
  const [subject,  setSubject]  = useState("Physics");
  const [loading,  setLoading]  = useState(false);
  const [sessionId]             = useState(() => crypto.randomUUID());
  const [mastery,  setMastery]  = useState({});
  const [profile,  setProfile]  = useState(null);
  const [quizData, setQuizData] = useState(null);
  const [quizTopic,setQuizTopic]= useState("");
  const [quizAns,  setQuizAns]  = useState(null);
  const [quizResult,setQuizResult]=useState(null);
  const [sidePanel,setSidePanel]= useState(true);
  const bottomRef = useRef(null);
  const api = useApi();

  useEffect(() => { if (userId) { fetchProfile(); fetchMastery(); } }, [userId]);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior:"smooth" }); }, [messages]);

  const fetchProfile = async () => {
    const d = await api.get("/profile"); setProfile(d);
  };
  const fetchMastery = async () => {
    const d = await api.get("/mastery"); setMastery(d.mastery || {});
  };

  const sendMessage = async () => {
    if (!input.trim() || loading) return;
    const q = input.trim();
    setInput("");
    setMessages(m => [...m, { role:"user", text:q }]);
    setLoading(true);
    const msgIndex = messages.length + 1;

    const startTs = Date.now();
    const data = await api.post("/chat", {
      query: q, topic: topic||q.split(" ").slice(0,3).join(" "),
      subject, session_id: sessionId,
    });
    const elapsed = Date.now() - startTs;

    setMessages(m => [...m, {
      role:"assistant", text: data.response || "Error — try again.",
      meta: { source:data.source, confidence:data.confidence,
              difficulty:data.difficulty, mastery_pct:data.mastery_pct,
              guardrails:data.guardrails, latency:elapsed,
              interaction_id:data.interaction_id, images:data.images||[] },
    }]);
    setLoading(false);
    fetchMastery();

    // Auto-submit feedback after 5s dwell (simulated)
    setTimeout(() => {
      if (data.interaction_id) {
        api.post("/chat/feedback", {
          interaction_id: data.interaction_id,
          dwell_s: 5, scroll_depth: 0.6,
        });
      }
    }, 5000);
  };

  const generateQuiz = async () => {
    if (!quizTopic) return;
    setQuizData(null); setQuizAns(null); setQuizResult(null);
    const d = await api.get(`/quiz/generate?topic=${encodeURIComponent(quizTopic)}&subject=${encodeURIComponent(subject)}`);
    setQuizData(d);
  };

  const submitQuizAnswer = async (opt) => {
    setQuizAns(opt);
    const correct = opt.startsWith(quizData.answer);
    const r = await api.post("/quiz/submit", {
      topic: quizData.topic, question: quizData.question,
      is_correct: correct, difficulty: quizData.difficulty,
    });
    setQuizResult({ correct, ...r });
    fetchMastery();
  };

  if (!userId) return <AuthScreen onLogin={id => { setUserId(id); }}/>;

  const SUBJECTS = ["Physics","Chemistry","Biology","Mathematics","Science","History","Geography"];
  const topMastery = Object.entries(mastery).sort((a,b)=>b[1].score-a[1].score).slice(0,8);
  const weakTopics = Object.entries(mastery).sort((a,b)=>a[1].score-b[1].score).slice(0,5);

  return (
    <div style={{display:"flex",height:"100vh",overflow:"hidden",
      background:"#07080f",fontFamily:"'Space Grotesk',sans-serif",color:"#c8d0f0"}}>

      {/* ── Sidebar ──────────────────────────────────────────────────────── */}
      <div style={{width:220,flexShrink:0,background:"#0d0f1c",borderRight:"1px solid #1a1f38",
        display:"flex",flexDirection:"column",padding:"24px 0"}}>
        <div style={{padding:"0 20px 20px",borderBottom:"1px solid #1a1f38",marginBottom:8}}>
          <div style={{fontFamily:"'Fira Code',monospace",fontSize:".6rem",letterSpacing:".15em",
            color:"#4a5280",textTransform:"uppercase",marginBottom:6}}>NCERT Tutor</div>
          <div style={{fontSize:".85rem",fontWeight:600,color:"#e2e8ff",marginBottom:2}}>
            {profile?.name || "Student"}
          </div>
          <div style={{fontSize:".72rem",color:"#4a5280"}}>Class {profile?.grade} · {profile?.board}</div>
        </div>

        {[
          ["chat","💬","Chat"],
          ["mastery","📊","Mastery"],
          ["quiz","✏️","Quiz"],
          ["settings","⚙️","Settings"],
        ].map(([id,icon,label]) => (
          <button key={id} onClick={()=>setTab(id)}
            style={{display:"flex",alignItems:"center",gap:10,padding:"11px 20px",
              background:tab===id?"rgba(99,102,241,.12)":"transparent",
              borderLeft:`3px solid ${tab===id?"#6366f1":"transparent"}`,
              border:"none",cursor:"pointer",color:tab===id?"#a5b4fc":"#6677aa",
              fontSize:".83rem",fontWeight:tab===id?600:400,textAlign:"left",fontFamily:"inherit"}}>
            <span>{icon}</span>{label}
          </button>
        ))}

        {/* Weak topics mini list */}
        {weakTopics.length > 0 && (
          <div style={{marginTop:"auto",padding:"16px 20px",borderTop:"1px solid #1a1f38"}}>
            <div style={{fontFamily:"'Fira Code',monospace",fontSize:".6rem",
              letterSpacing:".1em",color:"#4a5280",textTransform:"uppercase",marginBottom:10}}>
              Needs work
            </div>
            {weakTopics.map(([topic,data]) => (
              <div key={topic} style={{display:"flex",justifyContent:"space-between",
                alignItems:"center",marginBottom:6}}>
                <span style={{fontSize:".72rem",color:"#6677aa",overflow:"hidden",
                  textOverflow:"ellipsis",whiteSpace:"nowrap",maxWidth:130}}>{topic}</span>
                <span style={{fontSize:".68rem",fontFamily:"'Fira Code',monospace",color:"#f87171",flexShrink:0}}>
                  {data.pct}%
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Main content ─────────────────────────────────────────────────── */}
      <div style={{flex:1,display:"flex",flexDirection:"column",overflow:"hidden"}}>

        {/* ── Header bar ─────────────────────────────────────────────────── */}
        <div style={{padding:"14px 24px",borderBottom:"1px solid #1a1f38",
          display:"flex",alignItems:"center",gap:12,flexShrink:0}}>
          <select value={subject} onChange={e=>setSubject(e.target.value)}
            style={{background:"#111425",border:"1px solid #1a1f38",borderRadius:6,
              padding:"6px 10px",color:"#c8d0f0",fontSize:".8rem",fontFamily:"inherit",cursor:"pointer"}}>
            {SUBJECTS.map(s=><option key={s}>{s}</option>)}
          </select>
          <input placeholder="Topic (optional)" value={topic} onChange={e=>setTopic(e.target.value)}
            style={{flex:1,background:"#111425",border:"1px solid #1a1f38",borderRadius:6,
              padding:"6px 12px",color:"#c8d0f0",fontSize:".8rem",fontFamily:"inherit",outline:"none"}}/>
          <button onClick={()=>setSidePanel(p=>!p)}
            style={{padding:"6px 12px",background:"transparent",border:"1px solid #1a1f38",
              borderRadius:6,color:"#4a5280",cursor:"pointer",fontSize:".75rem",fontFamily:"inherit"}}>
            {sidePanel?"Hide panel":"Show panel"}
          </button>
        </div>

        <div style={{flex:1,display:"flex",overflow:"hidden"}}>

          {/* ── Chat / Mastery / Quiz / Settings ─────────────────────────── */}
          <div style={{flex:1,overflow:"auto",padding:24}}>

            {/* CHAT TAB */}
            {tab==="chat" && (
              <div style={{maxWidth:720,margin:"0 auto"}}>
                {messages.length===0 && (
                  <div style={{textAlign:"center",paddingTop:60,color:"#2a3050"}}>
                    <div style={{fontSize:"2.5rem",marginBottom:12}}>📚</div>
                    <div style={{fontSize:"1rem",fontWeight:600,color:"#3a4070",marginBottom:6}}>
                      Ask any NCERT question
                    </div>
                    <div style={{fontSize:".82rem"}}>Personalized to Class {profile?.grade} · {subject}</div>
                    <div style={{display:"flex",flexWrap:"wrap",gap:8,justifyContent:"center",marginTop:20}}>
                      {["What is Ohm's Law?","Explain refraction with diagram","How does photosynthesis work?","Derive v² = u² + 2as"].map(q=>(
                        <button key={q} onClick={()=>{setInput(q);}}
                          style={{padding:"6px 14px",background:"#111425",border:"1px solid #1a1f38",
                            borderRadius:20,color:"#6677aa",fontSize:".75rem",cursor:"pointer",fontFamily:"inherit"}}>
                          {q}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {messages.map((m,i) => (
                  <div key={i} style={{marginBottom:20,display:"flex",
                    flexDirection:m.role==="user"?"row-reverse":"row",gap:12}}>
                    <div style={{width:32,height:32,borderRadius:10,flexShrink:0,
                      background:m.role==="user"?"#6366f1":"#1a1f38",
                      display:"flex",alignItems:"center",justifyContent:"center",fontSize:".85rem"}}>
                      {m.role==="user"?"🧑":"🤖"}
                    </div>
                    <div style={{flex:1,maxWidth:"85%"}}>
                      <div style={{background:m.role==="user"?"#111a3a":"#0d1020",
                        borderRadius:12,padding:"14px 16px",
                        border:`1px solid ${m.role==="user"?"#2a3068":"#1a1f38"}`}}>
                        {m.role==="user"
                          ? <div style={{fontSize:".88rem",color:"#c8d0f0"}}>{m.text}</div>
                          : <ResponseText text={m.text}/>
                        }

                        {/* Image references */}
                        {m.meta?.images?.length>0 && (
                          <div style={{marginTop:10,display:"flex",gap:8,flexWrap:"wrap"}}>
                            {m.meta.images.map((img,j) => (
                              <div key={j} style={{background:"#07080f",border:"1px solid #1a1f38",
                                borderRadius:8,padding:"6px 10px",fontSize:".72rem",color:"#6677aa",
                                display:"flex",alignItems:"center",gap:6}}>
                                🖼 {img.image_type} · p.{img.page}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>

                      {/* Meta row */}
                      {m.meta && (
                        <div style={{display:"flex",gap:10,alignItems:"center",marginTop:5,paddingLeft:4}}>
                          <SourceBadge source={m.meta.source} confidence={m.meta.confidence}/>
                          <DiffBadge diff={m.meta.difficulty}/>
                          <MasteryRing pct={m.meta.mastery_pct} size={32}/>
                          {m.meta.guardrails?.length>0 && (
                            <span style={{fontSize:".65rem",color:"#f87171",fontFamily:"'Fira Code',monospace"}}>
                              🛡 {m.meta.guardrails.join(",")}
                            </span>
                          )}
                          <span style={{fontSize:".65rem",color:"#2a3050",marginLeft:"auto",fontFamily:"'Fira Code',monospace"}}>
                            {m.meta.latency}ms
                          </span>
                        </div>
                      )}

                      {/* Rating */}
                      {m.role==="assistant" && m.meta?.interaction_id && !m.rated && (
                        <div style={{display:"flex",gap:4,paddingLeft:4,marginTop:4}}>
                          {[1,2,3,4,5].map(r=>(
                            <button key={r} onClick={()=>{
                              api.post("/chat/feedback",{
                                interaction_id:m.meta.interaction_id,
                                dwell_s:30, scroll_depth:0.7, rating:r
                              });
                              setMessages(msgs => msgs.map((msg,idx)=>idx===i?{...msg,rated:true,_rating:r}:msg));
                            }}
                              style={{background:"transparent",border:"none",cursor:"pointer",
                                fontSize:".9rem",opacity:m._rating===r?1:0.3,padding:"2px"}}>
                              ★
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                ))}

                {loading && (
                  <div style={{display:"flex",gap:12,marginBottom:20}}>
                    <div style={{width:32,height:32,borderRadius:10,background:"#1a1f38",
                      display:"flex",alignItems:"center",justifyContent:"center"}}>🤖</div>
                    <div style={{background:"#0d1020",borderRadius:12,padding:"14px 16px",border:"1px solid #1a1f38"}}>
                      <div style={{display:"flex",gap:4}}>
                        {[0,1,2].map(i=>(
                          <div key={i} style={{width:6,height:6,borderRadius:"50%",background:"#6366f1",
                            animation:`bounce 1s ease-in-out ${i*0.15}s infinite`}}/>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
                <div ref={bottomRef}/>
              </div>
            )}

            {/* MASTERY TAB */}
            {tab==="mastery" && (
              <div style={{maxWidth:700,margin:"0 auto"}}>
                <h2 style={{color:"#e2e8ff",fontWeight:700,marginBottom:6}}>Knowledge Map</h2>
                <p style={{color:"#4a5280",fontSize:".83rem",marginBottom:24}}>
                  Mastery scores from quiz answers, decayed by Ebbinghaus forgetting curve.
                </p>
                {topMastery.length===0
                  ? <div style={{color:"#4a5280",textAlign:"center",paddingTop:40}}>
                      No mastery data yet — ask questions or take quizzes to build your map.
                    </div>
                  : (
                  <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(300px,1fr))",gap:12}}>
                    {Object.entries(mastery).sort((a,b)=>b[1].score-a[1].score).map(([topic,data])=>(
                      <div key={topic} style={{background:"#0d0f1c",border:"1px solid #1a1f38",borderRadius:12,padding:16}}>
                        <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:10}}>
                          <span style={{fontSize:".83rem",fontWeight:500,color:"#c8d0f0",lineHeight:1.4}}>{topic}</span>
                          <MasteryRing pct={data.pct} size={44}
                            color={data.pct>74?"#34d399":data.pct>39?"#fbbf24":"#f87171"}/>
                        </div>
                        <div style={{background:"#07080f",borderRadius:6,height:4,overflow:"hidden"}}>
                          <div style={{
                            height:"100%",borderRadius:6,transition:"width .5s ease",
                            width:`${data.pct}%`,
                            background:data.pct>74?"#34d399":data.pct>39?"#fbbf24":"#f87171",
                          }}/>
                        </div>
                        <div style={{marginTop:6,display:"flex",justifyContent:"flex-end"}}>
                          <DiffBadge diff={data.zone}/>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* QUIZ TAB */}
            {tab==="quiz" && (
              <div style={{maxWidth:560,margin:"0 auto"}}>
                <h2 style={{color:"#e2e8ff",fontWeight:700,marginBottom:6}}>Quiz</h2>
                <p style={{color:"#4a5280",fontSize:".83rem",marginBottom:20}}>
                  Answer a question → BKT mastery updates instantly.
                </p>

                <div style={{display:"flex",gap:8,marginBottom:20}}>
                  <input placeholder="Enter topic (e.g. Refraction)" value={quizTopic}
                    onChange={e=>setQuizTopic(e.target.value)}
                    onKeyDown={e=>e.key==="Enter"&&generateQuiz()}
                    style={{flex:1,background:"#111425",border:"1px solid #1a1f38",
                      borderRadius:8,padding:"10px 14px",color:"#c8d0f0",fontSize:".85rem",
                      fontFamily:"inherit",outline:"none"}}/>
                  <button onClick={generateQuiz}
                    style={{padding:"10px 20px",background:"#6366f1",border:"none",borderRadius:8,
                      color:"#fff",fontWeight:600,cursor:"pointer",fontFamily:"inherit",fontSize:".85rem"}}>
                    Generate
                  </button>
                </div>

                {quizData && (
                  <div style={{background:"#0d0f1c",border:"1px solid #1a1f38",borderRadius:14,padding:20}}>
                    <div style={{display:"flex",gap:8,marginBottom:14,alignItems:"center"}}>
                      <DiffBadge diff={quizData.difficulty}/>
                      <span style={{fontFamily:"'Fira Code',monospace",fontSize:".68rem",color:"#4a5280"}}>
                        {quizData.topic} · mastery {quizData.mastery_pct}%
                      </span>
                    </div>

                    <p style={{color:"#e2e8ff",fontWeight:500,marginBottom:16,lineHeight:1.6}}>{quizData.question}</p>

                    <div style={{display:"flex",flexDirection:"column",gap:8}}>
                      {quizData.options.map(opt=>{
                        const isCorrect = quizResult && opt.startsWith(quizData.answer);
                        const isWrong   = quizResult && quizAns===opt && !isCorrect;
                        return (
                          <button key={opt} onClick={()=>!quizAns&&submitQuizAnswer(opt)}
                            disabled={!!quizAns}
                            style={{
                              padding:"11px 16px",borderRadius:8,textAlign:"left",
                              fontFamily:"inherit",fontSize:".83rem",cursor:quizAns?"default":"pointer",
                              border:`1px solid ${isCorrect?"#34d399":isWrong?"#f87171":"#1a1f38"}`,
                              background:isCorrect?"rgba(52,211,153,.08)":isWrong?"rgba(248,113,113,.08)":"#111425",
                              color:isCorrect?"#34d399":isWrong?"#f87171":"#c8d0f0",
                              transition:"all .2s",
                            }}>
                            {opt}
                          </button>
                        );
                      })}
                    </div>

                    {quizResult && (
                      <div style={{marginTop:16,padding:14,background:"#07080f",borderRadius:10,
                        border:`1px solid ${quizResult.correct?"#34d39940":"#f8717140"}`}}>
                        <div style={{fontWeight:600,marginBottom:6,
                          color:quizResult.correct?"#34d399":"#f87171"}}>
                          {quizResult.correct?"✓ Correct!":"✗ Incorrect"}
                        </div>
                        <div style={{fontSize:".8rem",color:"#8899cc",marginBottom:8,lineHeight:1.6}}>
                          {quizData.explanation}
                        </div>
                        <div style={{display:"flex",gap:12,fontSize:".75rem",
                          fontFamily:"'Fira Code',monospace",color:"#4a5280"}}>
                          <span>before: {Math.round((quizResult.mastery_before||0)*100)}%</span>
                          <span style={{color:"#6366f1"}}>→</span>
                          <span style={{color:quizResult.correct?"#34d399":"#f87171"}}>
                            after: {Math.round((quizResult.mastery_after||0)*100)}%
                          </span>
                        </div>
                        <button onClick={generateQuiz} style={{marginTop:10,padding:"7px 14px",
                          background:"transparent",border:"1px solid #1a1f38",borderRadius:6,
                          color:"#6677aa",cursor:"pointer",fontSize:".78rem",fontFamily:"inherit"}}>
                          Next question →
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* SETTINGS TAB */}
            {tab==="settings" && profile && (
              <div style={{maxWidth:480,margin:"0 auto"}}>
                <h2 style={{color:"#e2e8ff",fontWeight:700,marginBottom:6}}>Settings</h2>
                <p style={{color:"#4a5280",fontSize:".83rem",marginBottom:24}}>
                  Changes here update your personalization profile immediately.
                </p>

                <div style={{display:"flex",flexDirection:"column",gap:16}}>
                  {[
                    {label:"Grade", key:"grade", type:"select", opts:[6,7,8,9,10,11,12].map(g=>({v:g,l:`Class ${g}`}))},
                    {label:"Board", key:"board",  type:"select", opts:["CBSE","ICSE","State Board"].map(b=>({v:b,l:b}))},
                    {label:"Language", key:"preferred_language", type:"select",
                      opts:[{v:"en",l:"English"},{v:"hi",l:"Hindi"},{v:"ta",l:"Tamil"},
                            {v:"te",l:"Telugu"},{v:"mr",l:"Marathi"},{v:"bn",l:"Bengali"}]},
                  ].map(({label,key,type,opts})=>(
                    <div key={key}>
                      <label style={{display:"block",fontSize:".75rem",color:"#4a5280",
                        textTransform:"uppercase",letterSpacing:".08em",marginBottom:6,
                        fontFamily:"'Fira Code',monospace"}}>{label}</label>
                      <select value={profile[key]||""}
                        onChange={async e=>{
                          const val = key==="grade"?+e.target.value:e.target.value;
                          const update = {[key]:val};
                          await api.put("/profile",update);
                          setProfile(p=>({...p,...update}));
                        }}
                        style={{width:"100%",background:"#111425",border:"1px solid #1a1f38",
                          borderRadius:8,padding:"10px 14px",color:"#c8d0f0",fontSize:".85rem",
                          fontFamily:"inherit",boxSizing:"border-box"}}>
                        {opts.map(o=><option key={o.v} value={o.v}>{o.l}</option>)}
                      </select>
                    </div>
                  ))}

                  <div>
                    <label style={{display:"block",fontSize:".75rem",color:"#4a5280",
                      textTransform:"uppercase",letterSpacing:".08em",marginBottom:6,
                      fontFamily:"'Fira Code',monospace"}}>Target Exams</label>
                    <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
                      {["JEE","NEET","UPSC","NDA","SAT"].map(exam=>{
                        const sel = (profile.target_exams||[]).includes(exam);
                        return (
                          <button key={exam} onClick={async()=>{
                            const current = profile.target_exams||[];
                            const next = sel ? current.filter(e=>e!==exam) : [...current,exam];
                            await api.put("/profile",{target_exams:next});
                            setProfile(p=>({...p,target_exams:next}));
                          }}
                            style={{padding:"6px 14px",borderRadius:20,fontSize:".78rem",
                              border:`1px solid ${sel?"#6366f1":"#1a1f38"}`,
                              background:sel?"rgba(99,102,241,.15)":"transparent",
                              color:sel?"#a5b4fc":"#6677aa",cursor:"pointer",fontFamily:"inherit"}}>
                            {exam}
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <button onClick={()=>{localStorage.clear();setUserId("");}}
                    style={{marginTop:16,padding:"10px",background:"transparent",
                      border:"1px solid #2d1a1a",borderRadius:8,color:"#f87171",
                      cursor:"pointer",fontFamily:"inherit",fontSize:".83rem"}}>
                    Sign out
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* ── Right panel — personalization info ─────────────────────────── */}
          {sidePanel && tab==="chat" && (
            <div style={{width:240,flexShrink:0,borderLeft:"1px solid #1a1f38",
              background:"#0d0f1c",overflow:"auto",padding:20}}>
              <div style={{fontFamily:"'Fira Code',monospace",fontSize:".6rem",
                letterSpacing:".12em",textTransform:"uppercase",color:"#4a5280",marginBottom:14}}>
                Personalization
              </div>

              {profile && (
                <>
                  <div style={{marginBottom:16}}>
                    <div style={{fontSize:".68rem",color:"#4a5280",marginBottom:6,
                      fontFamily:"'Fira Code',monospace",textTransform:"uppercase",letterSpacing:".08em"}}>
                      Style Vector
                    </div>
                    {["visual","analogy","example","step_by_step","formula","depth","memory_tip"]
                      .map((d,i) => (
                      <div key={d} style={{marginBottom:5}}>
                        <div style={{display:"flex",justifyContent:"space-between",marginBottom:2}}>
                          <span style={{fontSize:".68rem",color:"#6677aa"}}>{d}</span>
                          <span style={{fontSize:".65rem",fontFamily:"'Fira Code',monospace",color:"#4a5280"}}>
                            {((profile.style_vector||[])[i]||.5).toFixed(2)}
                          </span>
                        </div>
                        <div style={{background:"#07080f",borderRadius:3,height:3}}>
                          <div style={{
                            height:"100%",borderRadius:3,background:"#6366f1",
                            width:`${((profile.style_vector||[])[i]||.5)*100}%`,
                            transition:"width .4s ease",
                          }}/>
                        </div>
                      </div>
                    ))}
                  </div>

                  {topMastery.slice(0,5).length>0 && (
                    <div>
                      <div style={{fontSize:".68rem",color:"#4a5280",marginBottom:8,
                        fontFamily:"'Fira Code',monospace",textTransform:"uppercase",letterSpacing:".08em"}}>
                        Top Mastery
                      </div>
                      {topMastery.slice(0,5).map(([t,d])=>(
                        <div key={t} style={{display:"flex",justifyContent:"space-between",
                          alignItems:"center",marginBottom:5}}>
                          <span style={{fontSize:".7rem",color:"#6677aa",maxWidth:150,
                            overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{t}</span>
                          <span style={{fontSize:".68rem",fontFamily:"'Fira Code',monospace",
                            color:d.pct>74?"#34d399":d.pct>39?"#fbbf24":"#f87171",flexShrink:0}}>
                            {d.pct}%
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </div>

        {/* ── Chat input ────────────────────────────────────────────────────── */}
        {tab==="chat" && (
          <div style={{padding:"16px 24px",borderTop:"1px solid #1a1f38",flexShrink:0,
            display:"flex",gap:10,background:"#0d0f1c"}}>
            <textarea
              value={input}
              onChange={e=>setInput(e.target.value)}
              onKeyDown={e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();sendMessage();}}}
              placeholder={`Ask a ${subject} question… (Enter to send)`}
              rows={2}
              style={{flex:1,background:"#111425",border:"1px solid #1a1f38",borderRadius:10,
                padding:"11px 14px",color:"#c8d0f0",fontSize:".88rem",
                fontFamily:"inherit",resize:"none",outline:"none",lineHeight:1.5}}
            />
            <button onClick={sendMessage} disabled={loading||!input.trim()}
              style={{padding:"0 20px",background:loading||!input.trim()?"#1a1f38":"#6366f1",
                border:"none",borderRadius:10,color:"#fff",fontWeight:600,cursor:"pointer",
                fontFamily:"inherit",fontSize:".9rem",flexShrink:0,
                transition:"background .2s"}}>
              {loading ? "…" : "→"}
            </button>
          </div>
        )}
      </div>

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Fira+Code:wght@400;500&display=swap');
        *{box-sizing:border-box;margin:0;padding:0;}
        body{background:#07080f;}
        ::-webkit-scrollbar{width:4px;height:4px}
        ::-webkit-scrollbar-track{background:transparent}
        ::-webkit-scrollbar-thumb{background:#1a1f38;border-radius:2px}
        @keyframes bounce{0%,100%{transform:translateY(0)}50%{transform:translateY(-4px)}}
        select option{background:#0d0f1c;color:#c8d0f0;}
      `}</style>
    </div>
  );
}
