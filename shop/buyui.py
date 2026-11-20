from __future__ import annotations

ST = r"""<style>
[hidden]{display:none!important}
.stp{display:flex;align-items:center;justify-content:center;gap:8px;margin:2px 0 18px;font-size:13px;color:var(--mu)}
.stp span{display:flex;align-items:center;gap:6px}
.stp i{font-style:normal;width:26px;height:26px;border-radius:50%;display:grid;place-items:center;background:#1b1b2a;border:1px solid #2c2c41;font-size:12px}
.stp .on{color:#fff}.stp .on i{background:linear-gradient(135deg,#a78bfa,#22d3ee);border:0}
.stp u{width:22px;height:2px;background:#2c2c41;border-radius:2px}
.tg{display:grid;grid-template-columns:repeat(auto-fill,minmax(118px,1fr));gap:12px;margin:18px 0 4px}
.tl{position:relative;display:block;padding:16px 8px 12px;border-radius:18px;text-align:center;background:#171724;border:1px solid #2a2a3d;transition:transform .2s,border-color .2s}
.tl:hover,.tl:active{transform:translateY(-3px);border-color:#7c5cf0}
.tl b{display:block;font-size:24px}.tl small{color:var(--mu);font-size:12px}.tl .pr{margin-top:6px;color:#c4b5fd;font-weight:700;font-size:13px}
.bdg{position:absolute;top:-9px;left:50%;transform:translateX(-50%);padding:2px 10px;border-radius:99px;background:linear-gradient(135deg,#34d399,#22d3ee);color:#04130d;font-size:11px;font-weight:700;white-space:nowrap}
.fm label{display:block;margin:16px 0 6px;color:var(--mu);font-size:13px}.fm input{text-align:left}
.rw{display:flex;gap:8px}.rw input{flex:1}
.ib{flex:none;min-width:46px;border-radius:14px;border:1px solid #2c2c41;background:#1b1b2a;color:var(--tx);font-family:inherit;cursor:pointer}
.hint{min-height:18px;margin-top:6px;font-size:12px;color:var(--mu)}.hint.ok{color:var(--up)}.hint.no{color:var(--dn)}
input[type=range]{padding:0;height:30px;margin-top:10px;accent-color:#a78bfa;direction:ltr}
.neg{color:#f87171}.pos{color:#34d399}
.wr{margin-top:14px;border-color:#5b3030!important;background:#1c1114!important}.tp{margin-top:14px;border-color:#2f4a40!important}
.er{margin-top:14px;padding:12px;border-radius:14px;background:#331818;color:var(--dn);font-size:14px}
.ov{position:fixed;inset:0;z-index:60;display:grid;place-items:end center;background:#000c}
.sh{width:min(100%,480px);padding:22px 22px calc(22px + env(safe-area-inset-bottom));border-radius:26px 26px 0 0;background:#12121a;border:1px solid var(--bd);animation:rv .3s both}
.sh h3{margin:0 0 10px}.ln{display:flex;justify-content:space-between;padding:9px 0;border-bottom:1px solid #1f1f2c}.ln:last-of-type{border:0}
.ac{display:flex;gap:10px;margin-top:16px}.ac .go,.ac .no{margin:0;flex:1}
.no{padding:14px;border-radius:14px;border:1px solid #2c2c41;background:#1b1b2a;color:var(--tx);font-family:inherit;font-size:15px;cursor:pointer}
.spn{width:54px;height:54px;margin:0 auto 14px;border-radius:50%;border:4px solid #2a2a3d;border-top-color:#a78bfa;animation:sp .8s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}
.okr{width:112px;height:112px;margin:6px auto 12px}.okr svg{width:100%;height:100%}
.okr .c{fill:rgba(52,211,153,.08);stroke:#34d399;stroke-width:4;stroke-linecap:round;stroke-dasharray:327;stroke-dashoffset:327;animation:dw .8s .1s cubic-bezier(.65,0,.35,1) forwards}
.okr .k{fill:none;stroke:#6ee7b7;stroke-width:6;stroke-linecap:round;stroke-linejoin:round;stroke-dasharray:70;stroke-dashoffset:70;animation:dw .5s .8s ease-out forwards}
@keyframes dw{to{stroke-dashoffset:0}}
.cr{display:flex;align-items:center;gap:10px;padding:12px 0;border-bottom:1px solid #1f1f2c}.cr:last-child{border:0}
.cr div{flex:1;min-width:0}.cr small{color:var(--mu);display:block;font-size:12px}
.cr b{display:block;direction:ltr;text-align:right;overflow:hidden;text-overflow:ellipsis}.cr .cp{margin:0}
#cf{position:fixed;inset:0;pointer-events:none;z-index:50}
</style>"""

