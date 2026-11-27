import React, { useState, useEffect, useRef } from "react";
import "./folio.css";

// Reference screens use fictional records. Keep production API calls in feature modules.
const paper = [
  { prompt: "Which factor is the light level measured in this study?", options: ["An abiotic factor", "A population count", "A trophic level"] },
  { prompt: "What should stay constant between quadrats?", options: ["Quadrat area", "Number of species found", "Distance to the river"] },
  { prompt: "Which method best measures the change in plant cover along this transect?", figure: true, options: ["Place quadrats at regular intervals along the line.", "Count only the tallest plant in each habitat.", "Collect a single sample at the tree line."] },
  { prompt: "Which measurements describe species diversity?", multi: true, options: ["Species richness", "Relative abundance", "Air temperature alone"] },
  { prompt: "Why would you repeat the survey on a second transect?", written: true },
  { prompt: "Which observation belongs in a field notebook?", options: ["Measured soil moisture", "An assumed population total", "An unverified trend"] },
  { prompt: "Which records make the survey reproducible?", multi: true, options: ["Quadrat size", "Sampling coordinates", "The observer’s favorite species"] },
  { prompt: "Describe one source of sampling bias in this survey.", written: true }
];
const seed = { answers: { 0: [0], 1: [0], 2: [0] }, flags: [4], scratch: "", size: 100, focus: false, closed: false, current: 2 };
const cacheKey = "folio-design-preview.v1";
function readSample() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(cacheKey));
    if (saved && Array.isArray(saved.flags) && saved.answers && Number.isInteger(saved.current) && paper[saved.current]) return {...seed, ...saved};
  } catch { /* A browser may disable storage for local files. */ }
  return seed;
}
function hasAnswer(answer) { return Array.isArray(answer) ? answer.length > 0 : Boolean(answer && answer.trim()); }
function two(n) { return String(n).padStart(2, "0"); }

