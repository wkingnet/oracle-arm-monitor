async function api(path, options={}){const res=await fetch(path,{headers:{'Content-Type':'application/json'},...options});return res.json();}
function collectConfig(){const data={};document.querySelectorAll('[data-key]').forEach(el=>data[el.dataset.key]=el.value.trim());return data;}
async function refreshStatus(){const data=await api('/api/status');document.getElementById('statusText').textContent=data.running?`监控中 PID ${data.pid}`:'未运行';}
async function refreshLogs(){const data=await api('/api/logs');document.getElementById('logs').textContent=data.text||'';}
document.getElementById('saveBtn').onclick=async()=>{await api('/api/config',{method:'POST',body:JSON.stringify(collectConfig())});await refreshStatus();};
document.getElementById('startBtn').onclick=async()=>{await api('/api/config',{method:'POST',body:JSON.stringify(collectConfig())});await api('/api/start',{method:'POST'});await refreshStatus();};
document.getElementById('stopBtn').onclick=async()=>{await api('/api/stop',{method:'POST'});await refreshStatus();};
refreshStatus();refreshLogs();setInterval(refreshStatus,3000);setInterval(refreshLogs,3000);