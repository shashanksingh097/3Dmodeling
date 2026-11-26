"""A model as one web page (EXPORT, HTML; PLAN item 114).

The page holds everything in one file: the bodies' triangles and edges (base64 numbers), their
names and colours, the notes pinned to the model, and a small WebGL viewer written for it, with no
library and nothing fetched from the internet. Anyone opens it in a browser: turn, pan and zoom
the model, hide and show parts, click two points to measure the distance between them, and read
the notes. The viewer's code is in VIEWER below.
"""

from __future__ import annotations

import base64
import html
import json
from dataclasses import dataclass

import numpy as np
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
from OCP.BRepLib import BRepLib_ToolTriangulatedShape
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.GCPnts import GCPnts_TangentialDeflection
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_REVERSED
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location

MAX_TRIANGLES = 3_000_000  # a page bigger than this would be too slow to open


@dataclass
class Part:
    name: str
    color: tuple
    shown: bool
    points: np.ndarray  # (n, 3) float32
    normals: np.ndarray  # (n, 3) float32
    tris: np.ndarray  # (m, 3) uint32
    edges: np.ndarray  # (k, 2, 3) float32: line pieces


def _b64(a: np.ndarray) -> str:
    return base64.b64encode(np.ascontiguousarray(a).tobytes()).decode("ascii")


def part_of(shape, name: str, color, deflection: float, shown: bool = True) -> Part:
    """One body's triangles with smooth normals per face, and its edges as polylines."""
    from . import meshbody
    from .features import as_edge, as_face

    if meshbody.is_mesh(shape):
        pts, t = meshbody.arrays(shape)
        pts, t = np.asarray(pts, float), np.asarray(t, np.int64)
        tp = pts[t]  # flat normals for a mesh body: corners not shared
        n = np.cross(tp[:, 1] - tp[:, 0], tp[:, 2] - tp[:, 0])
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-30)
        return Part(name, color, shown, tp.reshape(-1, 3).astype(np.float32), np.repeat(n, 3, axis=0).astype(np.float32),
                    np.arange(len(t) * 3, dtype=np.uint32).reshape(-1, 3), np.zeros((0, 2, 3), np.float32))
    shape = BRepBuilderAPI_Copy(shape).Shape()
    BRepMesh_IncrementalMesh(shape, deflection, False, 0.35, True)
    pts, nrm, tris = [], [], []
    base = 0
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        face = as_face(ex.Current())
        ex.Next()
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is None or tri.NbTriangles() == 0:
            continue
        if not tri.HasNormals():
            BRepLib_ToolTriangulatedShape.ComputeNormals_s(face, tri)
        trsf = loc.Transformation()
        rev = face.Orientation() == TopAbs_REVERSED
        nn = tri.NbNodes()
        p = np.empty((nn, 3))
        q = np.empty((nn, 3))
        for i in range(1, nn + 1):
            a = tri.Node(i).Transformed(trsf)
            p[i - 1] = (a.X(), a.Y(), a.Z())
            d = tri.Normal(i).Transformed(trsf)
            q[i - 1] = (d.X(), d.Y(), d.Z())
        if rev:
            q = -q
        t = np.array([tri.Triangle(i).Get() for i in range(1, tri.NbTriangles() + 1)], dtype=np.int64) - 1
        if rev:
            t = t[:, [0, 2, 1]]
        pts.append(p)
        nrm.append(q)
        tris.append(t + base)
        base += nn
    lines = []
    seen = set()
    edges = []
    fx = TopExp_Explorer(shape, TopAbs_FACE)
    while fx.More():  # each face's edges, leaving out seams (a cylinder's or a sphere's joint line)
        face = as_face(fx.Current())
        fx.Next()
        ex = TopExp_Explorer(face, TopAbs_EDGE)
        while ex.More():
            e = as_edge(ex.Current())
            ex.Next()
            if BRep_Tool.Degenerated_s(e) or BRep_Tool.IsClosed_s(e, face):
                seen.add(e.__hash__())
                continue
            edges.append(e)
    ex = TopExp_Explorer(shape, TopAbs_EDGE, TopAbs_FACE)  # loose edges: wires, curves
    while ex.More():
        edges.append(as_edge(ex.Current()))
        ex.Next()
    for e in edges:
        h = e.__hash__()
        if h in seen:
            continue
        seen.add(h)
        try:
            c = BRepAdaptor_Curve(e)
            disc = GCPnts_TangentialDeflection(c, 0.3, deflection)
            poly = [disc.Value(i) for i in range(1, disc.NbPoints() + 1)]
        except Exception:  # noqa: BLE001 - an edge that will not discretise is left out
            continue
        for a, b in zip(poly, poly[1:]):
            lines.append(((a.X(), a.Y(), a.Z()), (b.X(), b.Y(), b.Z())))
    if not tris:
        return Part(name, color, shown, np.zeros((0, 3), np.float32), np.zeros((0, 3), np.float32),
                    np.zeros((0, 3), np.uint32), np.asarray(lines, np.float32).reshape(-1, 2, 3))
    return Part(name, color, shown, np.vstack(pts).astype(np.float32), np.vstack(nrm).astype(np.float32),
                np.vstack(tris).astype(np.uint32), np.asarray(lines, np.float32).reshape(-1, 2, 3))


