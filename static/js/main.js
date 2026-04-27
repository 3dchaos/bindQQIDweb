// 获取数据并渲染
function loadData() {
    fetch('/api/get_all').then(res => res.json()).then(data => {
        // 1. 服务器下拉
        const sel = document.getElementById('serverSelect');
        sel.innerHTML = '<option value="">-- 请选择服务器 --</option>';
        data.servers.forEach(s => {
            sel.innerHTML += `<option value="${s}">${s}</option>`;
        });

        // 2. 服务器列表管理
        const sUl = document.getElementById('serverUl');
        sUl.innerHTML = '';
        data.servers.forEach(s => {
            sUl.innerHTML += `<li>${s} <button class="btn-danger" style="width:40px;padding:2px;" onclick="delServer('${s}')">×</button></li>`;
        });

        // 3. 注册数据列表
        const rUl = document.getElementById('recordUl');
        rUl.innerHTML = '';
        data.records.forEach(r => {
            rUl.innerHTML += `
                <li>
                    <span class="record-info">${r}</span>
                    <div class="btns">
                        <button class="btn-edit" onclick="editRec('${r}')">修改</button>
                        <button class="btn-danger" onclick="delRec('${r}')">删除</button>
                    </div>
                </li>`;
        });
    });
}

// 注册功能
function doRegister() {
    const server = document.getElementById('serverSelect').value;
    const account = document.getElementById('acc').value.trim();
    const qq = document.getElementById('qq').value.trim();
    if(!server || !account || !qq) return alert("所有字段均为必填！");

    fetch('/api/add_record', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({server, account, qq})
    }).then(res => res.json()).then(data => {
        if(data.success) {
            alert("注册成功！");
            document.getElementById('acc').value = '';
            document.getElementById('qq').value = '';
            loadData();
        } else alert(data.msg);
    });
}

// 删除数据记录
function delRec(line) {
    if(!confirm("确定删除此行吗？")) return;
    fetch('/api/del_record', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({line})
    }).then(() => loadData());
}

// 修改数据记录
function editRec(line) {
    const newLine = prompt("请编辑该行文本:", line);
    if(!newLine || newLine === line) return;
    fetch('/api/edit_record', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({old: line, new: newLine})
    }).then(res => res.json()).then(data => {
        if(data.success) loadData(); else alert(data.msg);
    });
}

// 管理服务器列表
function addServer() {
    const name = document.getElementById('newSvr').value.trim();
    if(!name) return;
    fetch('/api/manage_server', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action:'add', name})
    }).then(() => { document.getElementById('newSvr').value=''; loadData(); });
}

function delServer(name) {
    fetch('/api/manage_server', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action:'del', name})
    }).then(() => loadData());
}

// 初始加载
document.addEventListener('DOMContentLoaded', loadData);
