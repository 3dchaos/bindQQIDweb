import sqlite3
from flask import Flask, render_template, jsonify, request

# 全局变量存储数据库管理器
global_db_manager = None

def set_global_db_manager(db_manager):
    """设置全局数据库管理器"""
    global global_db_manager
    global_db_manager = db_manager

# 创建Flask应用
app = Flask(__name__)

@app.route('/')
def index():
    """主页面 - 直接返回HTML内容，不依赖模板文件"""
    html_content = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>典狱长数据查询系统</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Microsoft YaHei', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: #333;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        
        .header {
            text-align: center;
            margin-bottom: 30px;
            color: white;
        }
        
        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }
        
        .header p {
            font-size: 1.2em;
            opacity: 0.9;
        }
        
        .ad-banner {
            margin-top: 15px;
            padding: 10px 20px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            backdrop-filter: blur(10px);
        }
        
        .ad-link {
            text-decoration: none;
            color: white;
            display: flex;
            flex-direction: column;
            align-items: center;
            transition: all 0.3s ease;
        }
        
        .ad-link:hover {
            transform: scale(1.05);
        }
        
        .ad-text {
            font-size: 1.1em;
            font-weight: bold;
            margin-bottom: 5px;
        }
        
        .ad-desc {
            font-size: 0.9em;
            opacity: 0.8;
        }
        
        .tabs {
            display: flex;
            background: white;
            border-radius: 10px 10px 0 0;
            overflow: hidden;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        
        .tab {
            flex: 1;
            padding: 15px 20px;
            background: #f8f9fa;
            border: none;
            cursor: pointer;
            font-size: 16px;
            font-weight: bold;
            transition: all 0.3s ease;
            color: #666;
        }
        
        .tab:hover {
            background: #e9ecef;
        }
        
        .tab.active {
            background: #007bff;
            color: white;
        }
        
        .tab-content {
            background: white;
            border-radius: 0 0 10px 10px;
            padding: 20px;
            min-height: 500px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        
        .tab-content:not(.active) {
            display: none;
        }
        
        .search-box {
            margin-bottom: 20px;
        }
        
        .search-box input {
            width: 100%;
            padding: 12px 15px;
            border: 2px solid #e9ecef;
            border-radius: 25px;
            font-size: 16px;
            transition: border-color 0.3s ease;
        }
        
        .search-box input:focus {
            outline: none;
            border-color: #007bff;
        }
        
        .list-container {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 15px;
            max-height: 400px;
            overflow-y: auto;
        }
        
        .list-item {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.3s ease;
            border: 2px solid transparent;
        }
        
        .list-item:hover {
            background: #e9ecef;
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        }
        
        .detail-container {
            display: none;
        }
        
        .back-btn {
            background: #6c757d;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            margin-bottom: 20px;
            font-size: 14px;
            transition: background 0.3s ease;
        }
        
        .back-btn:hover {
            background: #5a6268;
        }
        
        .detail-list-container {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 15px;
            max-height: 400px;
            overflow-y: auto;
        }
        
        .detail-item {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.3s ease;
            border: 2px solid transparent;
        }
        
        .detail-item:hover {
            background: #e9ecef;
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        }
        
        .detail-item h3 {
            color: #007bff;
            margin-bottom: 8px;
            font-size: 16px;
        }
        
        .detail-item p {
            margin: 3px 0;
            color: #666;
            font-size: 14px;
        }
        
        .probability {
            background: #28a745;
            color: white;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 12px;
            margin-left: 10px;
        }
        
        .loading {
            text-align: center;
            padding: 40px;
            color: #666;
            font-size: 16px;
        }
        
        .error {
            text-align: center;
            padding: 40px;
            color: #dc3545;
            font-size: 16px;
        }
        
        /* 滚动条样式 */
        ::-webkit-scrollbar {
            width: 8px;
        }
        
        ::-webkit-scrollbar-track {
            background: #f1f1f1;
            border-radius: 4px;
        }
        
        ::-webkit-scrollbar-thumb {
            background: #c1c1c1;
            border-radius: 4px;
        }
        
        ::-webkit-scrollbar-thumb:hover {
            background: #a8a8a8;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>典狱长数据查询系统</h1>
            <p>查询怪物爆率、地图信息、物品掉落</p>
            <div class="ad-banner">
                <a href="https://dyzplugin.win/" target="_blank" class="ad-link">
                    <span class="ad-text">典狱长封挂插件</span>
                    <span class="ad-desc">让外挂无处遁形，还游戏一片净土</span>
                </a>
            </div>
        </div>
        
        <div class="tabs">
            <button class="tab active" onclick="switchTab('maps')">地图查询</button>
            <button class="tab" onclick="switchTab('monsters')">怪物查询</button>
            <button class="tab" onclick="switchTab('items')">物品查询</button>
        </div>
        
        <div class="tab-content active" id="maps">
            <div class="search-box">
                <input type="text" id="mapSearch" placeholder="搜索地图..." oninput="filterMaps()">
            </div>
            <div id="mapList" class="list-container">
                <div class="loading">加载中...</div>
            </div>
            <div id="mapDetail" class="detail-container" style="display: none;">
                <button class="back-btn" onclick="showMapList()">返回地图列表</button>
                <div id="mapDetailContent"></div>
            </div>
        </div>
        
        <div class="tab-content" id="monsters">
            <div class="search-box">
                <input type="text" id="monsterSearch" placeholder="搜索怪物..." oninput="filterMonsters()">
            </div>
            <div id="monsterList" class="list-container">
                <div class="loading">加载中...</div>
            </div>
            <div id="monsterDetail" class="detail-container" style="display: none;">
                <button class="back-btn" onclick="showMonsterList()">返回怪物列表</button>
                <div id="monsterDetailContent"></div>
            </div>
        </div>
        
        <div class="tab-content" id="items">
            <div class="search-box">
                <input type="text" id="itemSearch" placeholder="搜索物品..." oninput="filterItems()">
            </div>
            <div id="itemList" class="list-container">
                <div class="loading">加载中...</div>
            </div>
            <div id="itemDetail" class="detail-container" style="display: none;">
                <button class="back-btn" onclick="showItemList()">返回物品列表</button>
                <div id="itemDetailContent"></div>
            </div>
        </div>
    </div>

    <script>
        let maps = [];
        let monsters = [];
        let items = [];
        
        // 切换标签页
        function switchTab(tabName) {
            // 隐藏所有内容
            document.querySelectorAll('.tab-content').forEach(content => {
                content.classList.remove('active');
            });
            document.querySelectorAll('.tab').forEach(tab => {
                tab.classList.remove('active');
            });
            
            // 显示选中的内容
            document.getElementById(tabName).classList.add('active');
            event.target.classList.add('active');
            
            // 加载数据
            if (tabName === 'maps' && maps.length === 0) {
                loadMaps();
            } else if (tabName === 'monsters' && monsters.length === 0) {
                loadMonsters();
            } else if (tabName === 'items' && items.length === 0) {
                loadItems();
            }
        }
        
        // 加载地图列表
        async function loadMaps() {
            try {
                const response = await fetch('/api/maps');
                maps = await response.json();
                displayMaps(maps);
            } catch (error) {
                document.getElementById('mapList').innerHTML = '<div class="error">加载失败</div>';
            }
        }
        
        // 显示地图列表
        function displayMaps(mapsToShow) {
            const container = document.getElementById('mapList');
            if (mapsToShow.length === 0) {
                container.innerHTML = '<div class="error">没有找到地图</div>';
                return;
            }
            
            container.innerHTML = mapsToShow.map(map => 
                `<div class="list-item" onclick="showMapDetail('${map.name}')">${map.alias}</div>`
            ).join('');
        }
        
        // 过滤地图
        function filterMaps() {
            const searchTerm = document.getElementById('mapSearch').value.toLowerCase();
            const filteredMaps = maps.filter(map => 
                map.alias.toLowerCase().includes(searchTerm) || map.name.toLowerCase().includes(searchTerm)
            );
            displayMaps(filteredMaps);
        }
        
        // 显示地图详情
        async function showMapDetail(mapName) {
            try {
                const response = await fetch(`/api/map/${encodeURIComponent(mapName)}`);
                const data = await response.json();
                const monsters = data.monsters;
                const mapAlias = data.map_alias;
                
                document.getElementById('mapList').style.display = 'none';
                document.getElementById('mapDetail').style.display = 'block';
                
                const content = document.getElementById('mapDetailContent');
                content.innerHTML = `
                    <h2>${mapAlias}</h2>
                    <h3>怪物刷新信息：</h3>
                    <div class="detail-list-container">
                        ${monsters.map(monster => `
                            <div class="detail-item" data-monster="${monster.name}" onclick="jumpToMonsterDetail(this.dataset.monster)">
                                <h3>${monster.name}</h3>
                                <p>坐标: (${monster.x}, ${monster.y})</p>
                                <p>范围: ${monster.range}</p>
                                <p>数量: ${monster.count}</p>
                                <p>刷新时间: ${monster.refresh_time} 分钟</p>
                            </div>
                        `).join('')}
                    </div>
                `;
            } catch (error) {
                document.getElementById('mapDetailContent').innerHTML = '<div class="error">加载失败</div>';
            }
        }
        
        // 显示地图列表
        function showMapList() {
            document.getElementById('mapList').style.display = 'grid';
            document.getElementById('mapDetail').style.display = 'none';
        }
        
        // 加载怪物列表
        async function loadMonsters() {
            try {
                const response = await fetch('/api/monsters');
                monsters = await response.json();
                displayMonsters(monsters);
            } catch (error) {
                document.getElementById('monsterList').innerHTML = '<div class="error">加载失败</div>';
            }
        }
        
        // 显示怪物列表
        function displayMonsters(monstersToShow) {
            const container = document.getElementById('monsterList');
            if (monstersToShow.length === 0) {
                container.innerHTML = '<div class="error">没有找到怪物</div>';
                return;
            }
            
            container.innerHTML = monstersToShow.map(monster => 
                `<div class="list-item" onclick="showMonsterDetail('${monster}')">${monster}</div>`
            ).join('');
        }
        
        // 过滤怪物
        function filterMonsters() {
            const searchTerm = document.getElementById('monsterSearch').value.toLowerCase();
            const filteredMonsters = monsters.filter(monster => monster.toLowerCase().includes(searchTerm));
            displayMonsters(filteredMonsters);
        }
        
        // 显示怪物详情
        async function showMonsterDetail(monsterName) {
            try {
                console.log('显示怪物详情:', monsterName);
                const response = await fetch(`/api/monster/${encodeURIComponent(monsterName)}`);
                const data = await response.json();
                
                document.getElementById('monsterList').style.display = 'none';
                document.getElementById('monsterDetail').style.display = 'block';
                
                const content = document.getElementById('monsterDetailContent');
                content.innerHTML = `
                    <h2>${monsterName}</h2>
                    
                    <h3>爆出物品：</h3>
                    <div class="detail-list-container">
                        ${data.items.map(item => `
                            <div class="detail-item" data-item="${item.name}" onclick="jumpToItemDetail(this.dataset.item)">
                                <h3>${item.name} <span class="probability">${item.probability}</span></h3>
                            </div>
                        `).join('')}
                    </div>
                    
                    <h3>出现地图：</h3>
                    <div class="detail-list-container">
                        ${data.maps.map(map => `
                            <div class="detail-item" data-map="${map.map_name}" onclick="jumpToMapDetail(this.dataset.map)">
                                <h3>${map.map_alias}</h3>
                                <p>坐标: (${map.x}, ${map.y})</p>
                                <p>范围: ${map.range}</p>
                                <p>数量: ${map.count}</p>
                                <p>刷新时间: ${map.refresh_time} 分钟</p>
                            </div>
                        `).join('')}
                    </div>
                `;
            } catch (error) {
                console.error('显示怪物详情失败:', error);
                document.getElementById('monsterDetailContent').innerHTML = '<div class="error">加载失败</div>';
            }
        }
        
        // 显示怪物列表
        function showMonsterList() {
            document.getElementById('monsterList').style.display = 'grid';
            document.getElementById('monsterDetail').style.display = 'none';
        }
        
        // 加载物品列表
        async function loadItems() {
            try {
                const response = await fetch('/api/items');
                items = await response.json();
                displayItems(items);
            } catch (error) {
                document.getElementById('itemList').innerHTML = '<div class="error">加载失败</div>';
            }
        }
        
        // 显示物品列表
        function displayItems(itemsToShow) {
            const container = document.getElementById('itemList');
            if (itemsToShow.length === 0) {
                container.innerHTML = '<div class="error">没有找到物品</div>';
                return;
            }
            
            container.innerHTML = itemsToShow.map(item => 
                `<div class="list-item" onclick="showItemDetail('${item}')">${item}</div>`
            ).join('');
        }
        
        // 过滤物品
        function filterItems() {
            const searchTerm = document.getElementById('itemSearch').value.toLowerCase();
            const filteredItems = items.filter(item => item.toLowerCase().includes(searchTerm));
            displayItems(filteredItems);
        }
        
        // 显示物品详情
        async function showItemDetail(itemName) {
            try {
                console.log('显示物品详情:', itemName);
                const response = await fetch(`/api/item/${encodeURIComponent(itemName)}`);
                const data = await response.json();
                
                document.getElementById('itemList').style.display = 'none';
                document.getElementById('itemDetail').style.display = 'block';
                
                const content = document.getElementById('itemDetailContent');
                content.innerHTML = `
                    <h2>${itemName}</h2>
                    
                    <h3>爆出怪物：</h3>
                    <div class="detail-list-container">
                        ${data.monsters.map(monster => `
                            <div class="detail-item" data-monster="${monster.name}" onclick="jumpToMonsterDetail(this.dataset.monster)">
                                <h3>${monster.name} <span class="probability">${monster.probability}</span></h3>
                            </div>
                        `).join('')}
                    </div>
                `;
            } catch (error) {
                console.error('显示物品详情失败:', error);
                document.getElementById('itemDetailContent').innerHTML = '<div class="error">加载失败</div>';
            }
        }
        
        // 显示物品列表
        function showItemList() {
            document.getElementById('itemList').style.display = 'grid';
            document.getElementById('itemDetail').style.display = 'none';
        }
        
        // 跳转到怪物详情（跨标签页）
        async function jumpToMonsterDetail(monsterName) {
            // 切换到怪物查询标签页
            switchTab('monsters');
            
            // 等待标签页切换完成后再显示详情
            setTimeout(async () => {
                try {
                    const response = await fetch(`/api/monster/${encodeURIComponent(monsterName)}`);
                    const data = await response.json();
                    
                    document.getElementById('monsterList').style.display = 'none';
                    document.getElementById('monsterDetail').style.display = 'block';
                    
                    const content = document.getElementById('monsterDetailContent');
                    content.innerHTML = `
                        <h2>${monsterName}</h2>
                        
                        <h3>爆出物品：</h3>
                        <div class="detail-list-container">
                            ${data.items.map(item => `
                                <div class="detail-item" data-item="${item.name}" onclick="jumpToItemDetail(this.dataset.item)">
                                    <h3>${item.name} <span class="probability">${item.probability}</span></h3>
                                </div>
                            `).join('')}
                        </div>
                        
                        <h3>出现地图：</h3>
                        <div class="detail-list-container">
                            ${data.maps.map(map => `
                                <div class="detail-item" data-map="${map.map_name}" onclick="jumpToMapDetail(this.dataset.map)">
                                    <h3>${map.map_alias}</h3>
                                    <p>坐标: (${map.x}, ${map.y})</p>
                                    <p>范围: ${map.range}</p>
                                    <p>数量: ${map.count}</p>
                                    <p>刷新时间: ${map.refresh_time} 分钟</p>
                                </div>
                            `).join('')}
                        </div>
                    `;
                } catch (error) {
                    console.error('跳转到怪物详情失败:', error);
                    document.getElementById('monsterDetailContent').innerHTML = '<div class="error">加载失败</div>';
                }
            }, 100);
        }
        
        // 跳转到物品详情（跨标签页）
        async function jumpToItemDetail(itemName) {
            // 切换到物品查询标签页
            switchTab('items');
            
            // 等待标签页切换完成后再显示详情
            setTimeout(async () => {
                try {
                    const response = await fetch(`/api/item/${encodeURIComponent(itemName)}`);
                    const data = await response.json();
                    
                    document.getElementById('itemList').style.display = 'none';
                    document.getElementById('itemDetail').style.display = 'block';
                    
                    const content = document.getElementById('itemDetailContent');
                    content.innerHTML = `
                        <h2>${itemName}</h2>
                        
                        <h3>爆出怪物：</h3>
                        <div class="detail-list-container">
                            ${data.monsters.map(monster => `
                                <div class="detail-item" data-monster="${monster.name}" onclick="jumpToMonsterDetail(this.dataset.monster)">
                                    <h3>${monster.name} <span class="probability">${monster.probability}</span></h3>
                                </div>
                            `).join('')}
                        </div>
                    `;
                } catch (error) {
                    console.error('跳转到物品详情失败:', error);
                    document.getElementById('itemDetailContent').innerHTML = '<div class="error">加载失败</div>';
                }
            }, 100);
        }
        
        // 跳转到地图详情（跨标签页）
        async function jumpToMapDetail(mapName) {
            // 切换到地图查询标签页
            switchTab('maps');
            
            // 等待标签页切换完成后再显示详情
            setTimeout(async () => {
                try {
                    const response = await fetch(`/api/map/${encodeURIComponent(mapName)}`);
                    const data = await response.json();
                    const monsters = data.monsters;
                    const mapAlias = data.map_alias;
                    
                    document.getElementById('mapList').style.display = 'none';
                    document.getElementById('mapDetail').style.display = 'block';
                    
                    const content = document.getElementById('mapDetailContent');
                    content.innerHTML = `
                        <h2>${mapAlias}</h2>
                        <h3>怪物刷新信息：</h3>
                        <div class="detail-list-container">
                            ${monsters.map(monster => `
                                <div class="detail-item" data-monster="${monster.name}" onclick="jumpToMonsterDetail(this.dataset.monster)">
                                    <h3>${monster.name}</h3>
                                    <p>坐标: (${monster.x}, ${monster.y})</p>
                                    <p>范围: ${monster.range}</p>
                                    <p>数量: ${monster.count}</p>
                                    <p>刷新时间: ${monster.refresh_time} 分钟</p>
                                </div>
                            `).join('')}
                        </div>
                    `;
                } catch (error) {
                    console.error('跳转到地图详情失败:', error);
                    document.getElementById('mapDetailContent').innerHTML = '<div class="error">加载失败</div>';
                }
            }, 100);
        }
        
        // 页面加载时加载地图数据
        window.onload = function() {
            loadMaps();
        };
    </script>
</body>
</html>'''
    
    return html_content

@app.route('/test')
def test():
    return jsonify({
        "status": "ok", 
        "message": "Flask服务器正常运行",
        "db_manager": "已设置" if global_db_manager else "未设置",
        "port": "正常"
    })

@app.route('/api/maps')
def get_maps():
    """获取所有地图列表"""
    if not global_db_manager:
        return jsonify({"error": "数据库未初始化"}), 500
    
    conn = sqlite3.connect(global_db_manager.db_path)
    cursor = conn.cursor()
    cursor.execute(f"SELECT DISTINCT map_name, map_alias FROM {global_db_manager.map_table} ORDER BY map_alias")
    maps = []
    for row in cursor.fetchall():
        map_name, map_alias = row
        maps.append({
            'name': map_name,
            'alias': map_alias or map_name
        })
    conn.close()
    return jsonify(maps)

@app.route('/api/map/<map_name>')
def get_map_monsters(map_name):
    """获取指定地图的怪物信息"""
    if not global_db_manager:
        return jsonify({"error": "数据库未初始化"}), 500
    
    conn = sqlite3.connect(global_db_manager.db_path)
    cursor = conn.cursor()
    cursor.execute(f'''
        SELECT monster_name, x, y, range_val, count, refresh_time, map_alias
        FROM {global_db_manager.map_table} WHERE map_name = ?
        ORDER BY monster_name
    ''', (map_name,))
    monsters = []
    map_alias = map_name
    for row in cursor.fetchall():
        monsters.append({
            'name': row[0],
            'x': row[1],
            'y': row[2],
            'range': row[3],
            'count': row[4],
            'refresh_time': row[5]
        })
        map_alias = row[6] if row[6] else map_name
    conn.close()
    return jsonify({
        'monsters': monsters,
        'map_alias': map_alias
    })

@app.route('/api/monsters')
def get_monsters():
    """获取所有怪物列表"""
    if not global_db_manager:
        return jsonify({"error": "数据库未初始化"}), 500
    
    conn = sqlite3.connect(global_db_manager.db_path)
    cursor = conn.cursor()
    cursor.execute(f"SELECT DISTINCT monster_name FROM {global_db_manager.monitems_table} ORDER BY monster_name")
    monsters = [row[0] for row in cursor.fetchall()]
    conn.close()
    return jsonify(monsters)

@app.route('/api/monster/<monster_name>')
def get_monster_info(monster_name):
    """获取指定怪物的信息"""
    if not global_db_manager:
        return jsonify({"error": "数据库未初始化"}), 500
    
    conn = sqlite3.connect(global_db_manager.db_path)
    cursor = conn.cursor()
    
    # 获取怪物爆出物品
    cursor.execute(f'''
        SELECT item_name, probability, rate_numerator, rate_denominator
        FROM {global_db_manager.monitems_table} WHERE monster_name = ?
        ORDER BY rate_numerator DESC, rate_denominator ASC
    ''', (monster_name,))
    items = []
    for row in cursor.fetchall():
        items.append({
            'name': row[0],
            'probability': row[1],
            'rate_numerator': row[2],
            'rate_denominator': row[3]
        })
    
    # 获取怪物出现的地图
    cursor.execute(f'''
        SELECT DISTINCT map_name, map_alias, x, y, range_val, count, refresh_time
        FROM {global_db_manager.map_table} WHERE monster_name = ?
        ORDER BY map_alias
    ''', (monster_name,))
    maps = []
    for row in cursor.fetchall():
        maps.append({
            'map_name': row[0],
            'map_alias': row[1] or row[0],
            'x': row[2],
            'y': row[3],
            'range': row[4],
            'count': row[5],
            'refresh_time': row[6]
        })
    
    conn.close()
    return jsonify({
        'items': items,
        'maps': maps
    })

@app.route('/api/items')
def get_items():
    """获取所有物品列表"""
    if not global_db_manager:
        return jsonify({"error": "数据库未初始化"}), 500
    
    conn = sqlite3.connect(global_db_manager.db_path)
    cursor = conn.cursor()
    cursor.execute(f"SELECT item_name FROM {global_db_manager.item_table} ORDER BY item_name")
    items = [row[0] for row in cursor.fetchall()]
    conn.close()
    return jsonify(items)

@app.route('/api/item/<item_name>')
def get_item_info(item_name):
    """获取指定物品的信息"""
    if not global_db_manager:
        return jsonify({"error": "数据库未初始化"}), 500
    
    conn = sqlite3.connect(global_db_manager.db_path)
    cursor = conn.cursor()
    
    # 获取爆出该物品的怪物
    cursor.execute(f'''
        SELECT monster_name, probability, rate_numerator, rate_denominator
        FROM {global_db_manager.monitems_table} WHERE item_name = ?
        ORDER BY rate_numerator DESC, rate_denominator ASC
    ''', (item_name,))
    monsters = []
    for row in cursor.fetchall():
        monsters.append({
            'name': row[0],
            'probability': row[1],
            'rate_numerator': row[2],
            'rate_denominator': row[3]
        })
    
    conn.close()
    return jsonify({'monsters': monsters}) 

@app.route('/shutdown')
def shutdown_server():
    """优雅关闭 Flask 服务器"""
    func = request.environ.get('werkzeug.server.shutdown')
    if func:
        func()
    return jsonify({"status": "shutting_down"})