def page(parts: list[Part], notes: list[dict], title: str, units: str) -> str:
    data = {
        "title": title, "units": units.lower(),
        "parts": [{"name": pt.name, "color": [round(float(c), 4) for c in pt.color],
                   "p": _b64(pt.points), "n": _b64(pt.normals), "t": _b64(pt.tris), "e": _b64(pt.edges),
                   "tris": int(len(pt.tris)), "shown": pt.shown} for pt in parts],
        "notes": notes,
    }
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    return (VIEWER.replace("__TITLE__", html.escape(title)).replace("__DATA__", blob))


VIEWER = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#f4f5f7;--panel:#fff;--ink:#1c1e21;--mute:#666b73;--line:#d9dce1;--accent:#1f6fd1}
@media (prefers-color-scheme:dark){:root{--bg:#1d1f23;--panel:#272a2f;--ink:#e4e6ea;--mute:#a0a6ae;--line:#3a3e45;--accent:#6aa8ff}}
*{box-sizing:border-box}html,body{margin:0;height:100%;background:var(--bg);color:var(--ink);font:14px/1.4 system-ui,sans-serif}
#app{display:flex;height:100%}#side{width:260px;flex:none;background:var(--panel);border-right:1px solid var(--line);overflow:auto;padding:12px}
#view{position:relative;flex:1;min-width:0}canvas{display:block;width:100%;height:100%;touch-action:none}
h1{font-size:16px;margin:0 0 8px}h2{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--mute);margin:16px 0 6px}
label.part{display:flex;align-items:center;gap:6px;padding:2px 0;cursor:pointer}.sw{width:12px;height:12px;border-radius:2px;flex:none;border:1px solid var(--line)}
button{font:inherit;color:var(--ink);background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:4px 9px;cursor:pointer}
button.on{background:var(--accent);color:#fff;border-color:var(--accent)}#bar{position:absolute;top:10px;left:10px;display:flex;gap:6px;flex-wrap:wrap}
#readout{position:absolute;bottom:10px;left:10px;background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:6px 10px;display:none}
.note{position:absolute;transform:translate(-50%,-100%);background:var(--panel);border:1px solid var(--line);border-radius:4px;padding:2px 6px;font-size:12px;white-space:nowrap;pointer-events:none}
.mark{position:absolute;width:10px;height:10px;margin:-5px 0 0 -5px;border-radius:50%;background:#e33;pointer-events:none}
#notes div{padding:2px 0;color:var(--mute)}small{color:var(--mute)}
@media (max-width:640px){#app{flex-direction:column}#side{width:auto;height:35%;border-right:0;border-bottom:1px solid var(--line)}}
</style></head><body><div id="app"><div id="side"><h1 id="title"></h1><small id="info"></small>
<h2>Parts</h2><div id="parts"></div><div style="margin-top:6px"><button id="all">Show all</button></div>
<h2>Notes</h2><div id="notes"></div>
<h2>How</h2><small>Drag to turn · right-drag or Shift-drag to pan · wheel or pinch to zoom · Measure: click two points</small></div>
<div id="view"><canvas id="c"></canvas><div id="bar"><button data-v="fit">Fit</button><button data-v="iso">Iso</button>
<button data-v="top">Top</button><button data-v="front">Front</button><button data-v="right">Right</button>
<button id="measure">Measure</button><button id="shownotes" class="on">Notes</button></div><div id="readout"></div><div id="labels"></div></div></div>
<script id="data" type="application/json">__DATA__</script>
<script>
"use strict";
const D=JSON.parse(document.getElementById("data").textContent);
const cv=document.getElementById("c"),gl=cv.getContext("webgl2",{antialias:true});
if(!gl){document.getElementById("view").textContent="This page needs WebGL 2 (any recent browser).";throw new Error("no WebGL 2")}
document.getElementById("title").textContent=D.title;
function dec(s,T){const b=atob(s),u=new Uint8Array(b.length);for(let i=0;i<b.length;i++)u[i]=b.charCodeAt(i);return new T(u.buffer)}
function vs(t,s){const h=gl.createShader(t);gl.shaderSource(h,s);gl.compileShader(h);return h}
function prog(a,b){const p=gl.createProgram();gl.attachShader(p,vs(gl.VERTEX_SHADER,a));gl.attachShader(p,vs(gl.FRAGMENT_SHADER,b));gl.linkProgram(p);return p}
const P=prog(`#version 300 es
in vec3 p;in vec3 n;uniform mat4 M;uniform mat3 R;out vec3 N;void main(){N=R*n;gl_Position=M*vec4(p,1.);}`,
`#version 300 es
precision mediump float;in vec3 N;uniform vec3 C;out vec4 o;void main(){vec3 n=normalize(N);if(!gl_FrontFacing)n=-n;
float d=max(dot(n,normalize(vec3(.4,.5,1.))),0.),f=max(dot(n,normalize(vec3(-.6,-.2,.5))),0.);o=vec4(C*(.32+.6*d+.18*f)+pow(d,24.)*.25,1.);}`);
const L=prog(`#version 300 es
in vec3 p;uniform mat4 M;void main(){gl_Position=M*vec4(p,1.);gl_Position.z-=.00015*gl_Position.w;}`,
`#version 300 es
precision mediump float;uniform vec3 C;out vec4 o;void main(){o=vec4(C,1.);}`);
let lo=[1e30,1e30,1e30],hi=[-1e30,-1e30,-1e30],ntri=0;
const parts=D.parts.map((d,k)=>{const p=dec(d.p,Float32Array),n=dec(d.n,Float32Array),t=dec(d.t,Uint32Array),e=dec(d.e,Float32Array);
for(let i=0;i<p.length;i+=3)for(let j=0;j<3;j++){lo[j]=Math.min(lo[j],p[i+j]);hi[j]=Math.max(hi[j],p[i+j])}
for(let i=0;i<e.length;i+=3)for(let j=0;j<3;j++){lo[j]=Math.min(lo[j],e[i+j]);hi[j]=Math.max(hi[j],e[i+j])}
ntri+=t.length/3;const va=gl.createVertexArray();gl.bindVertexArray(va);
const b=(a,loc)=>{const bf=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,bf);gl.bufferData(gl.ARRAY_BUFFER,a,gl.STATIC_DRAW);gl.enableVertexAttribArray(loc);gl.vertexAttribPointer(loc,3,gl.FLOAT,false,0,0)};
b(p,gl.getAttribLocation(P,"p"));b(n,gl.getAttribLocation(P,"n"));const ib=gl.createBuffer();gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,ib);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,t,gl.STATIC_DRAW);
const ea=gl.createVertexArray();gl.bindVertexArray(ea);b(e,gl.getAttribLocation(L,"p"));gl.bindVertexArray(null);
return{name:d.name,color:d.color,p,t,va,ea,nt:t.length,ne:e.length/3,shown:d.shown!==false}});
if(!parts.length){lo=[-1,-1,-1];hi=[1,1,1]}
document.getElementById("info").textContent=parts.length+" part"+(parts.length==1?"":"s")+", "+ntri.toLocaleString()+" triangles, sizes in "+D.units;
const ctr=[0,1,2].map(i=>(lo[i]+hi[i])/2),rad=Math.max(Math.hypot(hi[0]-lo[0],hi[1]-lo[1],hi[2]-lo[2])/2,1e-6);
function fitd(){const b=cv.getBoundingClientRect(),a=b.width/Math.max(b.height,1);return rad/Math.tan(0.3)/Math.min(1,a)*1.08}
let cam={t:ctr.slice(),d:fitd(),yaw:-0.785,pitch:0.615};
function views(v){const a={iso:[-0.785,0.615],top:[0,Math.PI/2-1e-4],front:[0,0],right:[Math.PI/2,0]};if(v!="fit")[cam.yaw,cam.pitch]=a[v];cam.t=ctr.slice();cam.d=fitd();draw()}
function sub(a,b){return[a[0]-b[0],a[1]-b[1],a[2]-b[2]]}function cross(a,b){return[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]}
function nz(a){const l=Math.hypot(...a)||1;return a.map(x=>x/l)}function dot(a,b){return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]}
function frame(){const cp=Math.cos(cam.pitch),f=[-cp*Math.sin(cam.yaw),cp*Math.cos(cam.yaw),-Math.sin(cam.pitch)];
/* f: from the eye to the target, Z up */const eye=sub(cam.t,f.map(x=>x*cam.d)),r=nz(cross(f,[0,0,1])),u=cross(r,f);return{eye,f,r,u}}
function mats(){const{eye,f,r,u}=frame(),w=cv.width,h=cv.height,a=w/h,near=Math.max(cam.d-rad*4,cam.d*0.01),far=cam.d+rad*4,t=Math.tan(0.3);
const V=[r[0],u[0],-f[0],0,r[1],u[1],-f[1],0,r[2],u[2],-f[2],0,-dot(r,eye),-dot(u,eye),dot(f,eye),1];
const Pm=[1/(t*a),0,0,0,0,1/t,0,0,0,0,-(far+near)/(far-near),-1,0,0,-2*far*near/(far-near),0];
const M=new Array(16);for(let i=0;i<4;i++)for(let j=0;j<4;j++){let s=0;for(let k=0;k<4;k++)s+=Pm[k*4+j]*V[i*4+k];M[i*4+j]=s}
return{M,R:[r[0],u[0],-f[0],r[1],u[1],-f[1],r[2],u[2],-f[2]],eye,f,r,u,t,a}}
function proj(M,q){const x=M[0]*q[0]+M[4]*q[1]+M[8]*q[2]+M[12],y=M[1]*q[0]+M[5]*q[1]+M[9]*q[2]+M[13],w=M[3]*q[0]+M[7]*q[1]+M[11]*q[2]+M[15];
if(w<=0)return null;const b=cv.getBoundingClientRect();return[(x/w+1)/2*b.width,(1-y/w)/2*b.height]}
let pick=[],showNotes=true;
function draw(){const dpr=window.devicePixelRatio||1,b=cv.getBoundingClientRect();cv.width=Math.max(1,b.width*dpr|0);cv.height=Math.max(1,b.height*dpr|0);
gl.viewport(0,0,cv.width,cv.height);const dark=matchMedia("(prefers-color-scheme: dark)").matches;gl.clearColor(...(dark?[.16,.17,.19]:[.93,.94,.96]),1);
gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.enable(gl.DEPTH_TEST);const m=mats();
gl.useProgram(P);gl.uniformMatrix4fv(gl.getUniformLocation(P,"M"),false,m.M);gl.uniformMatrix3fv(gl.getUniformLocation(P,"R"),false,m.R);
for(const p of parts)if(p.shown){gl.uniform3fv(gl.getUniformLocation(P,"C"),p.color);gl.bindVertexArray(p.va);gl.drawElements(gl.TRIANGLES,p.nt,gl.UNSIGNED_INT,0)}
gl.useProgram(L);gl.uniformMatrix4fv(gl.getUniformLocation(L,"M"),false,m.M);
for(const p of parts)if(p.shown&&p.ne){gl.uniform3fv(gl.getUniformLocation(L,"C"),p.color.map(c=>c*.22));gl.bindVertexArray(p.ea);gl.drawArrays(gl.LINES,0,p.ne)}
gl.bindVertexArray(null);const box=document.getElementById("labels");box.innerHTML="";
if(showNotes)for(const n of D.notes){const s=proj(m.M,n.at);if(!s)continue;const d=document.createElement("div");d.className="note";d.style.left=s[0]+"px";d.style.top=s[1]+"px";d.textContent=n.text;box.appendChild(d)}
for(const q of pick){const s=proj(m.M,q);if(!s)continue;const d=document.createElement("div");d.className="mark";d.style.left=s[0]+"px";d.style.top=s[1]+"px";box.appendChild(d)}}
function ray(x,y){const m=mats(),b=cv.getBoundingClientRect(),nx=(x/b.width)*2-1,ny=1-(y/b.height)*2;
const dir=nz([0,1,2].map(i=>m.f[i]+m.r[i]*nx*m.t*m.a+m.u[i]*ny*m.t));return{o:m.eye,d:dir}}
function hit(x,y){const{o,d}=ray(x,y);let best=Infinity;for(const p of parts){if(!p.shown)continue;const P_=p.p,T=p.t;
for(let i=0;i<T.length;i+=3){const a=T[i]*3,b=T[i+1]*3,c=T[i+2]*3,e1=[P_[b]-P_[a],P_[b+1]-P_[a+1],P_[b+2]-P_[a+2]],e2=[P_[c]-P_[a],P_[c+1]-P_[a+1],P_[c+2]-P_[a+2]],
h=cross(d,e2),det=dot(e1,h);if(Math.abs(det)<1e-12)continue;const s=[o[0]-P_[a],o[1]-P_[a+1],o[2]-P_[a+2]],u=dot(s,h)/det;if(u<0||u>1)continue;
const q=cross(s,e1),v=dot(d,q)/det;if(v<0||u+v>1)continue;const t=dot(e2,q)/det;if(t>0&&t<best)best=t}}
return best<Infinity?[0,1,2].map(i=>o[i]+d[i]*best):null}
const fmt=x=>(Math.round(x*1e4)/1e4).toString();
let measuring=false,drag=null;
cv.addEventListener("pointerdown",e=>{cv.setPointerCapture(e.pointerId);drag={x:e.clientX,y:e.clientY,b:e.button,s:e.shiftKey,moved:false}});
cv.addEventListener("pointermove",e=>{if(!drag)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(Math.abs(dx)+Math.abs(dy)>2)drag.moved=true;drag.x=e.clientX;drag.y=e.clientY;
if(drag.b==2||drag.s){const m=mats(),k=cam.d*2*m.t/cv.getBoundingClientRect().height;for(let i=0;i<3;i++)cam.t[i]+=(-dx*m.r[i]+dy*m.u[i])*k}
else{cam.yaw-=dx*0.008;cam.pitch=Math.max(-1.5707,Math.min(1.5707,cam.pitch+dy*0.008))}draw()});
cv.addEventListener("pointerup",e=>{const b=cv.getBoundingClientRect();if(drag&&!drag.moved&&measuring&&drag.b==0){const q=hit(e.clientX-b.left,e.clientY-b.top);
if(q){if(pick.length>=2)pick=[];pick.push(q);const r=document.getElementById("readout");r.style.display="block";
const v=pick.length==2?sub(pick[1],pick[0]):null;
r.textContent=!v?"Point "+q.map(fmt).join(", ")+": click a second point":"Distance "+fmt(Math.hypot(...v))+" "+D.units+" (dx "+fmt(v[0])+", dy "+fmt(v[1])+", dz "+fmt(v[2])+")";draw()}}drag=null});
cv.addEventListener("contextmenu",e=>e.preventDefault());
cv.addEventListener("wheel",e=>{e.preventDefault();cam.d*=Math.exp(e.deltaY*0.0012);draw()},{passive:false});
document.querySelectorAll("[data-v]").forEach(b=>b.onclick=()=>views(b.dataset.v));
document.getElementById("measure").onclick=e=>{measuring=!measuring;e.target.classList.toggle("on",measuring);pick=[];document.getElementById("readout").style.display="none";draw()};
document.getElementById("shownotes").onclick=e=>{showNotes=!showNotes;e.target.classList.toggle("on",showNotes);draw()};
const pl=document.getElementById("parts");parts.forEach(p=>{const l=document.createElement("label");l.className="part";const c=document.createElement("input");c.type="checkbox";c.checked=p.shown;
c.onchange=()=>{p.shown=c.checked;draw()};const s=document.createElement("span");s.className="sw";s.style.background="rgb("+p.color.map(x=>x*255|0).join(",")+")";
l.append(c,s,document.createTextNode(p.name));pl.appendChild(l)});
document.getElementById("all").onclick=()=>{parts.forEach(p=>p.shown=true);pl.querySelectorAll("input").forEach(c=>c.checked=true);draw()};
const nl=document.getElementById("notes");if(!D.notes.length)nl.innerHTML="<small>none</small>";D.notes.forEach(n=>{const d=document.createElement("div");d.textContent=n.text;nl.appendChild(d)});
addEventListener("resize",draw);draw();
</script></body></html>
"""
