// 测试showTab函数
function testShowTab(tabId) {
    console.log('测试切换到模块:', tabId);
    try {
        if (typeof showTab === 'function') {
            showTab(tabId);
            console.log('✓ 成功调用showTab函数');
            
            // 检查标签页是否显示
            const tab = document.getElementById(tabId + '-tab');
            if (tab && tab.style.display === 'block') {
                console.log('✓ 标签页显示成功');
            } else {
                console.log('✗ 标签页显示失败');
            }
            
            // 检查导航项激活状态
            const navItems = document.querySelectorAll('.nav-item');
            let activeFound = false;
            navItems.forEach(item => {
                if (item.classList.contains('active')) {
                    activeFound = true;
                }
            });
            if (activeFound) {
                console.log('✓ 导航项激活状态正确');
            } else {
                console.log('✗ 导航项激活状态错误');
            }
        } else {
            console.log('✗ showTab函数不存在');
        }
    } catch (e) {
        console.log('✗ 调用showTab函数时出错:', e.message);
    }
}

// 检查函数存在性
function checkFunctions() {
    console.log('=== 函数存在性检查 ===');
    console.log('showTab函数:', typeof showTab === 'function' ? '✓ 存在' : '✗ 不存在');
    console.log('loadTabData函数:', typeof loadTabData === 'function' ? '✓ 存在' : '✗ 不存在');
    console.log('SessionManager:', typeof SessionManager !== 'undefined' ? '✓ 存在' : '✗ 不存在');
    console.log('currentSystemMode:', typeof window.currentSystemMode !== 'undefined' ? '✓ 存在: ' + window.currentSystemMode : '✗ 不存在');
}

// 执行测试
checkFunctions();
testShowTab('market');