FORM_JS = r"""<script>(function(){
var f=document.getElementById('bf');if(!f)return;
var B=+f.dataset.bal,PG=+f.dataset.pg||0,FIX=+f.dataset.fix||0,MN=+f.dataset.mn||0,MX=+f.dataset.mx||0;
function $(s){return document.querySelector(s)}
function F(n){return Number(n).toLocaleString('fa-IR')}
function cur(){if(FIX)return FIX;if(!f.gb)return 0;var v=f.gb.value.trim();if(!/^\d+(\.\d+)?$/.test(v))return 0;var g=parseFloat(v);return(g>=MN&&g<=MX)?Math.round(g*PG):0}
function upd(){var p=cur(),a=B-p,el=$('#af');$('#pv').textContent=p?F(p)+' تومان':'—';
if(!p){el.textContent='—';el.className='';$('#lw').hidden=true;return}
el.textContent=F(Math.max(a,0))+' تومان';el.className=a<0?'neg':'pos';$('#lw').hidden=a>=0;$('#lwa').textContent=F(Math.max(-a,0))}
var sl=$('#sl');
if(f.gb){if(sl)sl.oninput=function(){f.gb.value=sl.value;upd()};
f.gb.oninput=function(){var v=parseFloat(f.gb.value);if(sl&&v>=MN&&v<=MX)sl.value=v;upd()}}
var U=f.user,P=f.pw,uh=$('#uh');
U.oninput=function(){var ok=/^[A-Za-z][A-Za-z0-9_]{3,19}$/.test(U.value);uh.className='hint '+(U.value?(ok?'ok':'no'):'');uh.textContent=U.value?(ok?'✓ نام معتبر است':'انگلیسی، عدد و _ ، ۴ تا ۲۰ کاراکتر، شروع با حرف'):''};
function gen(){var a='abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ',d='23456789',r=new Uint32Array(14),s=[],i;crypto.getRandomValues(r);
for(i=0;i<9;i++)s.push(a[r[i]%a.length]);for(i=9;i<12;i++)s.push(d[r[i]%8]);s.push(a[r[12]%a.length]);s.push(d[r[13]%8]);return s.join('')}
$('#gp').onclick=function(){P.type='text';P.value=gen()};
$('#tp').onclick=function(){P.type=P.type==='password'?'text':'password'};
var ov=$('#ov'),ld=$('#ld'),go=false;
f.onsubmit=function(e){if(go)return true;e.preventDefault();var p=cur();
if(!U.value||!P.value){if(f.reportValidity)f.reportValidity();return false}
if(!p)return false;
if(B<p){$('#lw').hidden=false;$('#lw').scrollIntoView({behavior:'smooth'});return false}
$('#cs').textContent=F(p)+' تومان';$('#ca').textContent=F(B-p)+' تومان';$('#cu').textContent=U.value;ov.hidden=false;return false};
$('#cn').onclick=function(){ov.hidden=true};
$('#cy').onclick=function(){go=true;ov.hidden=true;ld.hidden=false;f.submit()};
upd();U.oninput();
})();</script>"""

DONE_JS = r"""<canvas id="cf"></canvas><script>(function(){
if(matchMedia('(prefers-reduced-motion:reduce)').matches)return;
var c=document.getElementById('cf'),x=c.getContext('2d'),W=c.width=innerWidth,H=c.height=innerHeight,P=[],col=['#a78bfa','#34d399','#fbbf24','#f472b6','#22d3ee','#fff'],i;
setTimeout(function(){for(i=0;i<80;i++){var a=Math.random()*6.283,s=Math.random()*8+4;P.push({x:W/2,y:H*.3,vx:Math.cos(a)*s,vy:Math.sin(a)*s-5,w:Math.random()*7+4,h:Math.random()*4+3,r:Math.random()*6,vr:(Math.random()-.5)*.4,c:col[i%6],l:1})}
(function f(){x.clearRect(0,0,W,H);P=P.filter(function(p){p.x+=p.vx;p.y+=p.vy;p.vy+=.28;p.vx*=.985;p.r+=p.vr;p.l-=.012;if(p.l<=0)return false;x.save();x.globalAlpha=p.l;x.translate(p.x,p.y);x.rotate(p.r);x.fillStyle=p.c;x.fillRect(-p.w/2,-p.h/2,p.w,p.h);x.restore();return true});if(P.length)requestAnimationFrame(f);else c.remove()})()},800)})();</script>"""