export function SaveStatus({ state = "saved", children }) {
  return <span className="status" role="status" data-state={state}><i aria-hidden="true"/>{children}</span>;
}
export function Header({ role, setRole }) {
  return <header className="appbar"><div className="bar-inner">
    <div className="brand"><span className="brand-mark" aria-hidden="true"><i/><i/><i/></span><b>Folio</b><small>Examination office</small></div>
    <label className="bar-controls"><span className="role-label">Preview role</span><select aria-label="Preview role" value={role} onChange={e => setRole(e.target.value)}>
      <option>Candidate</option><option>Examiner</option><option>Administrator</option>
    </select></label>
  </div></header>;
}
export function PageHead({ crumb, title, details, aside }) {
  return <><div className="breadcrumbs" aria-label="Location">Folio <span aria-hidden="true">/</span> {crumb}</div>
    <div className="pagehead"><div><h1>{title}</h1><div className="meta">{details}</div></div>{aside}</div></>;
}
export function AnswerSheet({ answers, flags, current, jump, review, closed }) {
  const done = paper.filter((_, i) => hasAnswer(answers[i])).length;
  return <section className="side" aria-label="Answer sheet"><div className="side-head"><h2>Answer sheet</h2>
    <div className="progress-top"><span>Answered</span><span className="progress-count">{two(done)} / {two(paper.length)}</span></div>
    <div className="track" aria-hidden="true"><span style={{width: (100 * done / paper.length) + "%"}}/></div></div>
    <div className="side-content"><div className="numbers">{paper.map((q,i) => {
      const answered=hasAnswer(answers[i]), marked=flags.includes(i);
      return <button key={i} aria-current={current===i?"step":undefined} aria-label={`Question ${i+1}, ${answered?"answered":"unanswered"}${marked?", flagged":""}`}
        className={["number", answered?"answered":"", marked?"flagged":"", i===current?"current":""].join(" ")} onClick={() => jump(i)}>{two(i+1)}{answered && <span aria-hidden="true" className="done-mark">✓</span>}</button>;
    })}</div>
    <div className="legend"><span><i className="key done"/>Answered ✓</span><span><i className="key open"/>Open</span><span><i className="shape-flag"/>Flagged</span></div>
    <button className="secondary block" onClick={review}>{closed ? "View submission" : "Review submission"}</button></div>
  </section>;
}
function Review({ data, close, submit }) {
  const panel=useRef(null);
  useEffect(() => {
    const previous=document.activeElement;
    panel.current.querySelector("button").focus();
    function trap(e) {
      if(e.key==="Escape"){e.preventDefault();close();return;}
      if(e.key!=="Tab")return;
      const buttons=Array.from(panel.current.querySelectorAll("button:not(:disabled)"));
      const first=buttons[0],last=buttons[buttons.length-1];
      if(e.shiftKey && document.activeElement===first){e.preventDefault();last.focus();}
      if(!e.shiftKey && document.activeElement===last){e.preventDefault();first.focus();}
    }
    document.addEventListener("keydown",trap);
    return () => {document.removeEventListener("keydown",trap);if(previous && previous.isConnected)previous.focus();};
  }, []);
  const done=paper.filter((_,i)=>hasAnswer(data.answers[i])).length;
  return <div className="dialog-scrim"><section ref={panel} className="dialog" role="dialog" aria-modal="true" aria-labelledby="review-title">
    <h2 id="review-title">{data.closed?"Submission recorded":"Review submission"}</h2>
    <p>{done} of {paper.length} answered · {data.flags.length} flagged for review.</p>
    <ol className="review-list">{paper.map((_,i)=><li key={i} className="split"><span>Question {two(i+1)}</span><span>{hasAnswer(data.answers[i])?"Answered":"Unanswered"}{data.flags.includes(i)?" · Flagged":""}</span></li>)}</ol>
    <div className="actions"><button className="secondary" onClick={close}>{data.closed?"Close":"Return to exam"}</button>
    {!data.closed && <button className="primary" onClick={submit}>Submit sample attempt</button>}</div>
  </section></div>;
}
export function CandidateWorkspace({ figureUrl }) {
  const [data,setData]=useState(readSample),[review,setReview]=useState(false),[stored,setStored]=useState(true);
  const patch=fields=>setData(prev=>({...prev,...fields}));
  useEffect(()=>{try{sessionStorage.setItem(cacheKey,JSON.stringify(data));setStored(true);}catch{setStored(false);}},[data]);
  const i=data.current,q=paper[i],answer=data.answers[i] || (q.written?"":[]),marked=data.flags.includes(i);
  function save(value){setData(prev=>prev.closed?prev:{...prev,answers:{...prev.answers,[i]:value}});}
  function choose(n){save(q.multi?(answer.includes(n)?answer.filter(v=>v!==n):[...answer,n]):[n]);}
  return <main className={data.focus?"shell focus":"shell"} style={{"--reading":(data.size / 100)+"rem"}}>
    <PageHead crumb="Candidate workspace" title="Field ecology" details={<><b>BIO 204</b><i/>Practical examination<i/>8 questions</>}
      aside={<div className="clock"><span className="clock-label">Time remaining · demo</span><strong>24:08</strong></div>}/>
    <div className="workgrid"><article className="sheet">
      <div className="folio-line"><span className="qno">Question {two(i+1)} / {two(paper.length)}</span>
        <button disabled={data.closed} className={"flag "+(marked?"on":"")} aria-pressed={marked} onClick={()=>patch({flags:marked?data.flags.filter(n=>n!==i):[...data.flags,i]})}><i className="shape-flag"/>{marked?"Flagged":"Flag for review"}</button></div>
      <h2 className="question" id="question-title">{q.prompt}</h2>
      {q.figure && <figure className="figure"><img src={figureUrl} alt="A 60-metre transect crosses the riverbank at 0 m, meadow at 30 m and tree line at 60 m."/><figcaption><span className="fig-id">Fig. 01</span>Vegetation survey along a 60 m transect</figcaption></figure>}
      <fieldset disabled={data.closed} aria-labelledby="question-title"><legend className="field-instruction">{q.written?"Written response":q.multi?"Select all that apply":"Select one answer"} · {q.written?4:2} marks</legend>
      {q.written?<textarea aria-label="Written response" value={answer} onChange={e=>save(e.target.value)}/>:q.options.map((s,n)=><label key={n} className={"option "+(answer.includes(n)?"chosen":"")}>
        <input type={q.multi?"checkbox":"radio"} name={"answer-"+i} checked={answer.includes(n)} onChange={()=>choose(n)}/><span className="opt-letter">{String.fromCharCode(65+n)}</span>{s}</label>)}</fieldset>
      <div className="actions"><SaveStatus state={stored?"saved":"pending"}>{data.closed?"Sample submitted":stored?"Saved in this preview":"In memory only"}</SaveStatus>
        <div className="row"><button className="secondary" disabled={i===0} onClick={()=>patch({current:i-1})}>Previous</button><button className="primary" onClick={()=>i===7?setReview(true):patch({current:i+1})}>{i===7?"Review answers":"Next question →"}</button></div></div>
    </article><aside><AnswerSheet {...data} current={i} jump={n=>patch({current:n})} review={()=>setReview(true)}/>
      <div className="tools"><details><summary>Scratchpad</summary><div className="tool-body"><label>Private rough work<textarea disabled={data.closed} value={data.scratch} onChange={e=>patch({scratch:e.target.value})}/></label></div></details>
      <details><summary>Workspace settings</summary><div className="tool-body"><div className="prefs"><label>Text size <select value={data.size} onChange={e=>patch({size:Number(e.target.value)})}>{[80,100,125,150,200].map(n=><option key={n} value={n}>{n}%</option>)}</select></label>
      <label><input type="checkbox" checked={data.focus} onChange={e=>patch({focus:e.target.checked})}/> Focus layout</label></div></div></details></div></aside></div>
    {review && <Review data={data} close={()=>setReview(false)} submit={()=>{patch({closed:true,scratch:""});setReview(false);}}/>}
    {data.closed && <p className="reset"><button className="quiet" onClick={()=>setData({...seed})}>Restart sample attempt</button></p>}
  </main>;
}
const roster=[
 {name:"Nora Khan",answered:3,status:"Working"}, {name:"Eli Brooks",answered:5,status:"Reconnected"},
 {name:"Sana Ali",answered:8,status:"Submitted"}, {name:"Remy Chen",answered:6,status:"Working"}
];
function Stat({value,label}){return <div className="stat"><span className="mini">{label}</span><strong>{value}</strong></div>;}
export function ExaminerDesk(){
  const [text,setText]=useState(""),[announcements,setAnnouncements]=useState([]);
  return <main className="shell"><PageHead crumb="Examiner workspace" title="Examination monitor" details={<><b>BIO 204</b><i/>Field ecology<i/>Practical examination</>}/>
    <div className="workgrid"><section className="board"><h2>Candidate register</h2><div className="summary-grid"><Stat label="Enrolled" value="04"/><Stat label="In progress" value="03"/><Stat label="Submitted" value="01"/></div>
    <table className="data-table"><thead><tr><th>Candidate</th><th>Answered</th><th>Attempt</th></tr></thead><tbody>{roster.map(r=><tr key={r.name}><td>{r.name}</td><td>{r.answered} / 8</td><td><span className={"badge "+(r.status==="Reconnected"?"amber":"")}>{r.status}</span></td></tr>)}</tbody></table></section>
    <aside className="side"><div className="side-head"><h2>Exam activity</h2></div><div className="side-content"><div className="event"><time>10:42</time>Eli Brooks reconnected. Saved progress restored.</div>
    {announcements.map((s,i)=><div className="event" key={i}><time>Preview announcement</time>{s}</div>)}<form onSubmit={e=>{e.preventDefault();if(text.trim()){setAnnouncements(a=>[...a,text.trim()]);setText("");}}}>
    <label className="field-instruction">Announcement<textarea value={text} onChange={e=>setText(e.target.value)} required/></label><button className="primary" disabled={!text.trim()}>Post to preview</button></form></div></aside></div></main>;
}
const sampleAccounts=[["Nora Khan","Candidate"],["Eli Brooks","Candidate"],["Sana Ali","Candidate"],["Remy Chen","Examiner"]];
export function AdminDesk(){
  const [search,setSearch]=useState(""),[enabled,setEnabled]=useState([true,true,true,true]);
  const matches=sampleAccounts.map(([name,role],i)=>({name,role,i})).filter(r=>(r.name+" "+r.role).toLowerCase().includes(search.toLowerCase()));
  return <main className="shell"><PageHead crumb="Administration" title="Account directory" details={<><b>Access management</b><i/>Fictional accounts</>}/>
  <section className="board"><div className="split"><h2>Accounts</h2><input className="search" type="search" placeholder="Find name or role" aria-label="Find name or role" value={search} onChange={e=>setSearch(e.target.value)}/></div>
  <table className="data-table"><thead><tr><th>Name</th><th>Role</th><th>Access</th><th>Action</th></tr></thead><tbody>{matches.map(r=><tr key={r.i}><td>{r.name}</td><td>{r.role}</td><td><span className={"badge "+(enabled[r.i]?"":"amber")}>{enabled[r.i]?"Enabled":"Disabled"}</span></td><td><button className="quiet" aria-label={(enabled[r.i]?"Disable ":"Enable ")+r.name} onClick={()=>setEnabled(v=>v.map((x,j)=>j===r.i?!x:x))}>{enabled[r.i]?"Disable":"Enable"}</button></td></tr>)}</tbody></table>
  {!matches.length && <p className="event" role="status">No matching accounts.</p>}</section></main>;
}
export default function Folio({ figureUrl = "/transect.png" }){
  const [role,setRole]=useState("Candidate");
  return <><Header role={role} setRole={setRole}/>{role==="Candidate"?<CandidateWorkspace figureUrl={figureUrl}/>:role==="Examiner"?<ExaminerDesk/>:<AdminDesk/>}
    <footer className="foot"><span>Folio · Design preview</span><span>Fictional exam data</span></footer></>;
}
