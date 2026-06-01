function draw(){ctx.clearRect(0,0,W,H);var sc=0,wc=0;for(var y=0;y<rows;y++){for(var x=0;x<cols;x++){var v=gr[y][x];if(v!==0){if(v===1){ctx.fillStyle='rgba(253,121,168,0.8)';sc++}else if(v===2){ctx.fillStyle='rgba(0,206,201,0.6)';wc++}else{ctx.fillStyle='rgba(255,255,255,0.15)'}ctx.fillRect(x*cs,y*cs,cs-1,cs-1)}}}ce.textContent=sc;we.textContent=wc}
function up3(){var sc=0,wc=0;for(var y=0;y<rows;y++){for(var x=0;x<cols;x++){if(gr[y][x]===1)sc++;else if(gr[y][x]===2)wc++}}ce.textContent=sc;we.textContent=wc}
cb.addEventListener('click',function(){ig3()});
eb.addEventListener('click',function(){for(var y=0;y<rows;y++){for(var x=0;x<cols;x++){if(gr[y][x]!==0)gr[y][x]=0}}});
wb.addEventListener('click',function(){for(var x=0;x<cols;x++){gr[rows-1][x]=3}for(var y=0;y<rows;y++){gr[y][0]=3;gr[y][cols-1]=3}});
mbs.forEach(function(b){b.addEventListener('click',function(){mbs.forEach(function(b2){b2.classList.remove('active')});b.classList.add('active');mode=b.dataset.mode})});
sr.addEventListener('input',function(){bs2=parseInt(this.value)});
window.addEventListener('resize',rs);setTimeout(rs,100)})();
})();
</script>
</body>
</html>
