(function(){'use strict';
/* 模块1: 记忆翻牌 */
(function(){var e='🐶🐱🐭🐹🐰🦊🐻🐼🐨🐯🦁🐮🐸🐵🐧🐦🐤🐣🐺🦄🐴🦋🐛🐝🐞🦀🐳🐬🐟🐠🐡🦈🐊🐅🦍🦧🐘🦏🐪🐫🦒🦘🦡🦨🦦🦥🐁🐀🐿️🦔🐇🐈🦮🐕‍🦺🐕🐩🐶🐱🐭🐹'.split('');
var b=document.getElementById('board'),me=document.getElementById('moves'),pe=document.getElementById('pairs'),te=document.getElementById('timer'),se=document.getElementById('gameStatus'),nb=document.getElementById('newGameBtn'),eb=document.getElementById('easyBtn'),hb=document.getElementById('hardBtn');
var co=4,ro=3,ca=[],fl=[],ma=0,mo=0,lo=0,ti=null,sec=0,st=0;
function sh(a){for(var i=a.length-1;i>0;i--){var j=Math.floor(Math.random()*(i+1)),t=a[i];a[i]=a[j];a[j]=t}return a}
function ig(c,r){co=c;ro=r;var t=co*ro;if(t%2!==0){ro++;t=co*ro}var pn=t/2,ch=[],po=e.slice();sh(po);for(var i=0;i<pn;i++){ch.push(po[i%po.length]);ch.push(po[i%po.length])}sh(ch);ca=ch.map(function(em,i){return{id:i,emoji:em,flipped:0,matched:0}});fl=[];ma=0;mo=0;sec=0;st=0;lo=0;if(ti){clearInterval(ti);ti=null}me.textContent='0';pe.textContent='0';te.textContent='0s';se.textContent='✦ 点击卡片开始游戏';rd()}
function rd(){b.style.gridTemplateColumns='repeat('+co+',1fr)';b.innerHTML='';ca.forEach(function(c,i){var t=document.createElement('div');t.className='tile';if(c.flipped||c.matched)t.classList.add('flipped');if(c.matched)t.classList.add('matched');t.dataset.index=i;t.innerHTML='<div class="face front"></div><div class="face back">'+c.emoji+'</div>';t.addEventListener('click',function(){fc(i)});b.appendChild(t)})}
function fc(i){if(lo)return;var c=ca[i];if(c.matched||c.flipped)return;if(fl.length>=2)return;if(!st){st=1;ti=setInterval(function(){sec++;te.textContent=sec+'s'},1000)}c.flipped=1;fl.push(i);rd();if(fl.length===2){mo++;me.textContent=mo;lo=1;var a=ca[fl[0]],b2=ca[fl[1]];if(a.emoji===b2.emoji){a.matched=1;b2.matched=1;ma++;pe.textContent=ma;fl=[];lo=0;if(ma===ca.length/2){if(ti){clearInterval(ti);ti=null}se.innerHTML='🎉 通关！用时 <strong>'+sec+'s</strong>，步数 <strong>'+mo+'</strong>'}rd()}else{se.textContent='❌ 不匹配';setTimeout(function(){ca[fl[0]].flipped=0;ca[fl[1]].flipped=0;fl=[];lo=0;se.textContent='💡 继续配对';rd()},700)}}}
nb.addEventListener('click',function(){ig(4,3)});eb.addEventListener('click',function(){ig(4,3)});hb.addEventListener('click',function(){ig(4,5)});ig(4,3)})();

/* 模块2: 像素画板 */
(function(){var cs=['#6c5ce7','#00cec9','#55efc4','#fd79a8','#fdcb6e','#e17055','#0984e3','#d63031','#ffffff','#2d3436'];var gs=20,cc='#6c5ce7',bs=2,down=0;var g=document.getElementById('pixelGrid'),cp=document.getElementById('colorPicker'),br=document.getElementById('brushSize'),bv=document.getElementById('brushSizeVal'),bl=document.getElementById('brushSizeLabel'),cb=document.getElementById('clearCanvasBtn'),fb=document.getElementById('fillCanvasBtn'),pc=document.getElementById('pxCount');var px=[];function bp(){cp.innerHTML='';cs.forEach(function(c){var d=document.createElement('div');d.className='cpt'+(c===cc?' active':'');d.style.background=c;d.addEventListener('click',function(){cp.querySelectorAll('.cpt').forEach(function(e){e.classList.remove('active')});d.classList.add('active');cc=c});cp.appendChild(d)})}
function i2(){px=[];for(var y=0;y<gs;y++){px[y]=[];for(var x=0;x<gs;x++){px[y][x]=null}}rg();up()}
function rg(){g.style.gridTemplateColumns='repeat('+gs+',1fr)';g.innerHTML='';for(var y=0;y<gs;y++){for(var x=0;x<gs;x++){var p=document.createElement('div');p.className='px';p.dataset.x=x;p.dataset.y=y;p.style.background=px[y][x]||'rgba(255,255,255,0.02)';p.addEventListener('mousedown',function(e){e.preventDefault();pt(+this.dataset.x,+this.dataset.y)});p.addEventListener('mouseenter',function(){if(down)pt(+this.dataset.x,+this.dataset.y)});g.appendChild(p)}}}
function pt(x,y){var sz=parseInt(bs),hf=Math.floor(sz/2);for(var dy=-hf;dy<=hf;dy++){for(var dx=-hf;dx<=hf;dx++){var nx=x+dx,ny=y+dy;if(nx>=0&&nx<gs&&ny>=0&&ny<gs)px[ny][nx]=cc}}rg();up()}
function up(){var c=0;for(var y=0;y<gs;y++)for(var x=0;x<gs;x++)if(px[y][x])c++;pc.textContent=c}
document.addEventListener('mousedown',function(){down=1});document.addEventListener('mouseup',function(){down=0});g.addEventListener('mouseleave',function(){down=0});
br.addEventListener('input',function(){bs=+this.value;bv.textContent=bs;bl.textContent=bs+'x'+bs});
cb.addEventListener('click',function(){for(var y=0;y<gs;y++)for(var x=0;x<gs;x++)px[y][x]=null;rg();up()});
fb.addEventListener('click',function(){for(var y=0;y<gs;y++)for(var x=0;x<gs;x++)px[y][x]=cc;rg();up()});
bp();i2()})();

/* 模块3: 重力沙盘 */
(function(){var c=document.getElementById('sandboxCanvas'),w=document.getElementById('sandboxWrap'),h=document.getElementById('sandboxHint'),ce=document.getElementById('sandCount'),we=document.getElementById('waterCount'),cb=document.getElementById('clearSandBtn'),eb=document.getElementById('explodeSandBtn'),wb=document.getElementById('wallSandBtn'),sr=document.getElementById('sandSize'),mbs=document.querySelectorAll('.m3 .mode-group .m');var ctx=c.getContext('2d'),W=0,H=0,cols=0,rows=0,cs=4,gr=[],mode='sand',bs2=2,down=0,aid=0;
function rs(){var r=w.getBoundingClientRect();W=r.width;H=r.height;var dpr=window.devicePixelRatio||1;c.width=W*dpr;c.height=H*dpr;c.style.width=W+'px';c.style.height=H+'px';ctx.setTransform(1,0,0,1,0,0);ctx.scale(dpr,dpr);cols=Math.floor(W/cs);rows=Math.floor(H/cs);i3()}
function i3(){gr=[];for(var y=0;y<rows;y++){gr[y]=[];for(var x=0;x<cols;x++){gr[y][x]=0}}dr()}
function gcr(e){var r=c.getBoundingClientRect();return{col:Math.floor((e.clientX-r.left)/cs),row:Math.floor((e.clientY-r.top)/cs)}}
function pt2(col,row){if(col<0||col>=cols||row<0||row>=rows)return;var sz=parseInt(bs2),hf=Math.floor(sz/2);for(var dy=-hf;dy<=hf;dy++){for(var dx=-hf;dx<=hf;dx++){var nx=col+dx,ny=row+dy;if(nx>=0&&nx<cols&&ny>=0&&ny<rows){if(mode==='eraser')gr[ny][nx]=0;else if(mode==='wall')gr[ny][nx]=3;else if(mode==='sand'&&gr[ny][nx]===0)gr[ny][nx]=1;else if(mode==='water'&&gr[ny][nx]===0)gr[ny][nx]=2}}}}
var mc=-1,mr=-1;c.addEventListener('mousedown',function(e){down=1;var p=gcr(e);mc=p.col;mr=p.row;pt2(p.col,p.row);if(h)h.classList.add('hid')});
c.addEventListener('mousemove',function(e){var p=gcr(e);if(p.col!==mc||p.row!==mr){mc=p.col;mr=p.row;if(down)pt2(p.col,p.row)}});
document.addEventListener('mouseup',function(){down=0});c.addEventListener('mouseleave',function(){down=0});
c.addEventListener('touchstart',function(e){e.preventDefault();var t=e.touches[0];c.dispatchEvent(new MouseEvent('mousedown',{clientX:t.clientX,clientY:t.clientY}))});
c.addEventListener('touchmove',function(e){e.preventDefault();var t=e.touches[0];c.dispatchEvent(new MouseEvent('mousemove',{clientX:t.clientX,clientY:t.clientY}))});
c.addEventListener('touchend',function(e){e.preventDefault();document.dispatchEvent(new MouseEvent('mouseup',{}))});
function sim(){for(var y=rows-2;y>=0;y--){for(var x=0;x<cols;x++){if(gr[y][x]===1){if(gr[y+1][x]===0){gr[y][x]=0;gr[y+1][x]=1}else if(gr[y+1][x]===2){gr[y][x]=2;gr[y+1][x]=1}else if(x>0&&gr[y+1][x-1]===0){gr[y][x]=0;gr[y+1][x-1]=1}else if(x<cols-1&&gr[y+1][x+1]===0){gr[y][x]=0;gr[y+1][x+1]=1}}}}for(var y=rows-2;y>=0;y--){for(var x=0;x<cols;x++){if(gr[y][x]===2){if(gr[y+1][x]===0){gr[y][x]=0;gr[y+1][x]=2}else if(x>0&&gr[y][x-1]===0&&gr[y+1][x-1]===0){gr[y][x]=0;gr[y][x-1]=2}else if(x<cols-1&&gr[y][x+1]===0&&gr[y+1][x+1]===0){gr[y][x]=0;gr[y][x+1]=2}else if(x>0&&gr[y][x-1]===0){gr[y][x]=0;gr[y][x-1]=2}else if(x<cols-1&&gr[y][x+1]===0){gr[y][x]=0;gr[y][x+1]=2}}}}dr();up3();aid=requestAnimationFrame(sim)}
function dr(){ctx.clearRect(0,0,W,H);var sc=0,wc=0;for(var y=0;y<rows;y++){for(var x=0;x<cols;x++){var v=gr[y][x];if(v!==0){if(v===1){ctx.fillStyle='rgba(253,121,168,0.8)';sc++}else if(v===2){ctx.fillStyle='rgba(0,206,201,0.6)';wc++}else{ctx.fillStyle='rgba(255,255,255,0.15)'}ctx.fillRect(x*cs,y*cs,cs-1,cs-1)}}}ce.textContent=sc;we.textContent=wc}
function up3(){var sc=0,wc=0;for(var y=0;y<rows;y++){for(var x=0;x<cols;x++){if(gr[y][x]===1)sc++;else if(gr[y][x]===2)wc++}}ce.textContent=sc;we.textContent=wc}
cb.addEventListener('click',function(){i3()});
eb.addEventListener('click',function(){for(var y=0;y<rows;y++){for(var x=0;x<cols;x++){if(gr[y][x]!==0)gr[y][x]=0}}});
wb.addEventListener('click',function(){for(var x=0;x<cols;x++){gr[rows-1][x]=3}for(var y=0;y<rows;y++){gr[y][0]=3;gr[y][cols-1]=3}});
mbs.forEach(function(b){b.addEventListener('click',function(){mbs.forEach(function(b2){b2.classList.remove('active')});b.classList.add('active');mode=b.dataset.mode})});
sr.addEventListener('input',function(){bs2=parseInt(this.value)});
window.addEventListener('resize',rs);setTimeout(rs,100)})();
})();
